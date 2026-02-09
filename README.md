# ForenSight（证镜）

面向财务舞弊研判的多智能体分析系统。  
核心链路是：`信息汇聚 -> 结构化底稿(workpaper) -> 多智能体研判 -> 裁决报告`。

这个项目更偏“证据驱动研判引擎”，而不是纯问答：每次运行都会落地完整中间产物，便于复盘和审计。

## 这个项目能做什么

- 输入财报文本或上传文档（`PDF/ODF/ODT`）
- 自动提取财务字段并计算关键指标（盈利、流动性、杠杆、效率、估值）
- 生成结构化工作底稿 `workpaper.json`
- 并发执行 8 类智能体：
  - `base`（基础风险）
  - `fraud_type_A ~ fraud_type_F`（六类专项风险）
  - `defense`（辩护/复核，支持开关）
- 触发自主外部补充调查（ReAct，最多两轮）
- 输出最终裁决 `final_report.json`（总体风险、采纳点、驳回点、理由、建议）

## 处理流程（与代码一致）

1. 信息汇聚：从文本/上传文档提取可分析内容  
2. 财务结构化：抽取报表字段并补全关键缺口（可结合 SEC / Tavily）  
3. 底稿构建：生成 `workpaper` + `context_pack` + `context_capsule`  
4. 多智能体分析：基于底稿执行 `base + A~F (+ defense)`  
5. 裁决输出：聚合智能体报告生成 `final_report`  
6. 落盘与追踪：写入 `outputs/run_xxx/` 下的所有阶段文件

## 架构与技术栈

- 后端：FastAPI（`src/web_app.py`）
- 编排：`src/orchestrator.py` / `src/agents.py`
- 文档解析：`pypdf` + ODF(XML) 解析
- 前端：Jinja2 + 原生 JS/CSS
- LLM：当前仅支持 DeepSeek（配置中固定）
- 测试：pytest

## 快速开始

### 1) 环境准备

- Python `>= 3.9`
- DeepSeek API Key

### 2) 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) 配置

```bash
cp .env.example .env
```

必填：

- `LLM_API_KEY`

建议确认：

- `LLM_PROVIDER=deepseek`
- `LLM_MODEL_NAME=deepseek-chat`（或 `deepseek-reasoner`）
- `LLM_BASE_URL=https://api.deepseek.com`

可选：

- `TAVILY_API_KEY`（外部联网检索）
- `AGENT_MAX_CONCURRENCY`（默认 `4`，建议 `2-8`）
- `LLM_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES`

### 4) 启动服务

```bash
uvicorn src.web_app:app --reload
```

打开：`http://127.0.0.1:8000`

## API 说明

### 1) 上传财报（可选）

- `POST /api/upload-report`
- 支持：`.pdf` / `.odf` / `.odt`
- 返回：`report_id`

### 2) 发起分析

- `POST /api/run?mode=sync|async`
- `mode=sync`：直接返回完整结果
- `mode=async`：返回 `run_id`，再轮询状态

请求体（文本模式）：

```json
{
  "input_texts": ["...财报正文或摘要..."],
  "enable_defense": true
}
```

请求体（上传文件模式）：

```json
{
  "uploaded_report_id": "xxxx",
  "enable_defense": true
}
```

补充字段：

- `model`：可覆盖模型名（仅接受 `deepseek*`）
- `base_url`：可覆盖 API Base URL

### 3) 查询异步状态

- `GET /api/status?run_id=<id>`
- 状态字段：`running | completed | failed`

## 输出文件（每次运行）

目录：`outputs/run_<timestamp>_<id>/`

- `workpaper.json`：结构化底稿
- `agent_reports/*.json`：每个智能体独立报告
- `final_report.json`：最终裁决
- `run.log`：阶段日志（summary、financial_data、workpaper、agent:*、final_report）

## 检索机制说明（不是向量 RAG）

本项目不是“向量库召回式 RAG”。当前是：

- 外部搜索增强（Tavily API）
- 外部结构化数据补全（SEC CompanyFacts）
- 搜索结果以文本摘要方式拼接到 prompt，供模型参考

也就是说，更接近 `Search-Augmented Generation`。

## 配置项

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_PROVIDER` | 否 | `deepseek` | 当前仅 deepseek 生效 |
| `LLM_MODEL_NAME` | 否 | `deepseek-chat` | 模型名称 |
| `LLM_API_KEY` | 是 | - | DeepSeek API Key |
| `LLM_BASE_URL` | 否 | `https://api.deepseek.com` | DeepSeek API 地址 |
| `LLM_TIMEOUT_SECONDS` | 否 | `90` | LLM 请求超时（秒） |
| `LLM_MAX_RETRIES` | 否 | `2` | LLM 请求重试次数 |
| `AGENT_MAX_CONCURRENCY` | 否 | `4` | 智能体并发上限（1-16） |
| `TAVILY_API_KEY` | 否 | 空 | 联网检索增强 |
| `DEBUG` | 否 | `false` | 调试开关 |

## 开发命令

```bash
make setup
make test
make run-web
```

等价命令：

- `make setup`：创建虚拟环境并安装依赖
- `make test`：运行 pytest
- `make run-web`：启动 Web 服务

## 项目结构

```text
.
├── src/
│   ├── web_app.py        # API入口、异步状态与流式阶段更新
│   ├── orchestrator.py   # 同步主流程编排
│   ├── agents.py         # 多智能体执行、ReAct补充检索
│   ├── workpaper.py      # 底稿生成、上下文胶囊、底稿补全
│   ├── financials.py     # 财务抽取、SEC/Tavily补全、指标计算
│   ├── tavily_client.py  # Tavily搜索封装
│   └── ...
├── templates/            # 前端模板
├── static/               # 前端脚本与样式
├── tests/                # 单元测试
├── outputs/              # 运行产物
└── README.md
```

## 常见问题

### 1) 为什么有时 Tavily 看起来“没结果”

当前 `src/tavily_client.py` 在请求异常时会直接返回空列表。  
如果 Tavily 账号超额、鉴权失败或网络异常，前端只会看到“无检索结果”。

建议检查：

- `TAVILY_API_KEY` 是否有效
- Tavily 账户是否有可用额度
- 出网网络是否可访问 `https://api.tavily.com`

### 2) 置信度为什么容易重复（比如都 0.85）

`confidence` 目前由 LLM 直接生成，没有程序化校准公式。  
因此会出现同批智能体给出接近分数的情况。

## 已知限制

- 结论质量高度依赖输入文本质量与完整度
- 外部检索质量受 Tavily 命中率与额度限制
- 当前 provider 固定为 DeepSeek

## 后续可优化方向

- 给 `confidence` 增加可解释的程序化打分（证据数量、冲突度、检索覆盖度）
- 增加证据定位（页码/段落索引）
- 支持更多 LLM provider（OpenAI/Anthropic 等）
- 建立稳定评测集与回归基线
