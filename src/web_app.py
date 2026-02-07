import json
import time
import uuid
import threading
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import load_config
from .llm_client import LLMClient
from .orchestrator import run_pipeline
from .pdf_loader import extract_pdf_text_chunks, extract_financial_statement_text
from .workpaper import (
    build_workpaper_from_text,
    react_enrich_workpaper,
    apply_company_profile_hint,
    build_context_pack,
    build_context_capsule,
    sanitize_company_scope_fields,
)
from .agents import run_agent
from .tavily_client import TavilyClient
from .financials import extract_financials_with_fallback
from .summarizer import summarize_text
from .run_logger import log_step
from .pdf_loader import extract_company_name
from .pdf_loader import (
    extract_revenue_context,
    extract_context_text,
    score_revenue_text,
    score_context_text,
)


BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
SAMPLE_10K = BASE_DIR / "aapl_10-K-2025-As-Filed.pdf"

RUNS: Dict[str, Dict[str, Any]] = {}
RUN_LOCK = threading.Lock()
RUN_TIMEOUT_SECONDS = 300


class RunRequest(BaseModel):
    input_texts: Optional[List[str]] = None
    use_samples: bool = True
    enable_defense: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


def create_app(
    llm_factory: Optional[Callable[[str, str, str, str], Any]] = None
) -> FastAPI:
    app = FastAPI(title="FFMAS Prototype")

    use_default_factory = llm_factory is None

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    if use_default_factory:
        def llm_factory(provider: str, model: str, api_key: str, base_url: str):
            return LLMClient(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=load_config().llm_timeout_seconds,
                max_retries=load_config().llm_max_retries,
            )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        config = load_config()
        _, has_samples = _get_sample_pdf_paths()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "defaults": {
                    "provider": config.llm_provider,
                    "model": config.llm_model_name,
                    "base_url": config.llm_base_url,
                },
                "has_samples": has_samples,
                "has_api_key": bool(config.llm_api_key),
            },
        )

    @app.post("/api/run")
    def run_analysis(payload: RunRequest, mode: str = "async"):
        config = load_config()
        provider = payload.provider or config.llm_provider
        model = payload.model or config.llm_model_name
        api_key = config.llm_api_key
        base_url = payload.base_url or config.llm_base_url

        if not api_key and use_default_factory:
            raise HTTPException(status_code=400, detail="Missing API key")

        input_texts = payload.input_texts
        pdf_paths: Optional[List[str]] = None

        if not input_texts:
            if payload.use_samples:
                pdf_paths, has_samples = _get_sample_pdf_paths()
                if not has_samples:
                    raise HTTPException(status_code=400, detail="Sample 10-K PDF not found")
            else:
                raise HTTPException(status_code=400, detail="No input texts or sample PDFs")

        output_dir = BASE_DIR / "outputs" / f"run_{int(time.time())}"
        llm = llm_factory(provider, model, api_key, base_url)
        tavily_client = TavilyClient(config.tavily_api_key) if config.tavily_api_key else None
        if getattr(llm, "_responses", None) is not None:
            tavily_client = None

        if mode == "sync":
            final_report = run_pipeline(
                input_texts=input_texts,
                pdf_paths=pdf_paths,
                llm=llm,
                output_dir=output_dir,
                enable_defense=payload.enable_defense,
                tavily_client=tavily_client,
            )
            workpaper_path = output_dir / "workpaper.json"
            workpaper = json.loads(workpaper_path.read_text(encoding="utf-8"))

            agent_reports: Dict[str, Any] = {}
            for report_file in (output_dir / "agent_reports").glob("*.json"):
                agent_reports[report_file.stem] = json.loads(report_file.read_text(encoding="utf-8"))

            step_outputs = {
                "workpaper": workpaper,
                "base": agent_reports.get("base"),
                "fraud_type_A": agent_reports.get("fraud_type_A"),
                "fraud_type_B": agent_reports.get("fraud_type_B"),
                "fraud_type_C": agent_reports.get("fraud_type_C"),
                "fraud_type_D": agent_reports.get("fraud_type_D"),
                "fraud_type_E": agent_reports.get("fraud_type_E"),
                "fraud_type_F": agent_reports.get("fraud_type_F"),
                "defense": agent_reports.get("defense"),
                "final": final_report,
            }

            return JSONResponse(
                {
                    "final_report": final_report,
                    "workpaper": workpaper,
                    "agent_reports": agent_reports,
                    "step_outputs": step_outputs,
                    "meta": {
                        "output_dir": str(output_dir),
                        "used_samples": payload.use_samples,
                    },
                }
            )

        run_id = str(uuid.uuid4())
        with RUN_LOCK:
            RUNS[run_id] = {
                "status": "running",
                "step_outputs": {},
                "agent_reports": {},
                "final_report": None,
                "workpaper": None,
                "meta": {"output_dir": str(output_dir), "used_samples": payload.use_samples},
                "started_at": time.time(),
                "last_update": time.time(),
            }

        thread = threading.Thread(
            target=_run_pipeline_stream,
            args=(
                run_id,
                input_texts,
                pdf_paths,
                llm,
                output_dir,
                payload.enable_defense,
                tavily_client,
            ),
            daemon=True,
        )
        thread.start()

        return JSONResponse({"run_id": run_id})

    @app.get("/api/status")
    def run_status(run_id: str):
        with RUN_LOCK:
            data = RUNS.get(run_id)
        if not data:
            raise HTTPException(status_code=404, detail="Run not found")
        if data.get("status") == "running":
            last_update = data.get("last_update", data.get("started_at", time.time()))
            if time.time() - last_update > RUN_TIMEOUT_SECONDS:
                _fail_run(run_id, "运行超时，请缩短文本或稍后重试")
                with RUN_LOCK:
                    data = RUNS.get(run_id)
        return JSONResponse(data)

    return app


