import importlib.util
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple, List, Optional
import re
import os
from datetime import datetime

import requests


SKILL_CALCULATOR_PATH = Path(
    "/Users/han/.codex/skills/analyzing-financial-statements/calculate_ratios.py"
)
RATIO_CALCULATOR_PATH_ENV = "FINANCIAL_RATIO_CALCULATOR_PATH"


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

SECTION_FIELDS = {
    "income_statement": {
        "revenue",
        "cost_of_goods_sold",
        "operating_income",
        "net_income",
        "ebit",
        "interest_expense",
        "ebitda",
    },
    "balance_sheet": {
        "total_assets",
        "current_assets",
        "inventory",
        "cash_and_equivalents",
        "current_liabilities",
        "shareholders_equity",
        "total_debt",
        "accounts_receivable",
    },
    "cash_flow": {
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
    },
    "market_data": {
        "share_price",
        "shares_outstanding",
        "earnings_growth_rate",
    },
}

ALIASES = {
    "income_statement": {
        "net_sales": "revenue",
        "total_net_sales": "revenue",
        "sales": "revenue",
        "total_cost_of_sales": "cost_of_goods_sold",
        "cost_of_sales": "cost_of_goods_sold",
    },
    "balance_sheet": {
        "total_shareholders_equity": "shareholders_equity",
        "total_stockholders_equity": "shareholders_equity",
        "stockholders_equity": "shareholders_equity",
        "cash": "cash_and_equivalents",
        "receivables": "accounts_receivable",
    },
    "cash_flow": {
        "net_cash_from_operating_activities": "operating_cash_flow",
        "net_cash_from_investing_activities": "investing_cash_flow",
        "net_cash_from_financing_activities": "financing_cash_flow",
        "cash_from_financing_activities": "financing_cash_flow",
    },
    "market_data": {
        "closing_price": "share_price",
        "price": "share_price",
        "shares": "shares_outstanding",
        "income_growth_rate": "earnings_growth_rate",
        "earnings_growth": "earnings_growth_rate",
    },
}


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _load_ratio_calculator():
    candidates: List[Path] = []
    env_path = os.getenv(RATIO_CALCULATOR_PATH_ENV, "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    candidates.append(SKILL_CALCULATOR_PATH)

    load_errors: List[str] = []
    for path in candidates:
        ratio_cls, err = _load_ratio_calculator_from_path(path)
        if ratio_cls is not None:
            return ratio_cls
        if err:
            load_errors.append(err)

    try:
        from .ratio_calculator import FinancialRatioCalculator

        return FinancialRatioCalculator
    except Exception as exc:
        load_errors.append(f"local module: {exc}")

    detail = "; ".join(load_errors) if load_errors else "no available calculator source"
    raise RuntimeError(f"Failed to load financial ratio calculator ({detail})")


def _load_ratio_calculator_from_path(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    if not path.exists():
        return None, None

    spec = importlib.util.spec_from_file_location(
        f"financial_ratio_calculator_{abs(hash(str(path)))}", path
    )
    if spec is None or spec.loader is None:
        return None, f"{path}: invalid import spec"

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return None, f"{path}: {exc}"

    ratio_cls = getattr(module, "FinancialRatioCalculator", None)
    if ratio_cls is None:
        return None, f"{path}: missing FinancialRatioCalculator"
    return ratio_cls, None


def _merge_sections(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    for section in ["income_statement", "balance_sheet", "cash_flow", "market_data"]:
        base.setdefault(section, {})
        base[section].update(update.get(section, {}) or {})
    return base


def _canonicalize_financial_data(data: Dict[str, Any]) -> Dict[str, Any]:
    canonical: Dict[str, Any] = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "market_data": {},
    }
    for section, fields in SECTION_FIELDS.items():
        raw = data.get(section, {}) or {}
        alias_map = ALIASES.get(section, {})
        for raw_key, value in raw.items():
            key = str(raw_key).strip().lower().replace(" ", "_")
            key = re.sub(r"[^a-z0-9_]", "", key)
            key = alias_map.get(key, key)
            if key in fields:
                canonical[section][key] = value
    return canonical


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
    # Fall back to sequential mode when a non-thread-safe test double is injected.
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
    enrichment_text: str = "",
    tavily_client=None,
    company_name: str = "",
) -> Dict[str, Any]:
    data = _canonicalize_financial_data(
        extract_financial_statements_parallel(text, llm, parallel=parallel)
    )
    if _count_financial_fields(data) >= min_fields:
        return _enrich_financial_data(
            data,
            source_text=enrichment_text or text,
            tavily_client=tavily_client,
            company_name=company_name,
        )
    fallback = _canonicalize_financial_data(extract_financial_statements(text, llm))
    merged = _merge_sections(data, fallback)
    return _enrich_financial_data(
        merged,
        source_text=enrichment_text or text,
        tavily_client=tavily_client,
        company_name=company_name,
    )


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
        cleaned = str(value).strip()
        if not cleaned:
            return None
        lower = cleaned.lower()
        if lower in {"none", "null", "nan", "n/a", "na", "-", "—", "--"}:
            return None
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        cleaned = cleaned.replace("(", "").replace(")", "")
        cleaned = cleaned.replace(",", "").replace("%", "")
        cleaned = cleaned.replace("$", "").replace("¥", "")
        cleaned = cleaned.replace("−", "-").replace("–", "-")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if not match:
            return None
        number = float(match.group(0))
        if negative and number > 0:
            number = -number
        return number
    except Exception:
        return None


def _extract_number_series(line: str) -> List[float]:
    numbers: List[float] = []
    for raw in re.findall(r"\(?-?\d[\d,]*(?:\.\d+)?\)?", line):
        num = _coerce_number(raw)
        if num is not None:
            numbers.append(num)
    return numbers


def _section_block(text: str, start_pattern: str, end_patterns: List[str]) -> str:
    start = re.search(start_pattern, text, flags=re.IGNORECASE)
    if not start:
        return text
    tail = text[start.start() :]
    end_index = None
    for pattern in end_patterns:
        hit = re.search(pattern, tail, flags=re.IGNORECASE)
        if hit and hit.start() > 0:
            if end_index is None or hit.start() < end_index:
                end_index = hit.start()
    if end_index is None:
        return tail
    return tail[:end_index]


def _extract_first_by_patterns(text: str, patterns: List[str]) -> float:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = _coerce_number(match.group(1))
            if value is not None:
                return value
    return None


def _extract_revenue(text: str) -> float:
    operations_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+OPERATIONS",
        [r"CONSOLIDATED\s+BALANCE\s+SHEETS", r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS", r"See\s+accompanying"],
    )
    return _extract_first_by_patterns(
        operations_block,
        [
            r"Total\s+net\s+sales[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Net\s+sales[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Total\s+revenue(?:s)?[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Revenue(?:s)?[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )


def _extract_cost_of_goods_sold(text: str) -> float:
    operations_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+OPERATIONS",
        [r"CONSOLIDATED\s+BALANCE\s+SHEETS", r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS", r"See\s+accompanying"],
    )
    return _extract_first_by_patterns(
        operations_block,
        [
            r"Total\s+cost\s+of\s+sales[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Cost\s+of\s+sales[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Cost\s+of\s+goods\s+sold[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Cost\s+of\s+products\s+sold[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )


def _extract_operating_income(text: str) -> float:
    operations_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+OPERATIONS",
        [r"CONSOLIDATED\s+BALANCE\s+SHEETS", r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS", r"See\s+accompanying"],
    )
    return _extract_first_by_patterns(
        operations_block,
        [
            r"Operating\s+income[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Income\s+from\s+operations[^\n\r]{0,160}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )


def _extract_financing_cash_flow(text: str) -> float:
    cashflow_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS",
        [r"See\s+accompanying", r"Apple\s+Inc\.\s+\|\s+20\d{2}\s+Form\s+10-K"],
    )
    return _extract_first_by_patterns(
        cashflow_block,
        [
            r"Cash\s+used\s+in\s+financing\s+activities[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Cash\s+provided\s+by\s+financing\s+activities[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )


def _extract_cash_begin_end_balances(text: str) -> Tuple[float, float]:
    cashflow_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS",
        [r"See\s+accompanying", r"Apple\s+Inc\.\s+\|\s+20\d{2}\s+Form\s+10-K"],
    )
    begin = _extract_first_by_patterns(
        cashflow_block,
        [
            r"Cash[^\n\r]{0,220}?beginning\s+balances[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )
    end = _extract_first_by_patterns(
        cashflow_block,
        [
            r"Cash[^\n\r]{0,220}?ending\s+balances[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )
    return begin, end


def _extract_term_debt_total(text: str) -> float:
    balance_block = _section_block(
        text,
        r"CONSOLIDATED\s+BALANCE\s+SHEETS",
        [r"CONSOLIDATED\s+STATEMENTS\s+OF\s+OPERATIONS", r"See\s+accompanying"],
    )
    direct = _extract_first_by_patterns(
        balance_block,
        [r"Total\s+debt[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)"],
    )
    if direct is not None:
        return direct
    term_debt_values: List[float] = []
    for match in re.finditer(r"Term\s+debt[^\n\r]{0,120}", balance_block, flags=re.IGNORECASE):
        line = match.group(0)
        numbers = _extract_number_series(line)
        if numbers:
            term_debt_values.append(numbers[0])
    if len(term_debt_values) >= 2:
        return term_debt_values[0] + term_debt_values[1]
    if len(term_debt_values) == 1:
        return term_debt_values[0]
    return None


def _extract_shareholders_equity(text: str) -> float:
    balance_block = _section_block(
        text,
        r"CONSOLIDATED\s+BALANCE\s+SHEETS",
        [r"CONSOLIDATED\s+STATEMENTS\s+OF\s+OPERATIONS", r"See\s+accompanying"],
    )
    for line in balance_block.splitlines():
        lowered = line.lower()
        if "total shareholders" not in lowered and "total stockholders" not in lowered:
            continue
        if "beginning" in lowered or "ending" in lowered:
            continue
        values = _extract_number_series(line)
        if values:
            return values[0]
    fallback = _extract_first_by_patterns(
        balance_block,
        [
            r"Total\s+shareholders[’']?\s+equity(?!,\s*beginning)[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Total\s+stockholders[’']?\s+equity(?!,\s*beginning)[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )
    if fallback is not None:
        return fallback
    return _extract_first_by_patterns(
        text,
        [
            r"Total\s+shareholders[’']?\s+equity,\s*ending\s+balances[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Total\s+stockholders[’']?\s+equity,\s*ending\s+balances[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )


def _extract_interest_expense(text: str) -> float:
    operations_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+OPERATIONS",
        [r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS", r"See\s+accompanying"],
    )
    direct = _extract_first_by_patterns(
        operations_block,
        [
            r"Interest\s+expense[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            r"Interest\s+and\s+other[^\n\r]{0,120}?expense[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
        ],
    )
    if direct is not None:
        return abs(direct)
    fallback = _extract_first_by_patterns(
        operations_block,
        [r"Other\s+income/\(expense\),\s*net[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)"],
    )
    if fallback is not None:
        return abs(fallback)
    fallback_all = _extract_first_by_patterns(
        text,
        [r"Other\s+income/\(expense\),\s*net[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)"],
    )
    if fallback_all is not None:
        return abs(fallback_all)
    return None


def _extract_depreciation_amortization(text: str) -> float:
    cashflow_block = _section_block(
        text,
        r"CONSOLIDATED\s+STATEMENTS\s+OF\s+CASH\s+FLOWS",
        [r"See\s+accompanying", r"Apple\s+Inc\.\s+\|\s+20\d{2}\s+Form\s+10-K"],
    )
    return _extract_first_by_patterns(
        cashflow_block,
        [r"Depreciation\s+and\s+amortization[^\n\r]{0,120}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)"],
    )


def _extract_share_price(text: str) -> float:
    return _extract_first_by_patterns(
        text,
        [
            r"closing\s+price[\s\S]{0,220}?\$\s*(\d+(?:\.\d+)?)",
            r"stock\s+price[\s\S]{0,220}?\$\s*(\d+(?:\.\d+)?)",
        ],
    )


def _extract_market_cap(text: str) -> float:
    match = re.search(
        r"aggregate\s+market\s+value[\s\S]{0,240}?\$\s*([\d,]+(?:\.\d+)?)\s*(trillion|billion|million)?",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    base = _coerce_number(match.group(1))
    if base is None:
        return None
    scale = (match.group(2) or "").lower()
    if scale == "trillion":
        base *= 1_000_000_000_000
    elif scale == "billion":
        base *= 1_000_000_000
    elif scale == "million":
        base *= 1_000_000
    return base


def _extract_earnings_growth_rate(text: str) -> float:
    row_patterns = [
        r"Net\s+income[^\n\r]{0,200}",
        r"Total\s+net\s+sales[^\n\r]{0,200}",
        r"Revenue[^\n\r]{0,200}",
    ]
    for pattern in row_patterns:
        row_match = re.search(pattern, text, flags=re.IGNORECASE)
        if not row_match:
            continue
        series = _extract_number_series(row_match.group(0))
        if len(series) >= 2 and series[1] != 0:
            growth = (series[0] - series[1]) / abs(series[1])
            if -1 < growth < 5:
                return growth
    percentage = _extract_first_by_patterns(
        text,
        [r"earnings\s+growth[^\n\r]{0,80}?(-?\d+(?:\.\d+)?)%"],
    )
    if percentage is not None:
        return percentage / 100.0
    return None


def _sec_enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return os.getenv("ENABLE_SEC_COMPANYFACTS", "true").lower() == "true"


def _sec_headers() -> Dict[str, str]:
    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "FFMAS Research Bot/1.0 (contact: research@example.com)",
    )
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


def _http_get_json(url: str, timeout: int = 20) -> Dict[str, Any]:
    try:
        resp = requests.get(url, headers=_sec_headers(), timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, dict) else {}
    except requests.RequestException:
        return {}


def _normalize_company_name(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    tokens = [t for t in lowered.split() if t]
    stop = {"inc", "incorporated", "corporation", "corp", "co", "company", "ltd", "llc", "plc"}
    filtered = [t for t in tokens if t not in stop]
    return " ".join(filtered) if filtered else lowered


def _extract_possible_ticker(text: str) -> str:
    patterns = [
        r"Trading\s+Symbol(?:\(s\))?[^\n\r]{0,40}\b([A-Z]{1,5})\b",
        r"Nasdaq(?:\s+Global\s+\w+)?[^\n\r]{0,40}\b([A-Z]{1,5})\b",
        r"NYSE[^\n\r]{0,40}\b([A-Z]{1,5})\b",
    ]
    for pattern in patterns:
        hit = re.search(pattern, text or "", flags=re.IGNORECASE)
        if not hit:
            continue
        ticker = str(hit.group(1) or "").upper().strip()
        if ticker and ticker not in {"NASDAQ", "NYSE"}:
            return ticker
    return ""


@lru_cache(maxsize=1)
def _load_sec_company_tickers() -> List[Dict[str, Any]]:
    if not _sec_enabled():
        return []
    payload = _http_get_json(SEC_TICKERS_URL)
    if not payload:
        return []

    rows: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        values = []

    for item in values:
        if not isinstance(item, dict):
            continue
        cik = item.get("cik_str") or item.get("cik")
        ticker = str(item.get("ticker", "")).upper().strip()
        title = str(item.get("title", "")).strip()
        if cik is None or not ticker or not title:
            continue
        try:
            cik_num = int(cik)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "cik": str(cik_num).zfill(10),
                "ticker": ticker,
                "title": title,
                "normalized_title": _normalize_company_name(title),
            }
        )
    return rows


def _resolve_sec_cik(company_name: str, source_text: str) -> str:
    rows = _load_sec_company_tickers()
    if not rows:
        return ""

    ticker = _extract_possible_ticker(source_text)
    if ticker:
        for item in rows:
            if item["ticker"] == ticker:
                return item["cik"]

    normalized = _normalize_company_name(company_name)
    if not normalized:
        return ""

    for item in rows:
        if item["normalized_title"] == normalized:
            return item["cik"]
    for item in rows:
        if normalized and normalized in item["normalized_title"]:
            return item["cik"]
    return ""


def _pick_latest_fact_value(entries: List[Dict[str, Any]]) -> float:
    if not entries:
        return None
    numeric = []
    for entry in entries:
        value = _coerce_number(entry.get("val"))
        if value is None:
            continue
        item = dict(entry)
        item["_val"] = value
        numeric.append(item)
    if not numeric:
        return None

    annual = [e for e in numeric if str(e.get("form", "")).upper() in SEC_ANNUAL_FORMS]
    candidates = annual or numeric
    candidates.sort(
        key=lambda e: (
            int(_coerce_number(e.get("fy")) or 0),
            str(e.get("fp", "")) == "FY",
            str(e.get("end", "")),
            str(e.get("filed", "")),
        ),
        reverse=True,
    )
    return _coerce_number(candidates[0].get("_val"))


def _get_companyfact_value(
    companyfacts: Dict[str, Any],
    concepts: List[Tuple[str, str]],
    preferred_units: List[str],
) -> float:
    facts = companyfacts.get("facts", {}) or {}
    for taxonomy, concept in concepts:
        concept_payload = (((facts.get(taxonomy, {}) or {}).get(concept, {}) or {}).get("units", {}) or {})
        if not concept_payload:
            continue
        ordered_units = preferred_units + [u for u in concept_payload if u not in preferred_units]
        for unit in ordered_units:
            values = concept_payload.get(unit, []) or []
            value = _pick_latest_fact_value(values)
            if value is not None:
                return value
    return None


def _fill_financials_from_sec_companyfacts(
    income: Dict[str, Any],
    balance: Dict[str, Any],
    cash: Dict[str, Any],
    market: Dict[str, Any],
    company_name: str,
    source_text: str,
) -> None:
    if not _sec_enabled():
        return
    cik = _resolve_sec_cik(company_name, source_text)
    if not cik:
        return
    payload = _http_get_json(SEC_COMPANYFACTS_URL.format(cik=cik))
    if not payload:
        return

    def apply(target: Dict[str, Any], key: str, value: Any) -> None:
        numeric = _coerce_number(value)
        if numeric is None:
            return
        # SEC CompanyFacts uses a consistent base unit (usually USD / shares).
        # Prefer it over heterogeneous OCR/LLM-extracted values to avoid unit-mixing.
        target[key] = numeric

    apply(
        income,
        "revenue",
        _get_companyfact_value(
            payload,
            [
                ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "SalesRevenueNet"),
                ("us-gaap", "Revenues"),
                ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
            ],
            ["USD"],
        ),
    )
    apply(
        income,
        "cost_of_goods_sold",
        _get_companyfact_value(
            payload,
            [
                ("us-gaap", "CostOfGoodsAndServicesSold"),
                ("us-gaap", "CostOfGoodsSold"),
                ("us-gaap", "CostOfSales"),
            ],
            ["USD"],
        ),
    )
    apply(
        income,
        "operating_income",
        _get_companyfact_value(
            payload,
            [("us-gaap", "OperatingIncomeLoss")],
            ["USD"],
        ),
    )
    apply(
        income,
        "net_income",
        _get_companyfact_value(
            payload,
            [("us-gaap", "NetIncomeLoss")],
            ["USD"],
        ),
    )
    apply(
        income,
        "interest_expense",
        _get_companyfact_value(
            payload,
            [("us-gaap", "InterestExpense"), ("us-gaap", "InterestAndDebtExpense")],
            ["USD"],
        ),
    )

    apply(
        balance,
        "total_assets",
        _get_companyfact_value(
            payload,
            [("us-gaap", "Assets")],
            ["USD"],
        ),
    )
    apply(
        balance,
        "current_assets",
        _get_companyfact_value(
            payload,
            [("us-gaap", "AssetsCurrent")],
            ["USD"],
        ),
    )
    apply(
        balance,
        "inventory",
        _get_companyfact_value(
            payload,
            [("us-gaap", "InventoryNet"), ("us-gaap", "InventoryFinishedGoods")],
            ["USD"],
        ),
    )
    apply(
        balance,
        "cash_and_equivalents",
        _get_companyfact_value(
            payload,
            [("us-gaap", "CashAndCashEquivalentsAtCarryingValue")],
            ["USD"],
        ),
    )
    apply(
        balance,
        "current_liabilities",
        _get_companyfact_value(
            payload,
            [("us-gaap", "LiabilitiesCurrent")],
            ["USD"],
        ),
    )
    apply(
        balance,
        "shareholders_equity",
        _get_companyfact_value(
            payload,
            [
                ("us-gaap", "StockholdersEquity"),
                ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
            ],
            ["USD"],
        ),
    )
    apply(
        balance,
        "accounts_receivable",
        _get_companyfact_value(
            payload,
            [("us-gaap", "AccountsReceivableNetCurrent"), ("us-gaap", "AccountsReceivableNet")],
            ["USD"],
        ),
    )

    total_debt = _get_companyfact_value(
        payload,
        [
            ("us-gaap", "Debt"),
            ("us-gaap", "DebtAndCapitalLeaseObligations"),
            ("us-gaap", "LongTermDebtAndCapitalLeaseObligations"),
        ],
        ["USD"],
    )
    if total_debt is None:
        long_term = _get_companyfact_value(
            payload,
            [("us-gaap", "LongTermDebt"), ("us-gaap", "LongTermDebtNoncurrent")],
            ["USD"],
        )
        current = _get_companyfact_value(
            payload,
            [
                ("us-gaap", "LongTermDebtCurrent"),
                ("us-gaap", "DebtCurrent"),
                ("us-gaap", "ShortTermBorrowings"),
            ],
            ["USD"],
        )
        if long_term is not None and current is not None:
            total_debt = long_term + current
        elif long_term is not None:
            total_debt = long_term
        elif current is not None:
            total_debt = current
    apply(balance, "total_debt", total_debt)

    apply(
        cash,
        "operating_cash_flow",
        _get_companyfact_value(
            payload,
            [("us-gaap", "NetCashProvidedByUsedInOperatingActivities")],
            ["USD"],
        ),
    )
    apply(
        cash,
        "investing_cash_flow",
        _get_companyfact_value(
            payload,
            [("us-gaap", "NetCashProvidedByUsedInInvestingActivities")],
            ["USD"],
        ),
    )
    apply(
        cash,
        "financing_cash_flow",
        _get_companyfact_value(
            payload,
            [("us-gaap", "NetCashProvidedByUsedInFinancingActivities")],
            ["USD"],
        ),
    )
    apply(
        market,
        "shares_outstanding",
        _get_companyfact_value(
            payload,
            [("dei", "EntityCommonStockSharesOutstanding")],
            ["shares"],
        ),
    )


def _fill_income_fields_from_tavily(income: Dict[str, Any], company_name: str, tavily_client) -> None:
    if not tavily_client or not getattr(tavily_client, "enabled", False):
        return
    missing_revenue = _coerce_number(income.get("revenue")) is None
    missing_cogs = _coerce_number(income.get("cost_of_goods_sold")) is None
    missing_operating = _coerce_number(income.get("operating_income")) is None
    if not (missing_revenue or missing_cogs or missing_operating):
        return

    query = (
        f"{company_name or '目标公司'} latest annual report total net sales "
        "cost of sales operating income"
    )
    results = tavily_client.search(query, max_results=5)
    for item in results:
        text = " ".join([str(item.get("title", "")), str(item.get("content", ""))])
        if missing_revenue and _coerce_number(income.get("revenue")) is None:
            value = _extract_revenue(text)
            if value is not None:
                income["revenue"] = value
        if missing_cogs and _coerce_number(income.get("cost_of_goods_sold")) is None:
            value = _extract_cost_of_goods_sold(text)
            if value is not None:
                income["cost_of_goods_sold"] = value
        if missing_operating and _coerce_number(income.get("operating_income")) is None:
            value = _extract_operating_income(text)
            if value is not None:
                income["operating_income"] = value


def _fill_share_price_from_tavily(company_name: str, tavily_client) -> float:
    if not tavily_client or not getattr(tavily_client, "enabled", False):
        return None
    query = f"{company_name or '目标公司'} stock closing price latest annual report"
    results = tavily_client.search(query, max_results=5)
    for item in results:
        text = " ".join([str(item.get("title", "")), str(item.get("content", ""))])
        price = _extract_share_price(text)
        if price and 0 < price < 10000:
            return price
    return None


def _fill_financing_cash_flow_from_tavily(company_name: str, tavily_client) -> float:
    if not tavily_client or not getattr(tavily_client, "enabled", False):
        return None
    query = f"{company_name or '目标公司'} cash flow from financing activities latest annual report"
    results = tavily_client.search(query, max_results=5)
    for item in results:
        text = " ".join([str(item.get("title", "")), str(item.get("content", ""))])
        value = _extract_first_by_patterns(
            text,
            [
                r"financing\s+activities[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
                r"cash\s+flow\s+from\s+financing[^\n\r]{0,80}?(\(?-?\d[\d,]*(?:\.\d+)?\)?)",
            ],
        )
        if value is not None and abs(value) > 1:
            return value
    return None


def _enrich_financial_data(
    data: Dict[str, Any],
    source_text: str,
    tavily_client=None,
    company_name: str = "",
) -> Dict[str, Any]:
    enriched = _canonicalize_financial_data(data)
    income = enriched["income_statement"]
    balance = enriched["balance_sheet"]
    cash = enriched["cash_flow"]
    market = enriched["market_data"]

    text = source_text or ""

    if _coerce_number(income.get("revenue")) is None:
        revenue = _extract_revenue(text)
        if revenue is not None:
            income["revenue"] = revenue

    if _coerce_number(income.get("cost_of_goods_sold")) is None:
        cogs = _extract_cost_of_goods_sold(text)
        if cogs is not None:
            income["cost_of_goods_sold"] = cogs

    if _coerce_number(income.get("operating_income")) is None:
        operating_income = _extract_operating_income(text)
        if operating_income is not None:
            income["operating_income"] = operating_income

    _fill_financials_from_sec_companyfacts(
        income,
        balance,
        cash,
        market,
        company_name=company_name,
        source_text=text,
    )
    _fill_income_fields_from_tavily(income, company_name, tavily_client)

    if _coerce_number(income.get("ebit")) is None and _coerce_number(income.get("operating_income")) is not None:
        income["ebit"] = _coerce_number(income.get("operating_income"))

    if _coerce_number(income.get("interest_expense")) is None:
        interest = _extract_interest_expense(text)
        if interest is not None:
            income["interest_expense"] = interest

    if _coerce_number(income.get("ebitda")) is None:
        ebit = _coerce_number(income.get("ebit"))
        if ebit is None:
            ebit = _coerce_number(income.get("operating_income"))
        dep_amort = _extract_depreciation_amortization(text)
        if ebit is not None and dep_amort is not None:
            income["ebitda"] = ebit + dep_amort

    if _coerce_number(balance.get("shareholders_equity")) is None:
        equity = _extract_shareholders_equity(text)
        if equity is not None:
            balance["shareholders_equity"] = equity

    if _coerce_number(balance.get("total_debt")) is None:
        total_debt = _extract_term_debt_total(text)
        if total_debt is not None:
            balance["total_debt"] = total_debt

    if _coerce_number(cash.get("financing_cash_flow")) is None:
        financing_cf = _extract_financing_cash_flow(text)
        if financing_cf is None:
            beginning_cash, ending_cash = _extract_cash_begin_end_balances(text)
            operating_cf = _coerce_number(cash.get("operating_cash_flow"))
            investing_cf = _coerce_number(cash.get("investing_cash_flow"))
            if (
                beginning_cash is not None
                and ending_cash is not None
                and operating_cf is not None
                and investing_cf is not None
            ):
                financing_cf = ending_cash - beginning_cash - operating_cf - investing_cf
        if financing_cf is None:
            financing_cf = _fill_financing_cash_flow_from_tavily(company_name, tavily_client)
        if financing_cf is not None:
            cash["financing_cash_flow"] = financing_cf

    if _coerce_number(market.get("share_price")) is None:
        share_price = _extract_share_price(text)
        if share_price is None:
            market_cap = _extract_market_cap(text)
            shares = _coerce_number(market.get("shares_outstanding"))
            if market_cap is not None and shares and shares > 0:
                estimate = market_cap / shares
                if estimate > 5000:
                    estimate = market_cap / (shares * 1000)
                if 0 < estimate < 10000:
                    share_price = estimate
        if share_price is None:
            share_price = _fill_share_price_from_tavily(company_name, tavily_client)
        if share_price is not None:
            market["share_price"] = share_price

    if _coerce_number(market.get("earnings_growth_rate")) is None:
        earnings_growth = _extract_earnings_growth_rate(text)
        if earnings_growth is not None:
            market["earnings_growth_rate"] = earnings_growth

    return enriched


def _metric_value(data: Dict[str, Any], section: str, field: str) -> float:
    section_data = data.get(section, {}) or {}
    return _coerce_number(section_data.get(field))


def _set_metric_unavailable(
    metrics: Dict[str, Any],
    notes: List[str],
    category: str,
    metric: str,
    reasons: List[str],
) -> None:
    if category in metrics and metric in metrics[category]:
        metrics[category][metric] = None
    if reasons:
        notes.append(f"{category}.{metric} 缺少 {', '.join(reasons)}，未计算")


def _apply_metric_quality_gate(metrics: Dict[str, Any], normalized: Dict[str, Any]) -> List[str]:
    notes: List[str] = []

    net_income = _metric_value(normalized, "income_statement", "net_income")
    revenue = _metric_value(normalized, "income_statement", "revenue")
    cogs = _metric_value(normalized, "income_statement", "cost_of_goods_sold")
    operating_income = _metric_value(normalized, "income_statement", "operating_income")
    ebit = _metric_value(normalized, "income_statement", "ebit")
    interest_expense = _metric_value(normalized, "income_statement", "interest_expense")
    ebitda = _metric_value(normalized, "income_statement", "ebitda")

    total_assets = _metric_value(normalized, "balance_sheet", "total_assets")
    current_assets = _metric_value(normalized, "balance_sheet", "current_assets")
    inventory = _metric_value(normalized, "balance_sheet", "inventory")
    cash_and_eq = _metric_value(normalized, "balance_sheet", "cash_and_equivalents")
    current_liabilities = _metric_value(normalized, "balance_sheet", "current_liabilities")
    equity = _metric_value(normalized, "balance_sheet", "shareholders_equity")
    total_debt = _metric_value(normalized, "balance_sheet", "total_debt")
    receivables = _metric_value(normalized, "balance_sheet", "accounts_receivable")

    share_price = _metric_value(normalized, "market_data", "share_price")
    shares = _metric_value(normalized, "market_data", "shares_outstanding")
    earnings_growth = _metric_value(normalized, "market_data", "earnings_growth_rate")

    if net_income is None or equity in (None, 0):
        reasons = []
        if net_income is None:
            reasons.append("income_statement.net_income")
        if equity is None:
            reasons.append("balance_sheet.shareholders_equity")
        elif equity == 0:
            reasons.append("balance_sheet.shareholders_equity=0")
        _set_metric_unavailable(metrics, notes, "profitability", "roe", reasons)

    if net_income is None or total_assets in (None, 0):
        reasons = []
        if net_income is None:
            reasons.append("income_statement.net_income")
        if total_assets is None:
            reasons.append("balance_sheet.total_assets")
        elif total_assets == 0:
            reasons.append("balance_sheet.total_assets=0")
        _set_metric_unavailable(metrics, notes, "profitability", "roa", reasons)

    if revenue in (None, 0) or cogs is None:
        reasons = []
        if revenue is None:
            reasons.append("income_statement.revenue")
        elif revenue == 0:
            reasons.append("income_statement.revenue=0")
        if cogs is None:
            reasons.append("income_statement.cost_of_goods_sold")
        _set_metric_unavailable(metrics, notes, "profitability", "gross_margin", reasons)

    if revenue in (None, 0) or operating_income is None:
        reasons = []
        if revenue is None:
            reasons.append("income_statement.revenue")
        elif revenue == 0:
            reasons.append("income_statement.revenue=0")
        if operating_income is None:
            reasons.append("income_statement.operating_income")
        _set_metric_unavailable(metrics, notes, "profitability", "operating_margin", reasons)

    if revenue in (None, 0) or net_income is None:
        reasons = []
        if revenue is None:
            reasons.append("income_statement.revenue")
        elif revenue == 0:
            reasons.append("income_statement.revenue=0")
        if net_income is None:
            reasons.append("income_statement.net_income")
        _set_metric_unavailable(metrics, notes, "profitability", "net_margin", reasons)

    if current_assets is None or current_liabilities in (None, 0):
        reasons = []
        if current_assets is None:
            reasons.append("balance_sheet.current_assets")
        if current_liabilities is None:
            reasons.append("balance_sheet.current_liabilities")
        elif current_liabilities == 0:
            reasons.append("balance_sheet.current_liabilities=0")
        _set_metric_unavailable(metrics, notes, "liquidity", "current_ratio", reasons)

    if current_assets is None or inventory is None or current_liabilities in (None, 0):
        reasons = []
        if current_assets is None:
            reasons.append("balance_sheet.current_assets")
        if inventory is None:
            reasons.append("balance_sheet.inventory")
        if current_liabilities is None:
            reasons.append("balance_sheet.current_liabilities")
        elif current_liabilities == 0:
            reasons.append("balance_sheet.current_liabilities=0")
        _set_metric_unavailable(metrics, notes, "liquidity", "quick_ratio", reasons)

    if cash_and_eq is None or current_liabilities in (None, 0):
        reasons = []
        if cash_and_eq is None:
            reasons.append("balance_sheet.cash_and_equivalents")
        if current_liabilities is None:
            reasons.append("balance_sheet.current_liabilities")
        elif current_liabilities == 0:
            reasons.append("balance_sheet.current_liabilities=0")
        _set_metric_unavailable(metrics, notes, "liquidity", "cash_ratio", reasons)

    if total_debt is None or equity in (None, 0):
        reasons = []
        if total_debt is None:
            reasons.append("balance_sheet.total_debt")
        if equity is None:
            reasons.append("balance_sheet.shareholders_equity")
        elif equity == 0:
            reasons.append("balance_sheet.shareholders_equity=0")
        _set_metric_unavailable(metrics, notes, "leverage", "debt_to_equity", reasons)

    if ebit is None or interest_expense in (None, 0):
        reasons = []
        if ebit is None:
            reasons.append("income_statement.ebit")
        if interest_expense is None:
            reasons.append("income_statement.interest_expense")
        elif interest_expense == 0:
            reasons.append("income_statement.interest_expense=0")
        _set_metric_unavailable(metrics, notes, "leverage", "interest_coverage", reasons)

    if operating_income is None or interest_expense in (None, 0):
        reasons = []
        if operating_income is None:
            reasons.append("income_statement.operating_income")
        if interest_expense is None:
            reasons.append("income_statement.interest_expense")
        elif interest_expense == 0:
            reasons.append("income_statement.interest_expense=0")
        _set_metric_unavailable(metrics, notes, "leverage", "debt_service_coverage", reasons)

    if revenue is None or total_assets in (None, 0):
        reasons = []
        if revenue is None:
            reasons.append("income_statement.revenue")
        if total_assets is None:
            reasons.append("balance_sheet.total_assets")
        elif total_assets == 0:
            reasons.append("balance_sheet.total_assets=0")
        _set_metric_unavailable(metrics, notes, "efficiency", "asset_turnover", reasons)

    if cogs is None or inventory in (None, 0):
        reasons = []
        if cogs is None:
            reasons.append("income_statement.cost_of_goods_sold")
        if inventory is None:
            reasons.append("balance_sheet.inventory")
        elif inventory == 0:
            reasons.append("balance_sheet.inventory=0")
        _set_metric_unavailable(metrics, notes, "efficiency", "inventory_turnover", reasons)

    if revenue is None or receivables in (None, 0):
        reasons = []
        if revenue is None:
            reasons.append("income_statement.revenue")
        if receivables is None:
            reasons.append("balance_sheet.accounts_receivable")
        elif receivables == 0:
            reasons.append("balance_sheet.accounts_receivable=0")
        _set_metric_unavailable(metrics, notes, "efficiency", "receivables_turnover", reasons)

    receivables_turnover = ((metrics.get("efficiency", {}) or {}).get("receivables_turnover"))
    if receivables_turnover in (None, 0):
        reasons = []
        if receivables_turnover is None:
            reasons.append("efficiency.receivables_turnover")
        elif receivables_turnover == 0:
            reasons.append("efficiency.receivables_turnover=0")
        _set_metric_unavailable(metrics, notes, "efficiency", "days_sales_outstanding", reasons)

    if net_income is None or shares in (None, 0):
        reasons = []
        if net_income is None:
            reasons.append("income_statement.net_income")
        if shares is None:
            reasons.append("market_data.shares_outstanding")
        elif shares == 0:
            reasons.append("market_data.shares_outstanding=0")
        _set_metric_unavailable(metrics, notes, "valuation", "eps", reasons)

    eps = ((metrics.get("valuation", {}) or {}).get("eps"))
    if share_price is None or eps in (None, 0):
        reasons = []
        if share_price is None:
            reasons.append("market_data.share_price")
        if eps is None:
            reasons.append("valuation.eps")
        elif eps == 0:
            reasons.append("valuation.eps=0")
        _set_metric_unavailable(metrics, notes, "valuation", "pe_ratio", reasons)

    if equity is None or shares in (None, 0):
        reasons = []
        if equity is None:
            reasons.append("balance_sheet.shareholders_equity")
        if shares is None:
            reasons.append("market_data.shares_outstanding")
        elif shares == 0:
            reasons.append("market_data.shares_outstanding=0")
        _set_metric_unavailable(metrics, notes, "valuation", "book_value_per_share", reasons)

    book_value_per_share = ((metrics.get("valuation", {}) or {}).get("book_value_per_share"))
    if share_price is None or book_value_per_share in (None, 0):
        reasons = []
        if share_price is None:
            reasons.append("market_data.share_price")
        if book_value_per_share is None:
            reasons.append("valuation.book_value_per_share")
        elif book_value_per_share == 0:
            reasons.append("valuation.book_value_per_share=0")
        _set_metric_unavailable(metrics, notes, "valuation", "pb_ratio", reasons)

    if share_price is None or shares in (None, 0) or revenue in (None, 0):
        reasons = []
        if share_price is None:
            reasons.append("market_data.share_price")
        if shares is None:
            reasons.append("market_data.shares_outstanding")
        elif shares == 0:
            reasons.append("market_data.shares_outstanding=0")
        if revenue is None:
            reasons.append("income_statement.revenue")
        elif revenue == 0:
            reasons.append("income_statement.revenue=0")
        _set_metric_unavailable(metrics, notes, "valuation", "ps_ratio", reasons)

    if share_price is None or shares in (None, 0) or total_debt is None or cash_and_eq is None or ebitda in (None, 0):
        reasons = []
        if share_price is None:
            reasons.append("market_data.share_price")
        if shares is None:
            reasons.append("market_data.shares_outstanding")
        elif shares == 0:
            reasons.append("market_data.shares_outstanding=0")
        if total_debt is None:
            reasons.append("balance_sheet.total_debt")
        if cash_and_eq is None:
            reasons.append("balance_sheet.cash_and_equivalents")
        if ebitda is None:
            reasons.append("income_statement.ebitda")
        elif ebitda == 0:
            reasons.append("income_statement.ebitda=0")
        _set_metric_unavailable(metrics, notes, "valuation", "ev_to_ebitda", reasons)

    pe_ratio = ((metrics.get("valuation", {}) or {}).get("pe_ratio"))
    if pe_ratio is None or earnings_growth in (None, 0):
        reasons = []
        if pe_ratio is None:
            reasons.append("valuation.pe_ratio")
        if earnings_growth is None:
            reasons.append("market_data.earnings_growth_rate")
        elif earnings_growth == 0:
            reasons.append("market_data.earnings_growth_rate=0")
        _set_metric_unavailable(metrics, notes, "valuation", "peg_ratio", reasons)

    return notes


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
                notes.append(f"{section}.{key} 未披露")
            else:
                normalized[section][key] = num
    return normalized, notes


def compute_financial_metrics(financial_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    normalized, notes = normalize_financial_data(financial_data)
    ratio_cls = _load_ratio_calculator()
    calculator = ratio_cls(normalized)
    metrics = calculator.calculate_all_ratios()
    quality_notes = _apply_metric_quality_gate(metrics, normalized)
    notes.extend(quality_notes)
    return metrics, notes
