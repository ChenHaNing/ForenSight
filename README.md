# FFMAS: 多智能体财务舞弊识别系统

FFMAS（Financial Fraud Multi-Agent System）是一个基于大模型与多智能体协同推理的财务舞弊分析原型。  
项目支持从 10-K 等文本/PDF 中抽取财务与上下文信息，生成结构化工作底稿，并通过基础风控、专项舞弊、辩护、裁决等智能体输出最终风险报告。

## 功能概览

- 支持 PDF 或纯文本输入
- 自动构建工作底稿（含财务指标、证据、外部检索摘要）
- 多智能体并行/串行风险分析（A-F 六类舞弊 + 基础风控 + 辩护 + 裁决）
- 提供 Web 可视化流程与逐步输出
- 支持同步与异步 API 执行模式

## 技术栈

- Python 3.9+
- FastAPI + Jinja2（Web/API）
- Streamlit（原型界面）
- Pytest（测试）

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

至少设置：

- `LLM_PROVIDER`
- `LLM_MODEL_NAME`
- `LLM_API_KEY`
- `LLM_BASE_URL`

可选设置：

- `TAVILY_API_KEY`（外部检索）
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`

### 3. 运行方式

#### FastAPI Web（推荐）

```bash
uvicorn src.web_app:app --reload
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

#### Streamlit 原型

```bash
streamlit run app.py
```

## API 说明

- `POST /api/run`
  - `mode=sync`：同步返回 `final_report/workpaper/agent_reports`
  - `mode=async`（默认）：返回 `run_id`
- `GET /api/status?run_id=<id>`
  - 查询异步运行进度、步骤输出与最终状态

## 测试

```bash
python -m pytest
```

项目已将测试接入 GitHub Actions（`.github/workflows/ci.yml`），每次 Push/PR 自动执行。

## 目录结构

```text
.
├── app.py                    # Streamlit 入口
├── src/                      # 核心业务代码
│   ├── web_app.py            # FastAPI 应用与异步流程
│   ├── orchestrator.py       # 主流程编排
│   ├── agents.py             # 各类智能体执行
│   ├── financials.py         # 财务数据抽取与指标计算
│   ├── workpaper.py          # 工作底稿构建与补全
│   └── ...
├── tests/                    # 单元/流程测试
├── static/ templates/        # 前端资源
├── outputs/                  # 运行产物（已忽略）
└── .github/                  # CI 与协作模板
```

## 开发与贡献

见 `CONTRIBUTING.md`。

## 安全说明

- 不要提交真实密钥到仓库
- `.env`、运行日志与输出工件应保持本地化
