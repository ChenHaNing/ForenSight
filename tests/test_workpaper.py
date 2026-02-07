from src.workpaper import (
    build_workpaper_from_text,
    WORKPAPER_SCHEMA,
    react_enrich_workpaper,
    build_context_pack,
    build_context_capsule,
    filter_external_results_by_company,
    sanitize_company_scope_fields,
)
from src.llm_client import FakeLLM


def test_build_workpaper_from_text_returns_required_fields():
    fake_response = {
        "company_profile": "Example Co.",
        "financial_summary": "Summary",
        "risk_disclosures": "Risks",
        "major_events": "Events",
        "governance_signals": "Governance",
        "industry_comparables": "Peers",
        "announcements_summary": "Announcements",
        "related_parties_summary": "Related parties",
        "industry_benchmark_summary": "Benchmark",
        "external_search_summary": "External summary",
        "financial_metrics": {"gross_margin": 0.4},
        "metrics_notes": ["notes"],
        "fraud_type_A_block": "A-block",
        "fraud_type_B_block": "B-block",
        "fraud_type_C_block": "C-block",
        "fraud_type_D_block": "D-block",
        "fraud_type_E_block": "E-block",
        "fraud_type_F_block": "F-block",
        "evidence": [
            {"quote": "Sample evidence", "source": "p1"}
        ],
    }
    llm = FakeLLM([fake_response])
    workpaper = build_workpaper_from_text(
        "sample text",
        llm,
        financial_data={
            "income_statement": {"revenue": 1000, "cost_of_goods_sold": 600},
            "balance_sheet": {"total_assets": 2000, "shareholders_equity": 900},
            "cash_flow": {},
            "market_data": {},
        },
    )

    for key in [
        "company_profile",
        "financial_summary",
        "risk_disclosures",
        "major_events",
        "governance_signals",
        "industry_comparables",
        "announcements_summary",
        "related_parties_summary",
        "industry_benchmark_summary",
        "external_search_summary",
        "financial_metrics",
        "metrics_notes",
        "fraud_type_A_block",
        "fraud_type_B_block",
        "fraud_type_C_block",
        "fraud_type_D_block",
        "fraud_type_E_block",
        "fraud_type_F_block",
    ]:
        assert key in workpaper
    assert workpaper["company_profile"] == "Example Co."
    assert "evidence" in workpaper


def test_workpaper_schema_includes_new_fields():
    required = set(WORKPAPER_SCHEMA.get("required", []))
    for key in [
        "announcements_summary",
        "related_parties_summary",
        "industry_benchmark_summary",
        "external_search_summary",
        "financial_metrics",
        "metrics_notes",
        "fraud_type_C_block",
        "fraud_type_D_block",
        "fraud_type_E_block",
        "fraud_type_F_block",
    ]:
        assert key in required


class CaptureLLM:
    def __init__(self, response):
        self.response = response
        self.user_prompt = ""

    def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
        self.user_prompt = user_prompt
        return self.response


def test_build_workpaper_truncates_long_input():
    long_text = "A" * 70000
    fake_response = {
        "company_profile": "Example Co.",
        "financial_summary": "Summary",
        "risk_disclosures": "Risks",
        "major_events": "Events",
        "governance_signals": "Governance",
        "industry_comparables": "Peers",
        "announcements_summary": "Announcements",
        "related_parties_summary": "Related parties",
        "industry_benchmark_summary": "Benchmark",
        "external_search_summary": "External summary",
        "fraud_type_A_block": "A-block",
        "fraud_type_B_block": "B-block",
        "fraud_type_C_block": "C-block",
        "fraud_type_D_block": "D-block",
        "fraud_type_E_block": "E-block",
        "fraud_type_F_block": "F-block",
        "evidence": [{"quote": "Sample", "source": "p1"}],
    }
    llm = CaptureLLM(fake_response)
    build_workpaper_from_text(long_text, llm)
    assert len(llm.user_prompt) < len(long_text)


def test_build_workpaper_includes_revenue_context_and_company_hint():
    fake_response = {
        "company_profile": "Example Co.",
        "financial_summary": "Summary",
        "risk_disclosures": "Risks",
        "major_events": "Events",
        "governance_signals": "Governance",
        "industry_comparables": "Peers",
        "announcements_summary": "Announcements",
        "related_parties_summary": "Related parties",
        "industry_benchmark_summary": "Benchmark",
        "external_search_summary": "External summary",
        "fraud_type_A_block": "A-block",
        "fraud_type_B_block": "B-block",
        "fraud_type_C_block": "C-block",
        "fraud_type_D_block": "D-block",
        "fraud_type_E_block": "E-block",
        "fraud_type_F_block": "F-block",
        "evidence": [{"quote": "Sample", "source": "p1"}],
    }
    llm = CaptureLLM(fake_response)
    build_workpaper_from_text(
        "sample text",
        llm,
        revenue_context="Net sales by product",
        company_name="Apple Inc.",
    )
    assert "Net sales by product" in llm.user_prompt
    assert "Apple Inc." in llm.user_prompt


