# ForenSight（证镜）

ForenSight 是一个面向财务舞弊研判的多智能体证据推理原型系统。  
它将“结构化底稿构建 -> 多角色分析 -> 辩护对冲 -> 裁决输出”串成一条可追踪链路，用于快速形成可解释的风险结论。

## 适用场景

- 财报初筛：快速识别高风险信号，辅助后续人工核查
- 审计/合规辅助：形成结构化“风险点-证据-建议”输出
- 研究演示：验证多智能体协作与证据驱动裁决流程

## 核心能力

- 多输入模式：支持 `input_texts` 纯文本和上传 `PDF/ODF/ODT` 财报
- 结构化工作底稿：自动生成公司画像、风险披露、公告、关联方、行业对标等字段
- 多智能体分析：
  - `base` 基础风险智能体
  - `fraud_type_A` 至 `fraud_type_F` 六类舞弊专项智能体
  - `defense` 辩护智能体（可选）
  - 最终 `judge` 裁决输出
- 智能体并发执行：核心智能体支持并发运行，显著缩短整体等待时间（可配置并发度）
- 自主外部调查（ReAct）：当证据不足时，智能体会按 `research_plan` 发起多轮外部检索（可接 Tavily）
- 同步/异步运行：同步直接回包，异步通过 `run_id` 轮询状态
- 可追踪产物：每次运行落地 `workpaper.json`、各智能体报告和 `final_report.json`

## 处理流程

1. 信息汇聚：读取文本/文件并提取关键段落
2. 财务结构化：抽取报表字段并计算财务指标
3. 底稿构建：生成 `workpaper`（含 context pack/capsule）
4. 多智能体研判：基础 + 六类舞弊 + 辩护
5. 裁决汇总：输出总体风险等级、接受/驳回点及建议
6. 归档落盘：保存阶段日志与结果 JSON

## 技术栈

- 后端：FastAPI
- 模板与前端：Jinja2 + 原生 JS/CSS
- 文档解析：pypdf + ODF(XML) 解析
- LLM 调用：当前仅支持 DeepSeek
- 测试：pytest

## 快速开始

### 1) 环境要求

- Python `>= 3.9`
- 可用的 DeepSeek API Key

### 2) 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) 配置环境变量

```bash
cp .env.example .env
```

至少需要配置：

- `LLM_API_KEY`

当前固定为 DeepSeek，请确认：

- `LLM_PROVIDER=deepseek`
- `LLM_MODEL_NAME=deepseek-chat`（或 `deepseek-reasoner`）
- `LLM_BASE_URL=https://api.deepseek.com`

可选：

- `TAVILY_API_KEY`（启用外部检索增强）
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `AGENT_MAX_CONCURRENCY`（默认 `4`，建议 `2-8`）

### 4) 启动服务

```bash
uvicorn src.web_app:app --reload
```

访问：`http://127.0.0.1:8000`

## API 使用

### 1) 上传财报文件（可选）

- `POST /api/upload-report`
- 支持：`.pdf`、`.odf`、`.odt`
- 返回：`report_id`

### 2) 触发分析

- `POST /api/run`
- Query 参数：
  - `mode=sync` 同步返回完整结果
  - `mode=async` 异步返回 `run_id`

请求体示例（文本输入）：

```json
{
  "input_texts": ["...财报正文或摘要..."],
  "enable_defense": true
}
```

请求体示例（已上传文件）：

```json
{
  "uploaded_report_id": "xxxx",
  "enable_defense": true
}
```

### 3) 查询异步状态

- `GET /api/status?run_id=<id>`

## 输出目录与文件

每次运行会在 `outputs/run_<timestamp>_<id>/` 下生成：

- `workpaper.json`：结构化工作底稿
- `agent_reports/base.json` 等：各智能体结论
- `agent_reports/defense.json`：辩护智能体结论（启用时）
- `final_report.json`：最终裁决报告
- `run.log`：阶段日志

## 配置项说明

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_PROVIDER` | 否 | `deepseek` | LLM 提供方（当前固定 `deepseek`） |
| `LLM_MODEL_NAME` | 否 | `deepseek-chat` | 模型名称（`deepseek-chat` / `deepseek-reasoner`） |
| `LLM_API_KEY` | 是 | - | LLM 鉴权密钥 |
| `LLM_BASE_URL` | 否 | `https://api.deepseek.com` | DeepSeek API 基地址 |
| `LLM_TIMEOUT_SECONDS` | 否 | `90` | 单次请求超时（秒） |
| `LLM_MAX_RETRIES` | 否 | `2` | LLM 请求重试次数 |
| `AGENT_MAX_CONCURRENCY` | 否 | `4` | 智能体并发数上限（测试桩模式自动退回串行） |
| `TAVILY_API_KEY` | 否 | 空 | 外部检索增强（可选） |
| `DEBUG` | 否 | `false` | 调试开关 |

## 开发与测试

运行测试：

```bash
python3 -m pytest -q
```

Makefile 命令：

- `make setup`：创建虚拟环境并安装依赖
- `make test`：运行测试
- `make run-web`：启动 Web 服务

## 项目结构

```text
.
├── src/
│   ├── web_app.py          # FastAPI 入口与 API
│   ├── orchestrator.py     # 总流程编排
│   ├── workpaper.py        # 工作底稿构建与补全
│   ├── agents.py           # 多智能体执行与自主调查重试
│   ├── financials.py       # 财务字段抽取与指标计算
│   └── ...
├── templates/              # Jinja2 模板
├── static/                 # 前端脚本与样式
├── tests/                  # 单元测试
├── outputs/                # 运行产物
├── requirements.txt
└── README.md
```

## 已知限制

- 结论质量依赖输入财报质量与上下文完整度
- 外部检索增强依赖 Tavily 可用性与检索命中

## 下一步建议

- 增加 OpenAI/Anthropic provider 适配
- 增加更细粒度的证据引用定位（页码/段落坐标）
- 引入评测基准与回归数据集，稳定衡量策略改动效果
