# Contributing Guide

## 开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 本地运行

```bash
uvicorn src.web_app:app --reload
```

或：

```bash
streamlit run app.py
```

## 提交前检查

```bash
python -m pytest
```

请确保新增/修改逻辑有对应测试覆盖。

## 分支与提交建议

- 分支建议：`codex/<topic>`
- Commit message 建议使用 Conventional Commits：
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `test: ...`
  - `chore: ...`

## Pull Request 要求

- 描述问题背景和改动目标
- 说明关键实现点与风险点
- 附上测试结果（命令与通过数量）
- 若改动 API/UI，请附示例或截图

## 不应提交的内容

- `.env`、密钥、令牌
- `.venv/` 虚拟环境
- `outputs/` 运行产物、临时日志
