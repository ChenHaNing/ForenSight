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
    if AGENT_INPUT_FIELD[agent_name] == "all":
        content = workpaper
    else:
        key = AGENT_INPUT_FIELD[agent_name]
        content = workpaper.get(key, "")

    constraints = (
        "约束要求：\n"
        "1) 不得预设立场，仅基于证据判断。\n"
        "2) 若数据缺失，需明确标注缺失原因，不得臆测。\n"
        "3) 关注特征协同性，避免单点异常导致高风险。\n"
        "4) 输出风险点需对应具体证据。\n"
        "5) 若为关注类特征，需说明为何需要进一步核查。\n"
    )
    capsule = workpaper.get("context_capsule", "")
    capsule_block = f"背景要点（上下文胶囊）：\n{capsule}\n\n" if capsule else ""
    user_prompt = (
        "请基于输入内容生成结构化报告，必须引用证据并避免臆测。\n\n"
        f"{capsule_block}"
        f"{constraints}\n"
        f"输入内容：\n{content}\n"
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
    if external_results:
        report["_external_search"] = external_results

    if getattr(llm, "_responses", None) is not None:
        react_retry = False

    if react_retry and _needs_react_retry(report, workpaper) and tavily_client and getattr(tavily_client, "enabled", False):
        for _ in range(max_retries):
            retry_results = _build_react_retry_results(agent_name, workpaper, tavily_client)
            if company_name:
                retry_results = filter_external_results_by_company(retry_results, company_name)
            retry_prompt = user_prompt
            if retry_results:
                retry_prompt += "\n\n补充检索摘要：\n" + _format_external_results(retry_results)
            retry_report = llm.generate_json(system_prompt, retry_prompt, REPORT_SCHEMA)
            if retry_results:
                retry_report["_external_search"] = retry_results
            report = retry_report
            if not _needs_react_retry(report, workpaper):
                break
    return report


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


def _build_react_retry_results(agent_name: str, workpaper: Dict[str, Any], tavily_client) -> List[Dict[str, Any]]:
    company = workpaper.get("company_profile", "目标公司")
    focus = "财务 数据 缺失 补充"
    if _is_missing_value(workpaper.get("industry_comparables")):
        focus = "行业 对标 竞争对手"
    elif _is_missing_value(workpaper.get("company_profile")):
        focus = "公司简介 业务 概况"
    query = f"{company} {focus}"
    return tavily_client.search(query, max_results=5)


def _format_external_results(results: List[Dict[str, Any]]) -> str:
    lines = []
    for item in results:
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("content", "")
        lines.append(f"- {title} | {snippet} ({url})")
    return "\n".join(lines)


def _needs_react_retry(report: Dict[str, Any], workpaper: Dict[str, Any]) -> bool:
    evidence = report.get("evidence") or []
    if not evidence:
        return True
    risk_level = str(report.get("risk_level", "")).lower()
    if risk_level in {"unknown", "n/a"}:
        return True
    summary = str(report.get("reasoning_summary", ""))
    for marker in ["信息不足", "无法评估", "缺失", "未知"]:
        if marker in summary:
            return True
    if _is_missing_value(workpaper.get("industry_comparables")):
        return True
    return False


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    if len(text) < 10:
        return True
    for marker in ["缺失", "无法评估", "信息不足", "未知"]:
        if marker in text:
            return True
    return False