def test_filter_external_results_by_company():
    company = "APPLE INC."
    results = [
        {"title": "Apple supply chain update", "content": "Apple Inc. announced...", "url": "https://a.example"},
        {"title": "Starbucks revenue", "content": "Starbucks reported...", "url": "https://b.example"},
    ]
    filtered = filter_external_results_by_company(results, company)
    assert len(filtered) == 1
    assert "Apple" in filtered[0]["title"]


def test_filter_external_results_returns_original_when_no_match():
    company = "APPLE INC."
    results = [
        {"title": "Samsung earnings", "content": "Samsung reported...", "url": "https://s.example"},
    ]
    filtered = filter_external_results_by_company(results, company)
    assert filtered == results


def test_sanitize_company_scope_fields_rewrites_fields():
    class SimpleLLM:
        def __init__(self, response):
            self.response = response

        def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
            return self.response

    workpaper = {
        "industry_comparables": "三星、谷歌",
        "external_search_summary": "瑞幸咖啡案例",
        "fraud_type_A_block": "瑞幸咖啡虚构交易",
    }
    llm = SimpleLLM(
        {
            "industry_comparables": "消费电子行业平均水平对比",
            "external_search_summary": "未披露",
            "fraud_type_A_block": "未披露",
        }
    )
    updated = sanitize_company_scope_fields(workpaper, "Apple Inc.", llm)
    assert "三星" not in updated["industry_comparables"]
    assert updated["fraud_type_A_block"] == "未披露"


class FakeTavily:
    def __init__(self, results):
        self.results = results
        self.queries = []

    @property
    def enabled(self):
        return True

    def search(self, query, max_results=5):
        self.queries.append(query)
        return self.results


def test_react_enrich_workpaper_fills_missing_fields():
    class SimpleLLM:
        def __init__(self, response):
            self.response = response

        def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
            return self.response

    llm = SimpleLLM(
        {
            "company_profile": "Example Co.",
            "industry_comparables": "Peer A, Peer B",
            "industry_benchmark_summary": "Benchmark info",
            "external_search_summary": "External info",
        }
    )
    workpaper = {
        "company_profile": "",
        "industry_comparables": "",
        "industry_benchmark_summary": "",
        "external_search_summary": "",
    }
    tavily = FakeTavily(
        [
            {"title": "Company Profile", "url": "https://c.example", "content": "Profile"},
        ]
    )
    updated = react_enrich_workpaper(workpaper, llm, tavily)
    assert updated["company_profile"] == "Example Co."
    assert updated["industry_comparables"] == "Peer A, Peer B"
    assert tavily.queries


def test_build_context_capsule_contains_company_name():
    pack = {
        "company_name": "APPLE INC.",
        "business_overview": "Consumer electronics and services.",
        "segments": "iPhone, Mac, Services",
        "geographies": "Americas, Europe, Greater China",
        "revenue_mix": "Products and Services",
        "major_products": "iPhone, Mac, iPad",
        "key_accounting_policies": "Revenue recognition",
        "top_risk_factors": "Supply chain, regulation",
        "governance_overview": "Board oversight",
        "audit_controls": "SOX controls",
    }
    capsule = build_context_capsule(pack)
    assert "APPLE INC." in capsule


def test_build_workpaper_replaces_null_metrics_with_computed_values():
    fake_response = {
        "company_profile": "Example Co.",
        "financial_summary": "Summary",
        "risk_disclosures": "Risks",
        "major_events": "Events",
        "governance_signals": "Governance",
        "industry_comparables": "Peers",
        "announcements_summary": "Announcements",
        "related_parties_summary": "Related parties",
        "industry_benchmark_summary": "Benchmark",
        "external_search_summary": "External summary",
        "financial_metrics": None,
        "metrics_notes": None,
        "fraud_type_A_block": "A-block",
        "fraud_type_B_block": "B-block",
        "fraud_type_C_block": "C-block",
        "fraud_type_D_block": "D-block",
        "fraud_type_E_block": "E-block",
        "fraud_type_F_block": "F-block",
        "evidence": [{"quote": "Sample", "source": "p1"}],
    }
    llm = FakeLLM([fake_response])
    workpaper = build_workpaper_from_text(
        "sample text",
        llm,
        financial_data={
            "income_statement": {"revenue": 1000, "cost_of_goods_sold": 600},
            "balance_sheet": {"total_assets": 2000, "shareholders_equity": 900},
            "cash_flow": {},
            "market_data": {},
        },
    )
    assert isinstance(workpaper["financial_metrics"], dict)
    assert workpaper["financial_metrics"]["profitability"]["gross_margin"] == 0.4
    assert isinstance(workpaper["metrics_notes"], list)
