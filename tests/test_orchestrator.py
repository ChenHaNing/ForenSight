import json
import time
from src.orchestrator import run_pipeline
from tests.helpers.fake_llm import FakeLLM


def test_run_pipeline_writes_outputs(tmp_path):
    responses = [
        {"summary": "summary"},
        {
            "income_statement": {"revenue": 1000, "cost_of_goods_sold": 600, "net_income": 80},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        },
        {
            "income_statement": {},
            "balance_sheet": {"total_assets": 2000, "shareholders_equity": 900},
            "cash_flow": {},
            "market_data": {},
        },
        {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        },
        {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        },
        {
            "company_profile": "Example Co.",
            "financial_summary": "Summary",
            "risk_disclosures": "Risks",
            "major_events": "Events",
            "governance_signals": "Governance",
            "industry_comparables": "Peers",
            "announcements_summary": "Announcements",
            "related_parties_summary": "Related parties",
            "industry_benchmark_summary": "Benchmark",
            "external_search_summary": "External summary",
            "fraud_type_A_block": "A-block",
            "fraud_type_B_block": "B-block",
            "fraud_type_C_block": "C-block",
            "fraud_type_D_block": "D-block",
            "fraud_type_E_block": "E-block",
            "fraud_type_F_block": "F-block",
            "evidence": [{"quote": "Sample", "source": "p1"}],
        },
        {
            "risk_level": "medium",
            "risk_points": ["basePoint"],
            "evidence": ["baseEvidence"],
            "reasoning_summary": "baseSummary",
            "suggestions": ["baseSuggest"],
            "confidence": 0.7,
        },
        {
            "risk_level": "medium",
            "risk_points": ["pointA"],
            "evidence": ["evidenceA"],
            "reasoning_summary": "summaryA",
            "suggestions": ["suggestA"],
            "confidence": 0.6,
        },
        {
            "risk_level": "low",
            "risk_points": ["pointB"],
            "evidence": ["evidenceB"],
            "reasoning_summary": "summaryB",
            "suggestions": ["suggestB"],
            "confidence": 0.4,
        },
        {
            "risk_level": "low",
            "risk_points": ["pointC"],
            "evidence": ["evidenceC"],
            "reasoning_summary": "summaryC",
            "suggestions": ["suggestC"],
            "confidence": 0.4,
        },
        {
            "risk_level": "low",
            "risk_points": ["pointD"],
            "evidence": ["evidenceD"],
            "reasoning_summary": "summaryD",
            "suggestions": ["suggestD"],
            "confidence": 0.4,
        },
        {
            "risk_level": "low",
            "risk_points": ["pointE"],
            "evidence": ["evidenceE"],
            "reasoning_summary": "summaryE",
            "suggestions": ["suggestE"],
            "confidence": 0.4,
        },
        {
            "risk_level": "low",
            "risk_points": ["pointF"],
            "evidence": ["evidenceF"],
            "reasoning_summary": "summaryF",
            "suggestions": ["suggestF"],
            "confidence": 0.4,
        },
        {
            "risk_level": "low",
            "risk_points": ["defense"],
            "evidence": ["defenseEvidence"],
            "reasoning_summary": "defenseSummary",
            "suggestions": ["defenseSuggest"],
            "confidence": 0.5,
        },
        {
            "overall_risk_level": "medium",
            "accepted_points": ["pointA"],
            "rejected_points": ["pointB"],
            "rationale": "rationale",
            "uncertainty": "uncertainty",
            "suggestions": ["finalSuggestion"],
        },
    ]
    llm = FakeLLM(responses)

    final_report = run_pipeline(
        input_texts=["sample text"],
        pdf_paths=None,
        llm=llm,
        output_dir=tmp_path,
        enable_defense=True,
    )

    assert final_report["overall_risk_level"] == "medium"
    assert (tmp_path / "workpaper.json").exists()
    assert (tmp_path / "final_report.json").exists()
    agent_dir = tmp_path / "agent_reports"
    assert agent_dir.exists()
    reports = list(agent_dir.glob("*.json"))
    assert len(reports) >= 8

    with open(tmp_path / "final_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["overall_risk_level"] == "medium"
    log_path = tmp_path / "run.log"
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "\"step\": \"workpaper\"" in log_text
    assert "\"step\": \"final_report\"" in log_text


def test_run_pipeline_prefers_stronger_financial_text(monkeypatch, tmp_path):
    from src import orchestrator

    captured = {}

    def fake_extract_pdf_text_chunks(path):
        if "paper" in path:
            return [{"text": "Research paper discussing Revenue concepts."}]
        return [
            {
                "text": "Consolidated Statements of Operations\nNet income 100\nTotal assets 200"
            }
        ]

    def fake_extract_financials_with_fallback(text, llm, parallel=True, min_fields=4, **_kwargs):
        captured["text"] = text
        return {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        }

    def fake_build_workpaper_from_text(*_args, **_kwargs):
        return {"company_profile": "TestCo"}

    def fake_run_agents_suite(*_args, enable_defense=True, on_agent_result=None, **_kwargs):
        names = [
            "base",
            "fraud_type_A",
            "fraud_type_B",
            "fraud_type_C",
            "fraud_type_D",
            "fraud_type_E",
            "fraud_type_F",
        ]
        if enable_defense:
            names.append("defense")
        reports = {}
        for name in names:
            report = {
                "risk_level": "low",
                "risk_points": [],
                "evidence": [],
                "reasoning_summary": "",
                "suggestions": [],
                "confidence": 0.1,
            }
            reports[name] = report
            if on_agent_result:
                on_agent_result(name, report)
        return reports

    monkeypatch.setattr(orchestrator, "extract_pdf_text_chunks", fake_extract_pdf_text_chunks)
    monkeypatch.setattr(orchestrator, "extract_financials_with_fallback", fake_extract_financials_with_fallback)
    monkeypatch.setattr(orchestrator, "build_workpaper_from_text", fake_build_workpaper_from_text)
    monkeypatch.setattr(orchestrator, "run_agents_suite", fake_run_agents_suite)
    monkeypatch.setattr(orchestrator, "summarize_text", lambda *_args, **_kwargs: "summary")

    llm = FakeLLM(
        [
            {
                "overall_risk_level": "low",
                "accepted_points": [],
                "rejected_points": [],
                "rationale": "ok",
                "uncertainty": "low",
                "suggestions": [],
            }
        ]
    )

    orchestrator.run_pipeline(
        input_texts=None,
        pdf_paths=["paper.pdf", "10k.pdf"],
        llm=llm,
        output_dir=tmp_path,
        enable_defense=False,
    )

    assert "Consolidated Statements of Operations" in captured["text"]


def test_run_pipeline_parallelizes_agent_stage(monkeypatch, tmp_path):
    from src import orchestrator
    from src import agents as agents_module

    def fake_extract_financials_with_fallback(*_args, **_kwargs):
        return {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        }

    def fake_build_workpaper_from_text(*_args, **_kwargs):
        return {"company_profile": "Example Co."}

    def fake_run_agent(*_args, **_kwargs):
        time.sleep(0.12)
        return {
            "risk_level": "low",
            "risk_points": [],
            "evidence": [],
            "reasoning_summary": "",
            "suggestions": [],
            "confidence": 0.1,
        }

    monkeypatch.setattr(orchestrator, "summarize_text", lambda *_args, **_kwargs: "summary")
    monkeypatch.setattr(orchestrator, "extract_company_name", lambda *_args, **_kwargs: "Example Co.")
    monkeypatch.setattr(orchestrator, "extract_financials_with_fallback", fake_extract_financials_with_fallback)
    monkeypatch.setattr(orchestrator, "build_context_pack", lambda *_args, **_kwargs: {"company_name": "Example Co."})
    monkeypatch.setattr(orchestrator, "build_context_capsule", lambda *_args, **_kwargs: "capsule")
    monkeypatch.setattr(orchestrator, "build_workpaper_from_text", fake_build_workpaper_from_text)
    monkeypatch.setattr(orchestrator, "sanitize_company_scope_fields", lambda wp, *_args, **_kwargs: wp)
    monkeypatch.setattr(orchestrator, "react_enrich_workpaper", lambda wp, *_args, **_kwargs: wp)
    monkeypatch.setattr(agents_module, "run_agent", fake_run_agent)

    class FinalOnlyLLM:
        def generate_json(self, *_args, **_kwargs):
            return {
                "overall_risk_level": "low",
                "accepted_points": [],
                "rejected_points": [],
                "rationale": "ok",
                "uncertainty": "low",
                "suggestions": [],
            }

    start = time.perf_counter()
    orchestrator.run_pipeline(
        input_texts=["sample text"],
        pdf_paths=None,
        llm=FinalOnlyLLM(),
        output_dir=tmp_path,
        enable_defense=False,
    )
    elapsed = time.perf_counter() - start

    # 7 agents * 0.12s = 0.84s if strictly sequential.
    assert elapsed < 0.70
