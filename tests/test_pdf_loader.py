from src.pdf_loader import (
    extract_financial_statement_text,
    extract_company_name,
    extract_revenue_context,
    extract_context_text,
)


def test_extract_financial_statement_text_picks_keywords():
    chunks = [
        {"text": "Random text"},
        {"text": "Consolidated Balance Sheets\nTotal assets 100"},
        {"text": "Other section"},
        {"text": "Consolidated Statements of Cash Flows"},
    ]
    text = extract_financial_statement_text(chunks, max_chars=1000)
    assert "Balance Sheets" in text or "Consolidated Balance Sheets" in text
    assert "Cash Flows" in text


def test_extract_financial_statement_text_prefers_numeric_dense_chunks():
    chunks = [
        {"text": "Consolidated Statements of Operations"},
        {"text": "Net income 100 200 300 400 500 600 700 800 900"},
    ]
    text = extract_financial_statement_text(chunks, max_chars=60)
    assert "Net income" in text


def test_extract_company_name_from_registrant_line():
    text = "APPLE INC.\nExact name of registrant as specified in its charter\nCommission File Number"
    assert extract_company_name(text) == "APPLE INC."


def test_extract_revenue_context_prefers_revenue_keywords():
    chunks = [
        {"text": "Random text"},
        {"text": "Net sales by product\niPhone 100\nMac 50"},
        {"text": "Other section"},
    ]
    text = extract_revenue_context(chunks, max_chars=200)
    assert "Net sales by product" in text


def test_extract_context_text_prefers_business_section():
    chunks = [
        {"text": "Random text"},
        {"text": "Item 1. Business\nWe design products..."},
        {"text": "Other section"},
    ]
    text = extract_context_text(chunks, max_chars=200)
    assert "Item 1. Business" in text
