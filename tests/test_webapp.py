import time

from fastapi.testclient import TestClient

from src.llm_client import FakeLLM


def _build_fake_responses():
    return [
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


def test_api_run_returns_report_payload():
    llm = FakeLLM(_build_fake_responses())

    from src.web_app import create_app

    app = create_app(llm_factory=lambda *_args, **_kwargs: llm)
    client = TestClient(app)

    resp = client.post(
        "/api/run?mode=sync",
        json={
            "input_texts": ["sample text"],
            "enable_defense": True,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert "final_report" in payload
    assert payload["final_report"]["overall_risk_level"] == "medium"
    assert "agent_reports" in payload
    assert "workpaper" in payload
    assert "step_outputs" in payload
    assert "workpaper" in payload["step_outputs"]
    assert "base" in payload["step_outputs"]
    assert "fraud_type_A" in payload["step_outputs"]
    assert "fraud_type_B" in payload["step_outputs"]
    assert "fraud_type_C" in payload["step_outputs"]
    assert "fraud_type_D" in payload["step_outputs"]
    assert "fraud_type_E" in payload["step_outputs"]
    assert "fraud_type_F" in payload["step_outputs"]
    assert "defense" in payload["step_outputs"]
    assert "final" in payload["step_outputs"]
    assert payload["step_outputs"]["workpaper"]["company_profile"] == "Example Co."


def test_api_run_async_eventually_completes():
    from src import web_app

    with web_app.RUN_LOCK:
        web_app.RUNS.clear()

    llm = FakeLLM(_build_fake_responses())
    app = web_app.create_app(llm_factory=lambda *_args, **_kwargs: llm)
    client = TestClient(app)

    start_resp = client.post(
        "/api/run",
        json={
            "input_texts": ["sample text"],
            "enable_defense": True,
        },
    )
    assert start_resp.status_code == 200
    run_id = start_resp.json().get("run_id")
    assert run_id

    deadline = time.time() + 5
    last_payload = None
    while time.time() < deadline:
        status_resp = client.get("/api/status", params={"run_id": run_id})
        assert status_resp.status_code == 200
        last_payload = status_resp.json()
        if last_payload.get("status") in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert last_payload is not None
    assert last_payload.get("status") == "completed", last_payload.get("error")
    assert last_payload.get("final_report", {}).get("overall_risk_level") == "medium"
    assert "final" in last_payload.get("step_outputs", {})


def test_sample_pdf_paths_use_only_10k(tmp_path, monkeypatch):
    from src import web_app

    sample_10k = tmp_path / "aapl_10-K-2025-As-Filed.pdf"
    sample_10k.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(web_app, "SAMPLE_10K", sample_10k)

    paths, has_samples = web_app._get_sample_pdf_paths()

    assert has_samples is True
    assert paths == [str(sample_10k)]
