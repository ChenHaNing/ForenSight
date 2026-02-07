from src.financials import compute_financial_metrics, extract_financials_with_fallback


def test_compute_financial_metrics_basic():
    data = {
        "income_statement": {
            "revenue": 1000.0,
            "cost_of_goods_sold": 600.0,
            "operating_income": 120.0,
            "net_income": 80.0,
            "ebit": 120.0,
            "interest_expense": 20.0,
        },
        "balance_sheet": {
            "total_assets": 2000.0,
            "current_assets": 700.0,
            "inventory": 200.0,
            "cash_and_equivalents": 150.0,
            "current_liabilities": 350.0,
            "shareholders_equity": 900.0,
            "total_debt": 500.0,
            "accounts_receivable": 250.0,
        },
        "cash_flow": {},
        "market_data": {},
    }
    metrics, notes = compute_financial_metrics(data)
    assert not any(note.startswith("profitability.gross_margin") for note in notes)
    assert not any(note.startswith("efficiency.receivables_turnover") for note in notes)
    assert metrics["profitability"]["gross_margin"] == 0.4
    assert metrics["liquidity"]["current_ratio"] == 2.0
    assert metrics["leverage"]["debt_to_equity"] == 500.0 / 900.0
    assert metrics["efficiency"]["receivables_turnover"] == 1000.0 / 250.0


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
        return self.responses.pop(0)


def test_extract_financials_with_fallback_enriches_missing_core_fields():
    response = {
        "income_statement": {
            "revenue": 416161,
            "cost_of_goods_sold": 220960,
            "operating_income": 133050,
            "net_income": 112010,
            "ebit": None,
            "interest_expense": None,
            "ebitda": None,
        },
        "balance_sheet": {
            "total_assets": 359241,
            "current_assets": 147957,
            "inventory": 5718,
            "cash_and_equivalents": 35934,
            "current_liabilities": 165631,
            "shareholders_equity": None,
            "total_debt": None,
            "accounts_receivable": 39777,
        },
        "cash_flow": {
            "operating_cash_flow": 111482,
            "investing_cash_flow": 15195,
            "financing_cash_flow": None,
        },
        "market_data": {
            "share_price": None,
            "shares_outstanding": 14773260,
            "earnings_growth_rate": None,
        },
    }
    llm = FakeLLM([response, response, response, response])
    text = (
        "Operating income 133,050\n"
        "Other income/(expense), net (321)\n"
        "Depreciation and amortization 11,698\n"
        "Total shareholders’ equity 73,733\n"
        "Term debt 12,350\n"
        "Term debt 78,328\n"
        "Cash used in financing activities (121,983)\n"
        "Net income 112,010 93,736 96,995\n"
        "The closing price of the Company's common stock as reported by Nasdaq was $222.91.\n"
    )
    data = extract_financials_with_fallback(
        text,
        llm,
        parallel=False,
        min_fields=1,
        enrichment_text=text,
        company_name="Apple Inc.",
    )
    assert data["income_statement"]["ebit"] == 133050
    assert data["income_statement"]["interest_expense"] == 321
    assert data["income_statement"]["ebitda"] == 144748
    assert data["balance_sheet"]["shareholders_equity"] == 73733
    assert data["balance_sheet"]["total_debt"] == 90678
    assert data["cash_flow"]["financing_cash_flow"] == -121983
    assert data["market_data"]["share_price"] == 222.91
    assert data["market_data"]["earnings_growth_rate"] > 0


def test_extract_financing_cash_flow_from_balance_identity_when_summary_row_missing():
    response = {
        "income_statement": {"revenue": 100, "cost_of_goods_sold": 20, "operating_income": 30, "net_income": 10},
        "balance_sheet": {"total_assets": 200},
        "cash_flow": {
            "operating_cash_flow": 111482,
            "investing_cash_flow": 15195,
            "financing_cash_flow": None,
        },
        "market_data": {},
    }
    llm = FakeLLM([response, response, response, response])
    text = (
        "CONSOLIDATED STATEMENTS OF CASH FLOWS\n"
        "Cash, cash equivalents, and restricted cash and cash equivalents, beginning balances $ 29,943\n"
        "Cash, cash equivalents, and restricted cash and cash equivalents, ending balances $ 35,934\n"
    )
    data = extract_financials_with_fallback(
        text,
        llm,
        parallel=False,
        min_fields=1,
        enrichment_text=text,
        company_name="Apple Inc.",
    )
    assert data["cash_flow"]["financing_cash_flow"] == -120686


