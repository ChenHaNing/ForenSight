# Contributing

感谢你对 ForenSight 的关注，欢迎通过 Issue / Pull Request 参与贡献。

## 开发环境

1. Fork 并克隆仓库。
2. 创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. 配置环境变量：

```bash
cp .env.example .env
```

## 提交代码前

请至少完成以下检查：

```bash
make lint    # ruff 代码检查
make test    # 运行全部测试
```

代码格式化（可选但推荐）：

```bash
make format  # ruff 自动格式化
```

如果你修改了 API、行为或文档，请同时更新相应测试与 `README.md`。

CI 会在每个 PR 上自动运行 lint + test，请确保本地通过后再提交。

## 提交规范

- 每个 PR 尽量聚焦单一主题。
- Commit message 清晰描述“做了什么、为什么做”。
- 避免提交本地敏感信息（`.env`、私钥、token）。
- 不要提交运行产物目录（`outputs/`）中的分析结果文件。

## Pull Request 清单

- [ ] 代码可运行，测试通过
- [ ] 新增/修改行为有测试覆盖
- [ ] 文档已同步更新（如适用）
- [ ] 不包含敏感信息

## 行为准则

请保持专业、尊重和建设性沟通。
