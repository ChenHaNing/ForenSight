import io
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from tests.helpers.fake_llm import FakeLLM


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


def _build_minimal_odf(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "content.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<office:document-content>"
                f"<text:p>{text}</text:p>"
                "</office:document-content>"
            ),
        )
    return buffer.getvalue()


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


def test_api_run_requires_real_input_or_uploaded_report():
    from src.web_app import create_app

    app = create_app(llm_factory=lambda *_args, **_kwargs: FakeLLM(_build_fake_responses()))
    client = TestClient(app)

    resp = client.post(
        "/api/run?mode=sync",
        json={
            "enable_defense": True,
        },
    )
    assert resp.status_code == 400
    assert resp.json().get("detail") == "No input texts or uploaded report"


def test_index_does_not_show_sample_toggle():
    from src.web_app import create_app

    app = create_app(llm_factory=lambda *_args, **_kwargs: FakeLLM(_build_fake_responses()))
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "使用样本文档" not in resp.text


def test_frontend_report_visual_hooks_present():
    from src.web_app import create_app

    app = create_app(llm_factory=lambda *_args, **_kwargs: FakeLLM(_build_fake_responses()))
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert 'class="grid report-row"' in html
    assert 'class="risk-level-card"' in html
    assert html.count('class="label report-subtitle"') == 4
    assert html.count("summary-card") == 2

    root = Path(__file__).resolve().parents[1]
    css_text = (root / "static" / "styles.css").read_text(encoding="utf-8")
    assert ".report-grid li.is-rejected" in css_text
    assert ".summary-card .evidence-list .table-wrap" in css_text
    assert "overflow: hidden;" in css_text

    js_text = (root / "static" / "app.js").read_text(encoding="utf-8")
    assert "fillList(rejectedPointsEl, data.final_report?.rejected_points, 'is-rejected')" in js_text
    assert "function syncSummaryCardHeights()" in js_text
    assert "自主调查" in js_text
    assert "function formatReactAttempts" in js_text


