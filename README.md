# FFMAS: 多智能体财务舞弊识别系统

FFMAS（Financial Fraud Multi-Agent System）是一个基于大模型与多智能体协同推理的财务舞弊分析原型。

## 功能

- 支持 PDF 或纯文本输入
- 自动生成结构化工作底稿
- 多智能体风险分析（基础风控 + 六类舞弊 + 辩护 + 裁决）
- 提供 FastAPI Web 界面与同步/异步 API

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少配置：

- `LLM_PROVIDER`
- `LLM_MODEL_NAME`
- `LLM_API_KEY`
- `LLM_BASE_URL`

可选配置：

- `TAVILY_API_KEY`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`

### 3. 运行

FastAPI Web（推荐）：

```bash
uvicorn src.web_app:app --reload
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)

Streamlit 原型（可选）：

```bash
streamlit run app.py
```

## API

- `POST /api/run`
  - `mode=sync`：同步返回 `final_report/workpaper/agent_reports`
  - `mode=async`（默认）：返回 `run_id`
- `GET /api/status?run_id=<id>`：查询异步运行状态与阶段输出

## 测试

```bash
python -m pytest
```

## 项目结构

```text
.
├── app.py
├── src/
├── tests/
├── templates/
├── static/
├── outputs/
├── requirements.txt
└── README.md
```
