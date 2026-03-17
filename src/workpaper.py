import logging
import re
from typing import Any

from .financials import compute_financial_metrics, extract_financial_statements
from .token_utils import truncate_json_for_prompt

MAX_INPUT_CHARS = 60000
MAX_CONTEXT_PACK_INPUT_CHARS = 18000
MAX_REVENUE_CONTEXT_CHARS = 12000

WORKPAPER_SCHEMA = {
    "type": "object",
    "properties": {
        "company_profile": {"type": "string"},
        "financial_summary": {"type": "string"},
        "risk_disclosures": {"type": "string"},
        "major_events": {"type": "string"},
        "governance_signals": {"type": "string"},
        "industry_comparables": {"type": "string"},
        "announcements_summary": {"type": "string"},
        "related_parties_summary": {"type": "string"},
        "industry_benchmark_summary": {"type": "string"},
        "external_search_summary": {"type": "string"},
        "financial_metrics": {"type": "object"},
        "metrics_notes": {"type": "array", "items": {"type": "string"}},
        "context_pack": {"type": "object"},
        "context_capsule": {"type": "string"},
        "fraud_type_A_block": {"type": "string"},
        "fraud_type_B_block": {"type": "string"},
        "fraud_type_C_block": {"type": "string"},
        "fraud_type_D_block": {"type": "string"},
        "fraud_type_E_block": {"type": "string"},
        "fraud_type_F_block": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["quote", "source"],
            },
        },
    },
    "required": [
        "company_profile",
        "financial_summary",
        "risk_disclosures",
        "major_events",
        "governance_signals",
        "industry_comparables",
        "announcements_summary",
        "related_parties_summary",
        "industry_benchmark_summary",
        "external_search_summary",
        "financial_metrics",
        "metrics_notes",
        "context_pack",
        "context_capsule",
        "fraud_type_A_block",
        "fraud_type_B_block",
        "fraud_type_C_block",
        "fraud_type_D_block",
        "fraud_type_E_block",
        "fraud_type_F_block",
    ],
}


def build_workpaper_from_text(
    text: str,
    llm,
    tavily_client=None,
    financial_data=None,
    company_name: str = "",
    revenue_context: str = "",
) -> dict[str, Any]:
    system_prompt = "你是财务舞弊识别专家，负责构建结构化多维信息工作底稿。"
    text = _fit_text_for_prompt(text, MAX_INPUT_CHARS)
    revenue_context = _fit_text_for_prompt(revenue_context, MAX_REVENUE_CONTEXT_CHARS)
    company_hint = f"目标公司：{company_name}\n" if company_name else ""
    revenue_block = f"收入/分部信息补充：\n{revenue_context}\n\n" if revenue_context else ""
    user_prompt = (
        "请根据以下文本构建结构化工作底稿，保证字段完整，并提取关键证据片段。"
        "除财务/治理/风险摘要外，需补充公告、关联方、行业对标与外部检索摘要。"
        "仅围绕目标公司，不得引用其他公司案例；行业信息仅描述行业概况，不出现其他公司名称。\n\n"
        f"{company_hint}"
        f"{revenue_block}"
        f"文本内容：\n{text}\n"
    )
    if tavily_client and getattr(tavily_client, "enabled", False):
        query_company = company_name or "目标公司"
        results = tavily_client.search(f"{query_company} 年报 业务概况 风险提示", max_results=5)
        results = filter_external_results_by_company(results, query_company)
        if results:
            lines = []
            for item in results:
                title = item.get("title", "")
                url = item.get("url", "")
                snippet = item.get("content", "")
                lines.append(f"- {title} | {snippet} ({url})")
            user_prompt += "\n\n外部检索摘要(供参考)：\n" + "\n".join(lines)
    if financial_data is None:
        financial_data = extract_financial_statements(text, llm)
    metrics, notes = compute_financial_metrics(financial_data)

    user_prompt += (
        "\n\n已计算的财务指标（供参考，请纳入底稿）：\n"
        f"{metrics}\n"
        "\n指标缺失说明：\n"
        f"{notes}\n"
    )

    workpaper = llm.generate_json(system_prompt, user_prompt, WORKPAPER_SCHEMA)
    if not isinstance(workpaper.get("financial_metrics"), dict) or not workpaper.get("financial_metrics"):
        workpaper["financial_metrics"] = metrics
    if not isinstance(workpaper.get("metrics_notes"), list):
        workpaper["metrics_notes"] = notes
    return workpaper


