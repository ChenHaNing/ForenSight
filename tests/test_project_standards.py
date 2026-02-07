from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_github_project_files_exist():
    required_paths = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "CONTRIBUTING.md",
        PROJECT_ROOT / ".gitignore",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
        PROJECT_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
        PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
        PROJECT_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    assert not missing, f"Missing required project files: {missing}"


def test_env_example_does_not_contain_realistic_secret_prefix():
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "sk-" not in env_example
    assert "your_llm_api_key_here" in env_example


def test_gitignore_covers_main_runtime_artifacts():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in [".venv/", ".env", "outputs/*"]:
        assert pattern in gitignore


def test_ci_workflow_runs_pytest():
    ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m pytest" in ci


def test_readme_contains_quickstart_and_test_sections():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "快速开始" in readme
    assert "测试" in readme
