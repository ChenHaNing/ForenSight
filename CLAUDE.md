# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ForenSight (证镜) is a multi-agent financial fraud detection prototype. It processes financial reports (PDF/ODF/text) through specialized AI agents to produce structured fraud risk assessments. The domain language is Chinese. Based on a Shenzhen Stock Exchange research paper (independent implementation, not official).

## Commands

```bash
# Initial setup (creates venv, installs deps)
make setup

# Run all tests (quiet mode by default via pyproject.toml addopts)
make test

# Run a single test file
.venv/bin/python -m pytest tests/test_agents.py -v

# Run a specific test by name
.venv/bin/python -m pytest tests/test_agents.py::test_agent_runs_without_tavily -v

# Lint check (ruff)
make lint

# Auto-format (ruff)
make format

# Start the web server (FastAPI + Uvicorn with auto-reload)
make run-web
```

## Architecture

### Pipeline Flow

The system runs as a sequential pipeline orchestrated by `src/orchestrator.py:run_pipeline()`:

1. **PDF/text ingestion** — `pdf_loader.py` extracts overlapping text chunks, scores them by financial keyword relevance, and selects the best segments for financial statements, revenue context, and business description
2. **Summarization** — `summarizer.py` produces a two-stage summary (chunk summaries → final)
3. **Financial extraction** — `financials.py` runs a 4-tier fallback strategy: LLM extraction → enrichment LLM call → Tavily web search → zero defaults. This is the largest module (~1500 LOC) with extensive field alias mapping
4. **Workpaper construction** — `workpaper.py` builds a 16-field structured document validated against a JSON schema, including fraud-type-specific analysis blocks (A through F)
5. **Agent execution** — `agents.py` runs 7 fraud-type agents + optional defense agent in parallel via `ThreadPoolExecutor`. Each agent receives its focused workpaper block plus shared context. Agents use a ReAct pattern: they can request follow-up Tavily searches (max 2 rounds)
6. **Judge synthesis** — A final LLM call synthesizes all agent reports into `final_report.json` with accepted/rejected points and overall risk level

### Key Design Patterns

- **LLM abstraction**: All LLM calls go through `LLMClient.generate_json()` which handles retry with exponential backoff, JSON parsing (including stripping markdown fences), and schema injection into prompts. The client normalizes base URLs by stripping `/v1` or `/v1/chat/completions` suffixes.
- **Provider lock**: Currently hardcoded to DeepSeek only (`config.py` forces provider to "deepseek").
- **Agent concurrency**: `ThreadPoolExecutor` with configurable concurrency (1-16 workers, clamped in `config.py`). Automatically drops to 1 worker when `FakeLLM` is detected (tests).
- **ReAct retry**: Agents include a `research_plan` in their output. If `need_autonomous_research` is true and Tavily is configured, the agent re-runs with supplemental search results. Search results are filtered by company name and deduplicated.
- **Output artifacts**: Each run produces `outputs/run_<timestamp>/` containing `run.log` (JSONL), `workpaper.json`, `agent_reports/*.json`, and `final_report.json`.

### Module Dependency Graph

```
orchestrator.py  (entry point)
  ├── pdf_loader.py       (text extraction & chunk scoring)
  ├── summarizer.py       (two-stage LLM summarization)
  ├── financials.py       (financial data extraction & metrics)
  │   └── ratio_calculator.py  (20+ financial ratio computations)
  ├── workpaper.py        (structured workpaper construction)
  │   └── tavily_client.py     (optional web search)
  ├── agents.py           (multi-agent execution & ReAct retry)
  └── run_logger.py       (JSONL step logging)

web_app.py      (FastAPI server, calls orchestrator)
config.py       (env-based configuration, used by web_app)
token_utils.py  (token estimation & prompt truncation, used by agents/workpaper/financials)
llm_client.py   (LLM API wrapper with retry, response_format, schema validation)
```

### Web App (`web_app.py`)

FastAPI application with endpoints: `POST /api/upload-report` (file upload), `POST /api/run?mode=async|sync` (trigger analysis), `GET /api/status?run_id=` (poll progress), `POST /api/download` (ZIP results). Uses in-memory state with TTL cleanup and threading for async runs.

## Testing Conventions

- **FakeLLM** (`tests/helpers/fake_llm.py`): Mock that returns pre-defined responses via `pop(0)`. Tests must queue the exact number of responses the code path will consume.
- **Tavily auto-disabled**: Tavily client checks for `PYTEST_CURRENT_TEST` env var and disables itself during tests.
- **Concurrency in tests**: Agent suite automatically uses 1 worker when it detects `FakeLLM` (checks `llm._responses is not None`).
- **conftest.py**: Adds project root to `sys.path` so `src` imports work.

## Environment Configuration

Configured via `.env` (see `.env.example`). Key variables:
- `LLM_API_KEY` — required for real LLM calls
- `LLM_BASE_URL` — default `https://api.deepseek.com`
- `AGENT_MAX_CONCURRENCY` — parallel agent workers (1-16, default 4)
- `TAVILY_API_KEY` — optional, enables external web search enrichment
- `DEBUG` — enables debug mode

## Agent Types Reference

| Agent | Focus | Workpaper Field |
|-------|-------|-----------------|
| `base` | Overall fraud risk | `financial_summary` |
| `fraud_type_A` | Fictitious revenue transactions | `fraud_type_A_block` |
| `fraud_type_B` | Net income manipulation | `fraud_type_B_block` |
| `fraud_type_C` | Accounting policy manipulation | `fraud_type_C_block` |
| `fraud_type_D` | Asset valuation fraud | `fraud_type_D_block` |
| `fraud_type_E` | Related-party fund diversion | `fraud_type_E_block` |
| `fraud_type_F` | Industry-specific risks | `fraud_type_F_block` |
| `defense` (optional) | Counter-evidence | Entire workpaper |
