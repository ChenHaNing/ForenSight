from src.agents import run_agent
from src.llm_client import FakeLLM


def test_run_agent_returns_report_schema():
    fake_report = {
        "risk_level": "medium",
        "risk_points": ["point1"],
        "evidence": ["evidence1"],
        "reasoning_summary": "summary",
        "suggestions": ["suggestion"],
        "confidence": 0.6,
    }
    llm = FakeLLM([fake_report])
    workpaper = {
        "fraud_type_A_block": "A-block",
        "fraud_type_B_block": "B-block",
        "company_profile": "Example Co.",
    }
    report = run_agent("fraud_type_A", workpaper, llm)

    for key in [
        "risk_level",
        "risk_points",
        "evidence",
        "reasoning_summary",
        "suggestions",
        "confidence",
    ]:
        assert key in report
    assert report["risk_level"] == "medium"


class SpyLLM:
    def __init__(self, response):
        self.response = response
        self.last_user_prompt = None

    def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
        self.last_user_prompt = user_prompt
        return self.response


class FakeTavily:
    def __init__(self, results):
        self.results = results

    @property
    def enabled(self):
        return True

    def search(self, query, max_results=5):
        return self.results


class TraceTavily:
    def __init__(self, results):
        self.results = results
        self.queries = []

    @property
    def enabled(self):
        return True

    def search(self, query, max_results=5):
        self.queries.append(query)
        return self.results


def test_run_agent_includes_tavily_results_in_prompt():
    report = {
        "risk_level": "low",
        "risk_points": [],
        "evidence": [],
        "reasoning_summary": "summary",
        "suggestions": [],
        "confidence": 0.2,
    }
    llm = SpyLLM(report)
    workpaper = {
        "company_profile": "Example Co.",
        "fraud_type_A_block": "A-block",
    }
    tavily = FakeTavily(
        [
            {"title": "News A", "url": "https://a.example", "content": "Snippet A"},
            {"title": "News B", "url": "https://b.example", "content": "Snippet B"},
        ]
    )
    run_agent("fraud_type_A", workpaper, llm, tavily_client=tavily)

    assert "外部检索摘要" in llm.last_user_prompt
    assert "News A" in llm.last_user_prompt
    assert "Snippet B" in llm.last_user_prompt


def test_run_agent_attaches_external_search_results():
    report = {
        "risk_level": "low",
        "risk_points": [],
        "evidence": [],
        "reasoning_summary": "summary",
        "suggestions": [],
        "confidence": 0.2,
    }
    llm = SpyLLM(report)
    workpaper = {
        "company_profile": "Example Co.",
        "fraud_type_A_block": "A-block",
    }
    tavily = FakeTavily(
        [
            {"title": "News A", "url": "https://a.example", "content": "Snippet A"},
        ]
    )
    result = run_agent("fraud_type_A", workpaper, llm, tavily_client=tavily)
    assert "_external_search" in result
    assert result["_external_search"][0]["title"] == "News A"


class SequenceLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
        self.calls += 1
        return self.responses.pop(0)


def test_run_agent_react_retries_when_missing():
    llm = SequenceLLM(
        [
            {
                "risk_level": "unknown",
                "risk_points": [],
                "evidence": [],
                "reasoning_summary": "信息不足，无法评估。",
                "suggestions": [],
                "confidence": 0.1,
            },
            {
                "risk_level": "low",
                "risk_points": ["point"],
                "evidence": ["evidence"],
                "reasoning_summary": "summary",
                "suggestions": ["suggestion"],
                "confidence": 0.6,
            },
        ]
    )
    workpaper = {
        "company_profile": "Example Co.",
        "fraud_type_A_block": "A-block",
        "industry_comparables": "",
    }
    tavily = FakeTavily(
        [
            {"title": "Peer Report", "url": "https://peer.example", "content": "Peers"},
        ]
    )
    report = run_agent("fraud_type_A", workpaper, llm, tavily_client=tavily, react_retry=True)
    assert llm.calls == 2
    assert report["risk_level"] == "low"


def test_run_agent_includes_context_capsule():
    llm = SpyLLM(
        {
            "risk_level": "low",
            "risk_points": [],
            "evidence": [],
            "reasoning_summary": "summary",
            "suggestions": [],
            "confidence": 0.2,
        }
    )
    workpaper = {
        "company_profile": "Example Co.",
        "fraud_type_A_block": "A-block",
        "context_capsule": "背景要点：业务与行业概览",
    }
    run_agent("fraud_type_A", workpaper, llm)
    assert "背景要点" in llm.last_user_prompt


def test_run_agent_filters_external_results_by_company():
    report = {
        "risk_level": "low",
        "risk_points": [],
        "evidence": [],
        "reasoning_summary": "summary",
        "suggestions": [],
        "confidence": 0.2,
    }
    llm = SpyLLM(report)
    workpaper = {
        "company_profile": "Apple Inc.",
        "fraud_type_A_block": "A-block",
    }
    tavily = FakeTavily(
        [
            {"title": "Starbucks results", "url": "https://b.example", "content": "Starbucks"},
            {"title": "Apple Inc. 10-K", "url": "https://a.example", "content": "Apple Inc."},
        ]
    )
    run_agent("fraud_type_A", workpaper, llm, tavily_client=tavily)
    assert "Starbucks" not in llm.last_user_prompt


def test_run_agent_prompt_contains_financial_context_for_specialized_agent():
    report = {
        "risk_level": "low",
        "risk_points": [],
        "evidence": [],
        "reasoning_summary": "summary",
        "suggestions": [],
        "confidence": 0.2,
    }
    llm = SpyLLM(report)
    workpaper = {
        "company_profile": "Example Co.",
        "fraud_type_A_block": "未提供相关识别特征。",
        "financial_summary": "收入和利润保持增长。",
        "financial_metrics": {"efficiency": {"inventory_turnover": 12.0}},
        "metrics_notes": ["income_statement.revenue 未披露"],
    }
    run_agent("fraud_type_A", workpaper, llm)
    assert "financial_metrics" in llm.last_user_prompt
    assert "metrics_notes" in llm.last_user_prompt


def test_run_agent_retry_uses_metric_gap_terms_for_queries():
    llm = SequenceLLM(
        [
            {
                "risk_level": "unknown",
                "risk_points": [],
                "evidence": [],
                "reasoning_summary": "信息不足，无法评估存货减值风险。",
                "suggestions": [],
                "confidence": 0.1,
            },
            {
                "risk_level": "low",
                "risk_points": ["point"],
                "evidence": ["evidence"],
                "reasoning_summary": "summary",
                "suggestions": [],
                "confidence": 0.4,
            },
        ]
    )
    workpaper = {
        "company_profile": "Apple Inc.",
        "fraud_type_B_block": "净利润操纵线索缺失。",
        "industry_comparables": "已披露",
        "metrics_notes": [
            "income_statement.cost_of_goods_sold 未披露",
            "balance_sheet.inventory 未披露",
        ],
    }
    tavily = TraceTavily(
        [
            {"title": "Apple inventory disclosure", "url": "https://a.example", "content": "inventory"},
        ]
    )
    run_agent("fraud_type_B", workpaper, llm, tavily_client=tavily, react_retry=True, max_retries=1)
    joined = " ".join(tavily.queries)
    assert "存货" in joined
    assert "成本" in joined or "cost of sales" in joined.lower()
