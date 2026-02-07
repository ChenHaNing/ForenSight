from src.financials import extract_financial_statements_parallel, extract_financials_with_fallback


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
        return self.responses.pop(0)


def test_extract_financial_statements_parallel_returns_sections():
    llm = FakeLLM([
        {"income_statement": {"revenue": 1000}, "balance_sheet": {}, "cash_flow": {}, "market_data": {}},
        {"income_statement": {}, "balance_sheet": {"total_assets": 2000}, "cash_flow": {}, "market_data": {}},
        {"income_statement": {}, "balance_sheet": {}, "cash_flow": {"operating_cash_flow": 300}, "market_data": {}},
        {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "market_data": {"share_price": 100}},
    ])
    data = extract_financial_statements_parallel("text", llm, parallel=False)
    assert data["income_statement"]["revenue"] == 1000
    assert data["balance_sheet"]["total_assets"] == 2000
    assert data["cash_flow"]["operating_cash_flow"] == 300
    assert data["market_data"]["share_price"] == 100


def test_extract_financials_with_fallback_runs_second_pass():
    llm = FakeLLM([
        {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "market_data": {}},
        {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "market_data": {}},
        {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "market_data": {}},
        {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "market_data": {}},
        {
            "income_statement": {"revenue": 1000},
            "balance_sheet": {"total_assets": 2000},
            "cash_flow": {"operating_cash_flow": 300},
            "market_data": {},
        },
    ])
    data = extract_financials_with_fallback("text", llm, parallel=False, min_fields=1)
    assert data["income_statement"]["revenue"] == 1000
