.PHONY: setup test lint format clean run-web

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

test:
	. .venv/bin/activate && python -m pytest

lint:
	. .venv/bin/activate && python -m ruff check src/ tests/

format:
	. .venv/bin/activate && python -m ruff format src/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage

run-web:
	. .venv/bin/activate && uvicorn src.web_app:app --reload