def test_missing_interest_expense_keeps_undisclosed_note():
    response = {
        "income_statement": {
            "revenue": 1000,
            "cost_of_goods_sold": 600,
            "operating_income": 100,
            "net_income": 80,
            "ebit": 100,
            "interest_expense": None,
            "ebitda": 120,
        },
        "balance_sheet": {
            "total_assets": 2000,
            "shareholders_equity": 900,
            "total_debt": 500,
        },
        "cash_flow": {},
        "market_data": {},
    }
    llm = FakeLLM([response, response, response, response])
    data = extract_financials_with_fallback(
        "Operating income 100; no interest expense disclosure.",
        llm,
        parallel=False,
        min_fields=1,
        enrichment_text="Operating income 100; no interest expense disclosure.",
        company_name="Apple Inc.",
    )
    metrics, notes = compute_financial_metrics(data)
    assert metrics["leverage"]["interest_coverage"] is None
    assert "income_statement.interest_expense 未披露" in notes


def test_compute_financial_metrics_marks_uncomputable_ratios_as_none():
    data = {
        "income_statement": {
            "revenue": None,
            "cost_of_goods_sold": None,
            "operating_income": None,
            "net_income": 112010,
            "ebit": None,
            "interest_expense": None,
            "ebitda": None,
        },
        "balance_sheet": {
            "total_assets": 359241,
            "current_assets": 147957,
            "inventory": 5718,
            "cash_and_equivalents": 35934,
            "current_liabilities": 165631,
            "shareholders_equity": 73733,
            "total_debt": 90678,
            "accounts_receivable": 39777,
        },
        "cash_flow": {
            "operating_cash_flow": 111482,
            "investing_cash_flow": 15195,
            "financing_cash_flow": -120686,
        },
        "market_data": {
            "share_price": 220.22,
            "shares_outstanding": 14773260,
            "earnings_growth_rate": 0.19,
        },
    }
    metrics, notes = compute_financial_metrics(data)
    assert metrics["efficiency"]["inventory_turnover"] is None
    assert metrics["efficiency"]["receivables_turnover"] is None
    assert metrics["efficiency"]["asset_turnover"] is None
    assert any("efficiency.inventory_turnover" in note for note in notes)


def test_extract_financials_with_fallback_enriches_income_statement_from_text_patterns():
    response = {
        "income_statement": {
            "revenue": None,
            "cost_of_goods_sold": None,
            "operating_income": None,
            "net_income": 93736,
            "ebit": None,
            "interest_expense": None,
            "ebitda": None,
        },
        "balance_sheet": {
            "total_assets": 352755,
            "current_assets": 143566,
            "inventory": 6331,
            "cash_and_equivalents": 29965,
            "current_liabilities": 145308,
            "shareholders_equity": 62146,
            "total_debt": 111088,
            "accounts_receivable": 29508,
        },
        "cash_flow": {
            "operating_cash_flow": 118254,
            "investing_cash_flow": -3709,
            "financing_cash_flow": -123482,
        },
        "market_data": {
            "share_price": 220.22,
            "shares_outstanding": 14773260,
            "earnings_growth_rate": 0.19,
        },
    }
    llm = FakeLLM([response, response, response, response])
    text = (
        "CONSOLIDATED STATEMENTS OF OPERATIONS\n"
        "Total net sales 391,035 383,285 394,328\n"
        "Total cost of sales 223,546 214,137 223,546\n"
        "Operating income 123,216 114,301 119,437\n"
    )
    data = extract_financials_with_fallback(
        text,
        llm,
        parallel=False,
        min_fields=1,
        enrichment_text=text,
        company_name="Apple Inc.",
    )
    assert data["income_statement"]["revenue"] == 391035
    assert data["income_statement"]["cost_of_goods_sold"] == 223546
    assert data["income_statement"]["operating_income"] == 123216


def test_sec_companyfacts_values_override_inconsistent_local_units(monkeypatch):
    from src import financials

    monkeypatch.setattr(financials, "_sec_enabled", lambda: True)
    monkeypatch.setattr(financials, "_resolve_sec_cik", lambda company_name, source_text: "0000320193")

    payload = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [{"val": 391035000000, "fy": 2024, "fp": "FY", "form": "10-K"}]}
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"val": 93736000000, "fy": 2024, "fp": "FY", "form": "10-K"}]}
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [{"val": 14776398000, "fy": 2024, "fp": "FY", "form": "10-K"}]}
                }
            },
        }
    }
    monkeypatch.setattr(financials, "_http_get_json", lambda *_args, **_kwargs: payload)

    income = {"revenue": None, "net_income": 112010}
    balance = {}
    cash = {}
    market = {"shares_outstanding": 14773260}

    financials._fill_financials_from_sec_companyfacts(
        income,
        balance,
        cash,
        market,
        company_name="Apple Inc.",
        source_text="Apple Inc.",
    )

    assert income["revenue"] == 391035000000
    assert income["net_income"] == 93736000000
    assert market["shares_outstanding"] == 14776398000
