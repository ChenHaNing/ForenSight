from src.financials import compute_financial_metrics


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
    assert notes == []
    assert metrics["profitability"]["gross_margin"] == 0.4
    assert metrics["liquidity"]["current_ratio"] == 2.0
    assert metrics["leverage"]["debt_to_equity"] == 500.0 / 900.0
    assert metrics["efficiency"]["receivables_turnover"] == 1000.0 / 250.0
