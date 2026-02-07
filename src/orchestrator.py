import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from .pdf_loader import (
    extract_pdf_text_chunks,
    extract_financial_statement_text,
    score_financial_text,
    extract_company_name,
    extract_revenue_context,
    extract_context_text,
    score_revenue_text,
    score_context_text,
)
from .workpaper import (
    build_workpaper_from_text,
    react_enrich_workpaper,
    apply_company_profile_hint,
    build_context_pack,
    build_context_capsule,
    sanitize_company_scope_fields,
)
from .financials import extract_financials_with_fallback
from .summarizer import summarize_text
from .agents import run_agent
from .run_logger import log_step


FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_risk_level": {"type": "string"},
        "accepted_points": {"type": "array", "items": {"type": "string"}},
        "rejected_points": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "uncertainty": {"type": "string"},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "overall_risk_level",
        "accepted_points",
        "rejected_points",
        "rationale",
        "uncertainty",
        "suggestions",
    ],
}


def run_pipeline(
    input_texts: Optional[List[str]],
    pdf_paths: Optional[List[str]],
    llm,
    output_dir: Path,
    enable_defense: bool = True,
    tavily_client=None,
) -> Dict[str, Any]:
    if not input_texts and not pdf_paths:
        raise ValueError("input_texts or pdf_paths required")

    texts: List[str] = []
    financial_text = ""
    revenue_text = ""
    context_text = ""
    financial_score = 0
    revenue_score = 0
    context_score = 0
    if pdf_paths:
        for path in pdf_paths:
            chunks = extract_pdf_text_chunks(path)
            texts.extend([c["text"] for c in chunks])
            candidate = extract_financial_statement_text(chunks)
            score = score_financial_text(candidate)
            if score > financial_score:
                financial_text = candidate
                financial_score = score
            revenue_candidate = extract_revenue_context(chunks)
            revenue_score_candidate = score_revenue_text(revenue_candidate)
            if revenue_score_candidate > revenue_score:
                revenue_text = revenue_candidate
                revenue_score = revenue_score_candidate
            context_candidate = extract_context_text(chunks)
            context_score_candidate = score_context_text(context_candidate)
            if context_score_candidate > context_score:
                context_text = context_candidate
                context_score = context_score_candidate
    if input_texts:
        texts.extend(input_texts)
        if not financial_text:
            financial_text = "\n".join(input_texts)
        if not revenue_text:
            revenue_text = "\n".join(input_texts)
        if not context_text:
            context_text = "\n".join(input_texts)

    combined_text = "\n".join(texts)
    summary_text = summarize_text(combined_text, llm, chunk_size=4000, max_chunks=2)
    log_step(output_dir, "summary", {"summary": summary_text})
    company_name = extract_company_name(combined_text)
    if company_name:
        log_step(output_dir, "company_profile_hint", {"company_profile": company_name})
    financial_data = extract_financials_with_fallback(
        financial_text or combined_text,
        llm,
        enrichment_text=(financial_text or "") + "\n" + combined_text[:12000],
        tavily_client=tavily_client,
        company_name=company_name,
    )
    log_step(output_dir, "financial_data", financial_data)
    context_source = context_text or summary_text
    context_pack = build_context_pack(context_source, llm, company_name=company_name)
    context_capsule = build_context_capsule(context_pack)
    log_step(output_dir, "context_pack", context_pack)
    workpaper = build_workpaper_from_text(
        summary_text,
        llm,
        tavily_client=tavily_client,
        financial_data=financial_data,
        company_name=company_name,
        revenue_context=revenue_text,
    )
    workpaper = apply_company_profile_hint(workpaper, company_name)
    workpaper["context_pack"] = context_pack
    workpaper["context_capsule"] = context_capsule
    workpaper = sanitize_company_scope_fields(workpaper, company_name, llm)
    workpaper = react_enrich_workpaper(workpaper, llm, tavily_client=tavily_client)
    log_step(output_dir, "workpaper", workpaper)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent_reports").mkdir(parents=True, exist_ok=True)

    _write_json(output_dir / "workpaper.json", workpaper)

    reports: Dict[str, Dict[str, Any]] = {}
    for agent in [
        "base",
        "fraud_type_A",
        "fraud_type_B",
        "fraud_type_C",
        "fraud_type_D",
        "fraud_type_E",
        "fraud_type_F",
    ]:
        report = run_agent(
            agent,
            workpaper,
            llm,
            tavily_client=tavily_client,
            react_retry=True,
        )
        reports[agent] = report
        _write_json(output_dir / "agent_reports" / f"{agent}.json", report)
        log_step(output_dir, f"agent:{agent}", report)

    if enable_defense:
        defense_report = run_agent(
            "defense",
            workpaper,
            llm,
            tavily_client=tavily_client,
            react_retry=True,
        )
        reports["defense"] = defense_report
        _write_json(output_dir / "agent_reports" / "defense.json", defense_report)
        log_step(output_dir, "agent:defense", defense_report)

    final_report = llm.generate_json(
        "你是裁决分析智能体，负责综合判断舞弊风险等级。",
        f"以下是各智能体结论：\n{json.dumps(reports, ensure_ascii=False)}",
        FINAL_SCHEMA,
    )
    _write_json(output_dir / "final_report.json", final_report)
    log_step(output_dir, "final_report", final_report)
    return final_report


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