CONTEXT_PACK_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "business_overview": {"type": "string"},
        "segments": {"type": "string"},
        "geographies": {"type": "string"},
        "revenue_mix": {"type": "string"},
        "major_products": {"type": "string"},
        "key_accounting_policies": {"type": "string"},
        "top_risk_factors": {"type": "string"},
        "governance_overview": {"type": "string"},
        "audit_controls": {"type": "string"},
    },
    "required": [
        "company_name",
        "business_overview",
        "segments",
        "geographies",
        "revenue_mix",
        "major_products",
        "key_accounting_policies",
        "top_risk_factors",
        "governance_overview",
        "audit_controls",
    ],
}


ENRICHABLE_WORKPAPER_FIELDS = [
    "company_profile",
    "industry_comparables",
    "industry_benchmark_summary",
    "external_search_summary",
]

WORKPAPER_RESEARCH_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "need_autonomous_research": {"type": "boolean"},
        "minimum_rounds": {"type": "integer"},
        "target_fields": {"type": "array", "items": {"type": "string"}},
        "follow_up_queries": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": [
        "need_autonomous_research",
        "minimum_rounds",
        "target_fields",
        "follow_up_queries",
        "reason",
    ],
}

MAX_WORKPAPER_RESEARCH_ROUNDS = 2


def react_enrich_workpaper(
    workpaper: dict[str, Any],
    llm,
    tavily_client=None,
    max_retries: int = 2,
) -> dict[str, Any]:
    if getattr(llm, "_responses", None) is not None:
        return workpaper
    if not (tavily_client and getattr(tavily_client, "enabled", False)):
        return workpaper

    seen_queries = set()
    attempts = 0
    required_min_rounds = 0
    max_rounds = max(min(max_retries, MAX_WORKPAPER_RESEARCH_ROUNDS), 1)

    while attempts < max_rounds:
        try:
            plan = _request_workpaper_research_plan(workpaper, llm, attempts)
            required_min_rounds = max(required_min_rounds, plan["minimum_rounds"])
            continue_research = plan["need_autonomous_research"] or attempts < required_min_rounds
            if not continue_research:
                break

            company = (
                workpaper.get("company_profile")
                or workpaper.get("context_pack", {}).get("company_name")
                or "目标公司"
            )
            target_fields = _normalize_target_fields(plan.get("target_fields", []))
            if not target_fields and plan["need_autonomous_research"]:
                target_fields = ENRICHABLE_WORKPAPER_FIELDS[:]

            queries = _build_workpaper_research_queries(company, plan, attempts)
            new_queries = [q for q in queries if q not in seen_queries]
            external_results: list[dict[str, Any]] = []
            for query in new_queries:
                seen_queries.add(query)
                external_results.extend(tavily_client.search(query, max_results=5))
            external_results = filter_external_results_by_company(external_results, company)

            if external_results and target_fields:
                schema = {"type": "object", "properties": {}, "required": []}
                for field in target_fields:
                    schema["properties"][field] = {"type": "string"}
                    schema["required"].append(field)

                lines: list[str] = []
                for item in external_results:
                    title = item.get("title", "")
                    url = item.get("url", "")
                    snippet = item.get("content", "")
                    lines.append(f"- {title} | {snippet} ({url})")

                # Only send target fields + company_profile, not entire workpaper
                context_subset = {k: workpaper.get(k, "") for k in target_fields}
                context_subset["company_profile"] = workpaper.get("company_profile", "")
                context_json = truncate_json_for_prompt(context_subset, max_tokens=8000)

                system_prompt = "你是企业信息补全专家，基于检索结果补全工作底稿缺失字段。"
                user_prompt = (
                    "请根据外部检索结果补全指定字段，保证简洁、可审计且仅输出目标字段。\n"
                    f"补全字段：{', '.join(target_fields)}\n\n"
                    f"当前底稿摘要：\n{context_json}\n\n"
                    "外部检索摘要：\n"
                    + ("\n".join(lines) if lines else "无外部检索结果")
                )

                filled = llm.generate_json(system_prompt, user_prompt, schema)
                for field, value in filled.items():
                    if field in target_fields:
                        workpaper[field] = value
                workpaper["_react_search"] = external_results

            attempts += 1
        except Exception as exc:
            logging.warning("Workpaper enrichment round %d failed: %s", attempts, exc)
            attempts += 1
            break

    return workpaper


