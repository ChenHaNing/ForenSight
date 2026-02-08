import json
import re
from typing import Dict, Any, List
from .workpaper import filter_external_results_by_company


REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_level": {"type": "string"},
        "risk_points": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "reasoning_summary": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "research_plan": {
            "type": "object",
            "properties": {
                "need_autonomous_research": {"type": "boolean"},
                "minimum_rounds": {"type": "integer"},
                "follow_up_queries": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
            },
            "required": ["need_autonomous_research", "minimum_rounds", "follow_up_queries", "reason"],
        },
    },
    "required": [
        "risk_level",
        "risk_points",
        "evidence",
        "reasoning_summary",
        "suggestions",
        "confidence",
    ],
}


AGENT_PROMPTS = {
    "base": "你是基础舞弊风险识别智能体，评估整体风险。",
    "fraud_type_A": "你是虚构交易类收入舞弊智能体，聚焦收入虚构线索。",
    "fraud_type_B": "你是净利润操纵类舞弊智能体，聚焦利润操纵线索。",
    "fraud_type_C": "你是会计操纵类收入舞弊智能体，关注收入确认、会计政策变更异常。",
    "fraud_type_D": "你是净资产类舞弊智能体，关注资产减值、评估增值、资本结构异常。",
    "fraud_type_E": "你是资金占用舞弊智能体，关注资金往来、关联交易与资金回流。",
    "fraud_type_F": "你是特殊行业/业务模式舞弊智能体，关注行业特有风险与模式异常。",
    "defense": "你是辩护分析智能体，为风险点提供合理解释或反证。",
}


AGENT_INPUT_FIELD = {
    "base": "financial_summary",
    "fraud_type_A": "fraud_type_A_block",
    "fraud_type_B": "fraud_type_B_block",
    "fraud_type_C": "fraud_type_C_block",
    "fraud_type_D": "fraud_type_D_block",
    "fraud_type_E": "fraud_type_E_block",
    "fraud_type_F": "fraud_type_F_block",
    "defense": "all",
}


MAX_REACT_RETRY_ROUNDS = 4


def run_agent(
    agent_name: str,
    workpaper: Dict[str, Any],
    llm,
    tavily_client=None,
    react_retry: bool = False,
    max_retries: int = 1,
) -> Dict[str, Any]:
    if agent_name not in AGENT_PROMPTS:
        raise ValueError(f"Unknown agent: {agent_name}")

    system_prompt = AGENT_PROMPTS[agent_name]
    content = _build_agent_content(agent_name, workpaper)

    constraints = (
        "约束要求：\n"
        "1) 不得预设立场，仅基于证据判断。\n"
        "2) 若数据缺失，需明确标注缺失原因，不得臆测。\n"
        "3) 关注特征协同性，避免单点异常导致高风险。\n"
        "4) 输出风险点需对应具体证据。\n"
        "5) 若为关注类特征，需说明为何需要进一步核查。\n"
        "6) 必须给出research_plan：\n"
        "   - need_autonomous_research: 是否需要继续自主外部调查；\n"
        "   - minimum_rounds: 建议最少补充调查轮次(0-4)；\n"
        "   - follow_up_queries: 下一轮建议检索语句列表；\n"
        "   - reason: 判定理由。\n"
    )
    capsule = workpaper.get("context_capsule", "")
    capsule_block = f"背景要点（上下文胶囊）：\n{capsule}\n\n" if capsule else ""
    user_prompt = (
        "请基于输入内容生成结构化报告，必须引用证据并避免臆测。\n\n"
        f"{capsule_block}"
        f"{constraints}\n"
        f"输入内容：\n{json.dumps(content, ensure_ascii=False)}\n"
    )

    external_results = _build_external_results(agent_name, workpaper, tavily_client)
    company_name = workpaper.get("company_profile") or workpaper.get("context_pack", {}).get("company_name", "")
    if company_name:
        external_results = filter_external_results_by_company(external_results, company_name)
    if external_results:
        user_prompt += "\n\n外部检索摘要：\n" + _format_external_results(external_results)
    if capsule:
        user_prompt += "\n\n背景要点（提醒）：\n" + capsule

    report = llm.generate_json(system_prompt, user_prompt, REPORT_SCHEMA)
    react_attempts = 0
    if external_results:
        report["_external_search"] = external_results

    if getattr(llm, "_responses", None) is not None:
        react_retry = False

    tavily_enabled = bool(tavily_client and getattr(tavily_client, "enabled", False))
    policy = _extract_research_plan(report)
    should_retry = policy["need_autonomous_research"]
    required_min_rounds = max(max_retries if should_retry else 0, policy["minimum_rounds"])

    if react_retry and should_retry and tavily_enabled:
        while react_attempts < MAX_REACT_RETRY_ROUNDS and (
            react_attempts < required_min_rounds or policy["need_autonomous_research"]
        ):
            retry_results = _build_react_retry_results(agent_name, workpaper, report, tavily_client, attempt_index=react_attempts)
            if company_name:
                retry_results = filter_external_results_by_company(retry_results, company_name)
            retry_prompt = user_prompt
            if retry_results:
                retry_prompt += "\n\n补充检索摘要：\n" + _format_external_results(retry_results)
            retry_prompt += f"\n\n当前已完成自主调查轮次：{react_attempts + 1}"
            retry_report = llm.generate_json(system_prompt, retry_prompt, REPORT_SCHEMA)
            react_attempts += 1
            if retry_results:
                retry_report["_external_search"] = retry_results
            report = retry_report
            policy = _extract_research_plan(report)
            required_min_rounds = max(required_min_rounds, policy["minimum_rounds"])
            if react_attempts >= required_min_rounds and not policy["need_autonomous_research"]:
                break
    report["_react_attempts"] = react_attempts
    return report