app = create_app()


def _get_sample_pdf_paths() -> (List[str], bool):
    if SAMPLE_10K.exists():
        return [str(SAMPLE_10K)], True
    return [], False


def _run_pipeline_stream(
    run_id: str,
    input_texts: Optional[List[str]],
    pdf_paths: Optional[List[str]],
    llm,
    output_dir: Path,
    enable_defense: bool,
    tavily_client=None,
) -> None:
    try:
        texts: List[str] = []
        financial_text = ""
        revenue_text = ""
        context_text = ""
        if pdf_paths:
            for path in pdf_paths:
                chunks = extract_pdf_text_chunks(path)
                texts.extend([c["text"] for c in chunks])
                if not financial_text:
                    financial_text = extract_financial_statement_text(chunks)
                if not revenue_text:
                    revenue_text = extract_revenue_context(chunks)
                if not context_text:
                    context_text = extract_context_text(chunks)
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
        _update_run(run_id, {"collect_summary": summary_text})
        company_name = extract_company_name(combined_text)
        _update_run(run_id, {"collect_company_name": company_name or "未识别"})
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
        _update_run(run_id, {"collect_financial_data": financial_data})
        context_source = context_text or summary_text
        context_pack = build_context_pack(context_source, llm, company_name=company_name)
        context_capsule = build_context_capsule(context_pack)
        log_step(output_dir, "context_pack", context_pack)
        _update_run(run_id, {"collect_context_pack": context_pack})
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

        with open(output_dir / "workpaper.json", "w", encoding="utf-8") as f:
            json.dump(workpaper, f, ensure_ascii=False, indent=2)

        _update_run(run_id, {"workpaper": workpaper})

        reports: Dict[str, Any] = {}
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
            with open(output_dir / "agent_reports" / f"{agent}.json", "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            _update_run(run_id, {agent: report})
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
            with open(output_dir / "agent_reports" / "defense.json", "w", encoding="utf-8") as f:
                json.dump(defense_report, f, ensure_ascii=False, indent=2)
            _update_run(run_id, {"defense": defense_report})
            log_step(output_dir, "agent:defense", defense_report)

        final_report = llm.generate_json(
            "你是裁决分析智能体，负责综合判断舞弊风险等级。",
            f"以下是各智能体结论：\n{json.dumps(reports, ensure_ascii=False)}",
            {
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
            },
        )
        with open(output_dir / "final_report.json", "w", encoding="utf-8") as f:
            json.dump(final_report, f, ensure_ascii=False, indent=2)
        log_step(output_dir, "final_report", final_report)

        _finalize_run(run_id, workpaper, reports, final_report)
    except Exception as exc:
        _fail_run(run_id, str(exc))


def _update_run(run_id: str, step_data: Dict[str, Any]) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            return
        run["step_outputs"].update(step_data)
        run["last_update"] = time.time()


def _finalize_run(run_id: str, workpaper: Dict[str, Any], reports: Dict[str, Any], final_report: Dict[str, Any]) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            return
        run["status"] = "completed"
        run["workpaper"] = workpaper
        run["agent_reports"] = reports
        run["final_report"] = final_report
        run["last_update"] = time.time()
        run["step_outputs"].update(
            {
                "workpaper": workpaper,
                "base": reports.get("base"),
                "fraud_type_A": reports.get("fraud_type_A"),
                "fraud_type_B": reports.get("fraud_type_B"),
                "fraud_type_C": reports.get("fraud_type_C"),
                "fraud_type_D": reports.get("fraud_type_D"),
                "fraud_type_E": reports.get("fraud_type_E"),
                "fraud_type_F": reports.get("fraud_type_F"),
                "defense": reports.get("defense"),
                "final": final_report,
            }
        )


def _fail_run(run_id: str, error: str) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            return
        run["status"] = "failed"
        run["error"] = error
        run["last_update"] = time.time()