def _request_workpaper_research_plan(workpaper: dict[str, Any], llm, attempts: int) -> dict[str, Any]:
    system_prompt = "你是工作底稿完整性审计智能体，负责决定是否需要继续自主外部调查。"
    workpaper_json = truncate_json_for_prompt(workpaper, max_tokens=20000)
    user_prompt = (
        "请先判断工作底稿当前完整性，再给出research_plan。\n"
        "要求：\n"
        "1) need_autonomous_research: 是否继续调查；\n"
        "2) minimum_rounds: 建议最少调查轮次(0-2)；\n"
        f"3) target_fields: 仅可从 {ENRICHABLE_WORKPAPER_FIELDS} 中选择；\n"
        "4) follow_up_queries: 给出可执行检索语句；\n"
        "5) reason: 说明理由。\n\n"
        f"当前已完成轮次：{attempts}\n"
        f"当前工作底稿：\n{workpaper_json}\n"
    )
    plan_raw = llm.generate_json(system_prompt, user_prompt, WORKPAPER_RESEARCH_PLAN_SCHEMA)
    return _normalize_workpaper_research_plan(plan_raw)


def _normalize_workpaper_research_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {
            "need_autonomous_research": False,
            "minimum_rounds": 0,
            "target_fields": [],
            "follow_up_queries": [],
            "reason": "invalid_plan",
        }
    need_research = bool(plan.get("need_autonomous_research"))
    minimum_rounds = _normalize_workpaper_rounds(plan.get("minimum_rounds"))
    target_fields = _normalize_target_fields(plan.get("target_fields", []))
    follow_up_queries = []
    seen = set()
    for query in plan.get("follow_up_queries") or []:
        text = str(query).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        follow_up_queries.append(text)
    reason = str(plan.get("reason", "")).strip()
    return {
        "need_autonomous_research": need_research,
        "minimum_rounds": minimum_rounds,
        "target_fields": target_fields,
        "follow_up_queries": follow_up_queries[:5],
        "reason": reason,
    }


def _normalize_target_fields(fields: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for field in fields or []:
        text = str(field).strip()
        if text in ENRICHABLE_WORKPAPER_FIELDS and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _normalize_workpaper_rounds(value: Any) -> int:
    try:
        rounds = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_WORKPAPER_RESEARCH_ROUNDS, rounds))


def _build_workpaper_research_queries(company: str, plan: dict[str, Any], attempt_index: int) -> list[str]:
    guardrail_queries = [
        f"{company} 年报 风险因素 财务附注 披露",
        f"{company} annual report filing footnote disclosure",
        f"{company} regulator enforcement investigation disclosure",
    ]
    queries = []
    queries.extend(plan.get("follow_up_queries", []))
    queries.append(guardrail_queries[attempt_index % len(guardrail_queries)])

    deduped = []
    seen = set()
    for query in queries:
        text = re.sub(r"\s+", " ", str(query).strip())
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped[:6]


def sanitize_company_scope_fields(workpaper: dict[str, Any], company_name: str, llm) -> dict[str, Any]:
    if not company_name:
        return workpaper
    if getattr(llm, "_responses", None) is not None:
        return workpaper

    fields = [
        "industry_comparables",
        "external_search_summary",
        "fraud_type_A_block",
        "fraud_type_B_block",
        "fraud_type_C_block",
        "fraud_type_D_block",
        "fraud_type_E_block",
        "fraud_type_F_block",
    ]
    schema = {"type": "object", "properties": {}, "required": []}
    for field in fields:
        schema["properties"][field] = {"type": "string"}
        schema["required"].append(field)

    payload = {field: workpaper.get(field, "") for field in fields}
    system_prompt = "你是合规审计助手，负责清理非目标公司的内容。"
    user_prompt = (
        "以下文本必须只针对目标公司，禁止出现任何其他公司名称或案例。"
        "如无法从目标公司披露中得到结论，请写“未披露”。\n\n"
        f"目标公司：{company_name}\n\n"
        f"待清理字段：\n{payload}\n"
    )
    cleaned = llm.generate_json(system_prompt, user_prompt, schema)
    for field, value in cleaned.items():
        workpaper[field] = value
    return workpaper