def _build_agent_content(agent_name: str, workpaper: Dict[str, Any]) -> Dict[str, Any]:
    if AGENT_INPUT_FIELD[agent_name] == "all":
        return workpaper

    focus_key = AGENT_INPUT_FIELD[agent_name]
    return {
        "focus_block": workpaper.get(focus_key, ""),
        "financial_summary": workpaper.get("financial_summary", ""),
        "risk_disclosures": workpaper.get("risk_disclosures", ""),
        "major_events": workpaper.get("major_events", ""),
        "financial_metrics": workpaper.get("financial_metrics", {}),
        "metrics_notes": workpaper.get("metrics_notes", []),
        "context_capsule": workpaper.get("context_capsule", ""),
        "external_search_summary": workpaper.get("external_search_summary", ""),
    }


def _build_external_results(agent_name: str, workpaper: Dict[str, Any], tavily_client) -> List[Dict[str, Any]]:
    if not (tavily_client and getattr(tavily_client, "enabled", False)):
        return []
    company = workpaper.get("company_profile", "目标公司")
    query_focus = {
        "base": "财务舞弊 风险 信号",
        "fraud_type_A": "虚构交易 收入 舞弊",
        "fraud_type_B": "净利润 操纵 舞弊",
        "fraud_type_C": "会计政策 变更 收入确认 风险",
        "fraud_type_D": "资产减值 评估 资本结构 风险",
        "fraud_type_E": "资金占用 关联交易 风险",
        "fraud_type_F": "行业 特殊性 风险 模式异常",
        "defense": "行业 特殊性 合理解释",
    }.get(agent_name, "财务舞弊 风险")
    query = f"{company} {query_focus}"
    return tavily_client.search(query, max_results=5)


def _build_react_retry_results(
    agent_name: str,
    workpaper: Dict[str, Any],
    report: Dict[str, Any],
    tavily_client,
    attempt_index: int = 0,
) -> List[Dict[str, Any]]:
    company = workpaper.get("company_profile", "目标公司")
    queries = _build_retry_queries(
        agent_name,
        company,
        workpaper,
        report,
        attempt_index=attempt_index,
    )
    results: List[Dict[str, Any]] = []
    for query in queries:
        results.extend(tavily_client.search(query, max_results=4))
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in results:
        key = (str(item.get("url", "")), str(item.get("title", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:8]


def _build_retry_queries(
    agent_name: str,
    company: str,
    workpaper: Dict[str, Any],
    report: Dict[str, Any],
    attempt_index: int = 0,
) -> List[str]:
    base_focus = {
        "base": "财务舞弊 风险 信号",
        "fraud_type_A": "收入确认 虚构交易 财务舞弊",
        "fraud_type_B": "净利润操纵 存货减值 应计费用",
        "fraud_type_C": "会计政策 变更 收入确认 异常",
        "fraud_type_D": "资产减值 商誉减值 估值假设",
        "fraud_type_E": "资金占用 关联交易 资金回流",
        "fraud_type_F": "行业模式 风险信号",
        "defense": "风险事项 合理解释 反证",
    }.get(agent_name, "财务风险")

    queries = [f"{company} {base_focus}"]
    queries.extend(_model_suggested_queries(report))

    guardrail_queries = [
        f"{company} 年报 风险因素 管理层讨论 财务附注",
        f"{company} annual report filing footnote disclosure",
        f"{company} regulator enforcement investigation disclosure",
    ]
    queries.append(guardrail_queries[attempt_index % len(guardrail_queries)])

    deduped = []
    seen = set()
    for q in queries:
        normalized = re.sub(r"\s+", " ", q).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:6]


def _format_external_results(results: List[Dict[str, Any]]) -> str:
    lines = []
    for item in results:
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("content", "")
        lines.append(f"- {title} | {snippet} ({url})")
    return "\n".join(lines)


def _extract_research_plan(report: Dict[str, Any]) -> Dict[str, Any]:
    plan = report.get("research_plan")
    if isinstance(plan, dict):
        need_research = bool(plan.get("need_autonomous_research"))
        minimum_rounds = _normalize_rounds(plan.get("minimum_rounds"))
        follow_up_queries = []
        for query in plan.get("follow_up_queries") or []:
            text = str(query).strip()
            if text:
                follow_up_queries.append(text)
        reason = str(plan.get("reason", "")).strip()
        return {
            "need_autonomous_research": need_research,
            "minimum_rounds": minimum_rounds,
            "follow_up_queries": follow_up_queries[:4],
            "reason": reason,
        }

    # Backward-compatible fallback: if no plan is produced, use evidence sufficiency.
    evidence = report.get("evidence") or []
    needs_fallback_retry = len(evidence) == 0
    return {
        "need_autonomous_research": needs_fallback_retry,
        "minimum_rounds": 1 if needs_fallback_retry else 0,
        "follow_up_queries": [],
        "reason": "fallback_by_evidence",
    }


def _model_suggested_queries(report: Dict[str, Any]) -> List[str]:
    plan = _extract_research_plan(report)
    return plan.get("follow_up_queries", [])


def _normalize_rounds(value: Any) -> int:
    try:
        rounds = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(MAX_REACT_RETRY_ROUNDS, rounds))
