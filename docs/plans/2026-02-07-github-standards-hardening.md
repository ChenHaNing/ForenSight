# GitHub Standards Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 FFMAS 项目规整为可直接在 GitHub 协作与持续集成使用的标准化仓库结构。

**Architecture:** 通过补齐仓库元信息（README/CONTRIBUTING）、自动化流程（GitHub Actions CI）、协作模板（Issue/PR）和项目约束测试，形成“文档可读 + 流程可跑 + 质量可验”的主干闭环。所有改动保持对现有业务逻辑最小侵入。

**Tech Stack:** Python, FastAPI, Streamlit, Pytest, GitHub Actions

---

### Task 1: 仓库文档与元信息补齐

**Files:**
- Create: `README.md`
- Create: `CONTRIBUTING.md`
- Modify: `.env.example`
- Create: `.gitignore`
- Create: `Makefile`
- Create: `pyproject.toml`

**Steps:**
1. 编写 README（快速开始、运行方式、API、测试、目录结构）。
2. 编写 CONTRIBUTING（提交流程、测试要求、PR 要求）。
3. 清理 `.env.example` 中疑似真实密钥示例值。
4. 增加 `.gitignore` 忽略 `.venv/.env/outputs`。
5. 增加 Makefile 命令入口与 pytest 配置。

### Task 2: GitHub 协作与 CI 主干流程

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`

**Steps:**
1. 新增 CI，自动安装依赖并执行编译检查与 pytest。
2. 新增 PR 模板统一变更说明与测试检查。
3. 新增 Bug/Feature Issue 模板提升问题反馈质量。

### Task 3: 测试规整与主流程覆盖

**Files:**
- Modify: `tests/test_webapp.py`
- Create: `tests/test_project_standards.py`

**Steps:**
1. 新增异步 API 主流程测试（`/api/run` + `/api/status`）。
2. 新增项目标准约束测试（关键文件存在、敏感示例值、gitignore/CI 约束）。
3. 运行全量 pytest，确保不回归。
