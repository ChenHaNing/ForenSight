import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Tuple, List


SKILL_CALCULATOR_PATH = Path(
    "/Users/han/.codex/skills/analyzing-financial-statements/calculate_ratios.py"
)


FIN_STATEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "income_statement": {"type": "object"},
        "balance_sheet": {"type": "object"},
        "cash_flow": {"type": "object"},
        "market_data": {"type": "object"},
        "meta": {"type": "object"},
    },
    "required": [
        "income_statement",
        "balance_sheet",
        "cash_flow",
        "market_data",
    ],
}


def _load_ratio_calculator():
    spec = importlib.util.spec_from_file_location(
        "financial_ratio_calculator", SKILL_CALCULATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load financial ratio calculator skill")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FinancialRatioCalculator


def _merge_sections(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    for section in ["income_statement", "balance_sheet", "cash_flow", "market_data"]:
        base.setdefault(section, {})
        base[section].update(update.get(section, {}) or {})
    return base


def extract_financial_statements(text: str, llm) -> Dict[str, Any]:
    system_prompt = "你是财务报表解析专家，负责从文本中提取核心报表数据。"
    user_prompt = (
        "请从以下文本中抽取资产负债表、利润表、现金流量表的核心字段，"
        "尽量给出数值（数字），允许负数或括号表示的负数，保留原始数值。"
        "若单位为百万/十亿/千，保留数值本身，不需要换算。"
        "优先提取最新年度/期间的数值，若有多期请以最新为主。"
        "缺失请用null。请输出JSON，包含income_statement、"
        "balance_sheet、cash_flow、market_data。\n\n"
        f"文本内容：\n{text}\n"
    )
    return llm.generate_json(system_prompt, user_prompt, FIN_STATEMENT_SCHEMA)


def extract_financial_statements_parallel(text: str, llm, parallel: bool = True) -> Dict[str, Any]:
    # If llm is not thread-safe (e.g., FakeLLM), fall back to sequential
    if getattr(llm, "_responses", None) is not None:
        parallel = False

    prompts = [
        (
            "你是财务报表解析专家。",
            "仅抽取利润表关键字段（revenue、cost_of_goods_sold、operating_income、net_income、ebit、interest_expense、ebitda）。"
            "允许负数或括号表示的负数，保留原始数值。若单位为百万/十亿/千，保留数值本身。",
            {"income_statement": {}},
        ),
        (
            "你是财务报表解析专家。",
            "仅抽取资产负债表关键字段（total_assets、current_assets、inventory、cash_and_equivalents、current_liabilities、shareholders_equity、total_debt、accounts_receivable）。"
            "允许负数或括号表示的负数，保留原始数值。若单位为百万/十亿/千，保留数值本身。",
            {"balance_sheet": {}},
        ),
        (
            "你是财务报表解析专家。",
            "仅抽取现金流量表关键字段（operating_cash_flow、investing_cash_flow、financing_cash_flow）。"
            "允许负数或括号表示的负数，保留原始数值。若单位为百万/十亿/千，保留数值本身。",
            {"cash_flow": {}},
        ),
        (
            "你是财务报表解析专家。",
            "仅抽取市场数据字段（share_price、shares_outstanding、earnings_growth_rate）。"
            "若存在多个期间，优先最新值。",
            {"market_data": {}},
        ),
    ]

    def run_prompt(system, instruction):
        user_prompt = (
            f"{instruction}\n"  # instruction is already specific
            "缺失请用null。输出JSON，包含income_statement、balance_sheet、cash_flow、market_data。\n\n"
            f"文本内容：\n{text}\n"
        )
        return llm.generate_json(system, user_prompt, FIN_STATEMENT_SCHEMA)

    results: List[Dict[str, Any]] = []
    if parallel:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_prompt, p[0], p[1]) for p in prompts]
            for fut in futures:
                results.append(fut.result())
    else:
        for system, instruction, _ in prompts:
            results.append(run_prompt(system, instruction))

    merged: Dict[str, Any] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "market_data": {},
    }
    for res in results:
        _merge_sections(merged, res)
    return merged


def extract_financials_with_fallback(
    text: str,
    llm,
    parallel: bool = True,
    min_fields: int = 4,
) -> Dict[str, Any]:
    data = extract_financial_statements_parallel(text, llm, parallel=parallel)
    if _count_financial_fields(data) >= min_fields:
        return data
    fallback = extract_financial_statements(text, llm)
    return _merge_sections(data, fallback)


def _count_financial_fields(data: Dict[str, Any]) -> int:
    count = 0
    for section in ["income_statement", "balance_sheet", "cash_flow", "market_data"]:
        values = (data.get(section, {}) or {}).values()
        count += sum(1 for value in values if value is not None)
    return count


def _coerce_number(value: Any) -> float:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace(",", "").replace("%", "")
        return float(cleaned)
    except Exception:
        return None


def normalize_financial_data(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    notes = []
    normalized: Dict[str, Any] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "market_data": {},
    }
    for section in ["income_statement", "balance_sheet", "cash_flow", "market_data"]:
        raw = data.get(section, {}) or {}
        for key, value in raw.items():
            num = _coerce_number(value)
            if num is None:
                notes.append(f"{section}.{key} 缺失或无法解析")
            else:
                normalized[section][key] = num
    return normalized, notes


def compute_financial_metrics(financial_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    normalized, notes = normalize_financial_data(financial_data)
    ratio_cls = _load_ratio_calculator()
    calculator = ratio_cls(normalized)
    metrics = calculator.calculate_all_ratios()
    return metrics, notes
