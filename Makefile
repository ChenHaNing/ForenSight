.PHONY: setup test run-web run-streamlit

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

test:
	python -m pytest

run-web:
	uvicorn src.web_app:app --reload

run-streamlit:
	streamlit run app.py