def filter_external_results_by_company(results: list[dict[str, Any]], company_name: str) -> list[dict[str, Any]]:
    tokens = _company_tokens(company_name)
    if not tokens:
        return results
    filtered = []
    for item in results:
        hay = " ".join(
            [
                str(item.get("title", "")),
                str(item.get("content", "")),
                str(item.get("url", "")),
            ]
        ).lower()
        if any(token in hay for token in tokens):
            filtered.append(item)
    return filtered or results


def _company_tokens(company_name: str) -> list[str]:
    if not company_name or company_name.strip() in {"目标公司", "公司"}:
        return []
    base = re.sub(r"[\W_]+", " ", company_name).strip().lower()
    tokens = [t for t in base.split() if t and t not in {"inc", "inc.", "corp", "corp.", "corporation", "ltd", "llc", "co", "company"}]
    if len(tokens) == 1:
        tokens.append(base)
    return list(dict.fromkeys(tokens))


def apply_company_profile_hint(workpaper: dict[str, Any], company_name: str) -> dict[str, Any]:
    if company_name and _is_missing_value(workpaper.get("company_profile")):
        workpaper["company_profile"] = company_name
    return workpaper


def build_context_pack(text: str, llm, company_name: str = "") -> dict[str, Any]:
    if getattr(llm, "_responses", None) is not None:
        return {
            "company_name": company_name or "",
            "business_overview": "",
            "segments": "",
            "geographies": "",
            "revenue_mix": "",
            "major_products": "",
            "key_accounting_policies": "",
            "top_risk_factors": "",
            "governance_overview": "",
            "audit_controls": "",
        }
    system_prompt = "你是上下文工程专家，负责从年报中提取公司背景上下文包。"
    fitted_text = _fit_text_for_prompt(text, MAX_CONTEXT_PACK_INPUT_CHARS)
    user_prompt = (
        "请从以下文本中提取公司背景与业务关键信息，填充context_pack。"
        "优先使用年报披露信息，保持简洁、可审计。\n\n"
        f"公司名提示：{company_name}\n\n"
        f"文本内容：\n{fitted_text}\n"
    )
    pack = llm.generate_json(system_prompt, user_prompt, CONTEXT_PACK_SCHEMA)
    if company_name and _is_missing_value(pack.get("company_name")):
        pack["company_name"] = company_name
    return pack


def build_context_capsule(pack: dict[str, Any]) -> str:
    return (
        "背景要点：\n"
        f"- 公司：{pack.get('company_name','')}\n"
        f"- 业务概览：{pack.get('business_overview','')}\n"
        f"- 业务分部：{pack.get('segments','')}\n"
        f"- 地域分布：{pack.get('geographies','')}\n"
        f"- 收入结构：{pack.get('revenue_mix','')}\n"
        f"- 主要产品/服务：{pack.get('major_products','')}\n"
        f"- 关键会计政策：{pack.get('key_accounting_policies','')}\n"
        f"- 主要风险：{pack.get('top_risk_factors','')}\n"
        f"- 治理概览：{pack.get('governance_overview','')}\n"
        f"- 内控/审计：{pack.get('audit_controls','')}\n"
    )


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == ""


def _fit_text_for_prompt(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text

    # Preserve both head and tail sections to keep company profile and latest-period notes.
    split = max_chars // 2
    head = text[:split]
    tail = text[-(max_chars - split) :]
    return (
        head
        + "\n\n[... 中间内容已截断，保留首尾关键信息以控制上下文长度 ...]\n\n"
        + tail
    )