def test_api_run_sync_uses_unique_output_dir_even_same_second(monkeypatch):
    from src import web_app

    fixed_time = 1_700_000_000.123
    monkeypatch.setattr(web_app.time, "time", lambda: fixed_time)

    def llm_factory(*_args, **_kwargs):
        return FakeLLM(_build_fake_responses())

    app = web_app.create_app(llm_factory=llm_factory)
    client = TestClient(app)

    first = client.post(
        "/api/run?mode=sync",
        json={"input_texts": ["sample text"], "enable_defense": True},
    )
    second = client.post(
        "/api/run?mode=sync",
        json={"input_texts": ["sample text"], "enable_defense": True},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_dir = first.json()["meta"]["output_dir"]
    second_dir = second.json()["meta"]["output_dir"]
    assert first_dir != second_dir


def test_run_pipeline_stream_prefers_highest_scored_financial_text(monkeypatch, tmp_path):
    from src import web_app

    captured = {}

    def fake_extract_pdf_text_chunks(path):
        return [{"text": path}]

    def fake_extract_financial_statement_text(chunks):
        text = chunks[0]["text"]
        if "strong" in text:
            return "Consolidated Statements of Operations\nNet income 100\nTotal assets 200"
        return "Financial highlights"

    def fake_extract_financials_with_fallback(text, llm, **_kwargs):
        captured["text"] = text
        return {
            "income_statement": {},
            "balance_sheet": {},
            "cash_flow": {},
            "market_data": {},
        }

    monkeypatch.setattr(web_app, "extract_pdf_text_chunks", fake_extract_pdf_text_chunks)
    monkeypatch.setattr(web_app, "extract_financial_statement_text", fake_extract_financial_statement_text)
    monkeypatch.setattr(web_app, "extract_financials_with_fallback", fake_extract_financials_with_fallback)
    monkeypatch.setattr(web_app, "extract_revenue_context", lambda *_args, **_kwargs: "revenue")
    monkeypatch.setattr(web_app, "extract_context_text", lambda *_args, **_kwargs: "context")
    monkeypatch.setattr(web_app, "score_financial_text", lambda text: 100 if "Consolidated Statements of Operations" in text else 1, raising=False)
    monkeypatch.setattr(web_app, "score_revenue_text", lambda *_args, **_kwargs: 1, raising=False)
    monkeypatch.setattr(web_app, "score_context_text", lambda *_args, **_kwargs: 1, raising=False)
    monkeypatch.setattr(web_app, "summarize_text", lambda *_args, **_kwargs: "summary")
    monkeypatch.setattr(web_app, "extract_company_name", lambda *_args, **_kwargs: "Example Co.")
    monkeypatch.setattr(web_app, "build_context_pack", lambda *_args, **_kwargs: {"company_name": "Example Co."})
    monkeypatch.setattr(web_app, "build_context_capsule", lambda *_args, **_kwargs: "capsule")
    monkeypatch.setattr(web_app, "build_workpaper_from_text", lambda *_args, **_kwargs: {"company_profile": "Example Co."})
    monkeypatch.setattr(web_app, "apply_company_profile_hint", lambda workpaper, *_args, **_kwargs: workpaper)
    monkeypatch.setattr(web_app, "sanitize_company_scope_fields", lambda workpaper, *_args, **_kwargs: workpaper)
    monkeypatch.setattr(web_app, "react_enrich_workpaper", lambda workpaper, *_args, **_kwargs: workpaper)
    monkeypatch.setattr(
        web_app,
        "run_agent",
        lambda *_args, **_kwargs: {
            "risk_level": "low",
            "risk_points": [],
            "evidence": [],
            "reasoning_summary": "",
            "suggestions": [],
            "confidence": 0.1,
        },
    )
    monkeypatch.setattr(web_app, "log_step", lambda *_args, **_kwargs: None)

    run_id = "run-score-test"
    with web_app.RUN_LOCK:
        web_app.RUNS[run_id] = {
            "status": "running",
            "step_outputs": {},
            "agent_reports": {},
            "final_report": None,
            "workpaper": None,
            "meta": {},
            "started_at": time.time(),
            "last_update": time.time(),
        }

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

    web_app._run_pipeline_stream(
        run_id=run_id,
        input_texts=None,
        pdf_paths=["weak.pdf", "strong.pdf"],
        llm=llm,
        output_dir=tmp_path / "out",
        enable_defense=False,
        tavily_client=None,
    )

    assert "Consolidated Statements of Operations" in captured["text"]


def test_upload_report_odf_can_be_used_for_sync_run():
    from src.web_app import create_app

    app = create_app(llm_factory=lambda *_args, **_kwargs: FakeLLM(_build_fake_responses()))
    client = TestClient(app)

    upload_resp = client.post(
        "/api/upload-report",
        files={
            "file": (
                "report.odf",
                _build_minimal_odf("Revenue grew with stable cash flow."),
                "application/vnd.oasis.opendocument.text",
            )
        },
    )
    assert upload_resp.status_code == 200
    upload_payload = upload_resp.json()
    assert upload_payload.get("report_id")

    run_resp = client.post(
        "/api/run?mode=sync",
        json={
            "uploaded_report_id": upload_payload["report_id"],
            "enable_defense": True,
        },
    )
    assert run_resp.status_code == 200
    payload = run_resp.json()
    assert payload["final_report"]["overall_risk_level"] == "medium"


def test_upload_report_rejects_unsupported_extension():
    from src.web_app import create_app

    app = create_app(llm_factory=lambda *_args, **_kwargs: FakeLLM(_build_fake_responses()))
    client = TestClient(app)

    resp = client.post(
        "/api/upload-report",
        files={"file": ("report.xlsx", b"fake", "application/octet-stream")},
    )
    assert resp.status_code == 400
