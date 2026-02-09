from src.agents import run_agent
from tests.helpers.fake_llm import FakeLLM


def test_run_agent_returns_report_schema():
    fake_report = {
        "risk_level": "medium",
        "risk_points": ["point1"],
        "evidence": ["evidence1"],
        "reasoning_summary": "summary",
        "suggestions": ["suggestion"],
        "confidence": 0.6,
        "research_plan": {
            "need_autonomous_research": False,
            "minimum_rounds": 0,
            "follow_up_queries": [],
            "reason": "evidence is sufficient",
        },
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
        "_react_attempts",
    ]:
        assert key in report
    assert report["risk_level"] == "medium"
    assert report["_react_attempts"] == 0


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
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 1,
                    "follow_up_queries": ["Example Co. annual report risk factor footnote"],
                    "reason": "evidence is missing",
                },
            },
            {
                "risk_level": "low",
                "risk_points": ["point"],
                "evidence": ["evidence"],
                "reasoning_summary": "summary",
                "suggestions": ["suggestion"],
                "confidence": 0.6,
                "research_plan": {
                    "need_autonomous_research": False,
                    "minimum_rounds": 1,
                    "follow_up_queries": [],
                    "reason": "enough evidence",
                },
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
    assert report["_react_attempts"] == 1


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


def test_run_agent_retry_uses_model_follow_up_queries():
    llm = SequenceLLM(
        [
            {
                "risk_level": "medium",
                "risk_points": ["需要补充供应链与关联交易披露证据。"],
                "evidence": [],
                "reasoning_summary": "首轮证据不足，需要进一步外部调查。",
                "suggestions": [],
                "confidence": 0.2,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 1,
                    "follow_up_queries": [
                        "Apple supply chain concentration disclosure annual report",
                        "Apple related party transactions footnote disclosure",
                    ],
                    "reason": "need more filing-level evidence",
                },
            },
            {
                "risk_level": "low",
                "risk_points": ["point"],
                "evidence": ["evidence"],
                "reasoning_summary": "summary",
                "suggestions": [],
                "confidence": 0.4,
                "research_plan": {
                    "need_autonomous_research": False,
                    "minimum_rounds": 1,
                    "follow_up_queries": [],
                    "reason": "evidence is now sufficient",
                },
            },
        ]
    )
    workpaper = {
        "company_profile": "Apple Inc.",
        "fraud_type_B_block": "净利润操纵线索待核实。",
        "industry_comparables": "已披露",
    }
    tavily = TraceTavily(
        [
            {"title": "Apple disclosure", "url": "https://a.example", "content": "disclosure"},
        ]
    )
    run_agent("fraud_type_B", workpaper, llm, tavily_client=tavily, react_retry=True, max_retries=1)
    joined = " ".join(tavily.queries)
    assert "supply chain concentration disclosure" in joined.lower()
    assert "related party transactions footnote" in joined.lower()


def test_run_agent_related_party_disclosure_requires_two_retries_before_give_up():
    llm = SequenceLLM(
        [
            {
                "risk_level": "medium",
                "risk_points": ["关联方交易披露不完整，需进一步核查。"],
                "evidence": ["年报附注未充分披露交易细节。"],
                "reasoning_summary": "关联方交易披露不足，证据仍不充分。",
                "suggestions": ["继续核查关联方交易。"],
                "confidence": 0.3,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 2,
                    "follow_up_queries": [
                        "Apple related party transactions disclosure 10-K footnote",
                        "Apple 关联方交易 披露 附注",
                    ],
                    "reason": "disclosure evidence is insufficient",
                },
            },
            {
                "risk_level": "medium",
                "risk_points": ["关联方交易披露不完整，需进一步核查。"],
                "evidence": ["外部检索未发现充分披露证据。"],
                "reasoning_summary": "已补充检索一次，仍存在披露不完整问题。",
                "suggestions": ["继续核查。"],
                "confidence": 0.35,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 2,
                    "follow_up_queries": [
                        "Apple proxy statement related party transactions DEF 14A",
                    ],
                    "reason": "one round is still not enough",
                },
            },
            {
                "risk_level": "medium",
                "risk_points": ["关联方交易披露不完整，需进一步核查。"],
                "evidence": ["二次检索仍未获得充分披露信息。"],
                "reasoning_summary": "补充检索两次后仍无法证伪该风险点。",
                "suggestions": ["保留风险点并持续关注。"],
                "confidence": 0.4,
                "research_plan": {
                    "need_autonomous_research": False,
                    "minimum_rounds": 2,
                    "follow_up_queries": [],
                    "reason": "two rounds completed without new evidence",
                },
            },
        ]
    )
    workpaper = {
        "company_profile": "Apple Inc.",
        "fraud_type_E_block": "关联方交易披露不完整，可能存在资金回流。",
        "related_parties_summary": "关联方交易披露不足，交易细节不完整。",
        "industry_comparables": "已披露",
    }
    tavily = TraceTavily(
        [
            {"title": "Apple related party note", "url": "https://a.example", "content": "related party"},
        ]
    )
    report = run_agent("fraud_type_E", workpaper, llm, tavily_client=tavily, react_retry=True, max_retries=1)
    assert llm.calls == 3
    assert report["_react_attempts"] == 2
    assert "关联方交易披露不完整" in " ".join(report.get("risk_points", []))
    assert any(("关联方交易" in q) or ("related party" in q.lower()) for q in tavily.queries)


def test_run_agent_react_retry_is_capped_at_two_rounds():
    llm = SequenceLLM(
        [
            {
                "risk_level": "medium",
                "risk_points": ["需要持续补充证据。"],
                "evidence": ["证据不足。"],
                "reasoning_summary": "第一轮证据不足。",
                "suggestions": [],
                "confidence": 0.3,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 4,
                    "follow_up_queries": ["Apple annual report footnote disclosure"],
                    "reason": "need more evidence",
                },
            },
            {
                "risk_level": "medium",
                "risk_points": ["继续调查。"],
                "evidence": ["证据仍不足。"],
                "reasoning_summary": "第一轮补充后仍不足。",
                "suggestions": [],
                "confidence": 0.35,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 4,
                    "follow_up_queries": ["Apple related party transactions DEF 14A"],
                    "reason": "still insufficient",
                },
            },
            {
                "risk_level": "medium",
                "risk_points": ["继续调查。"],
                "evidence": ["证据仍不足。"],
                "reasoning_summary": "第二轮补充后仍不足。",
                "suggestions": [],
                "confidence": 0.38,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 4,
                    "follow_up_queries": ["Apple regulator enforcement disclosure"],
                    "reason": "still insufficient",
                },
            },
            {
                "risk_level": "medium",
                "risk_points": ["继续调查。"],
                "evidence": ["证据仍不足。"],
                "reasoning_summary": "第三轮补充后仍不足。",
                "suggestions": [],
                "confidence": 0.4,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 4,
                    "follow_up_queries": [],
                    "reason": "still insufficient",
                },
            },
            {
                "risk_level": "medium",
                "risk_points": ["继续调查。"],
                "evidence": ["证据仍不足。"],
                "reasoning_summary": "第四轮补充后仍不足。",
                "suggestions": [],
                "confidence": 0.42,
                "research_plan": {
                    "need_autonomous_research": True,
                    "minimum_rounds": 4,
                    "follow_up_queries": [],
                    "reason": "still insufficient",
                },
            },
        ]
    )
    workpaper = {
        "company_profile": "Apple Inc.",
        "fraud_type_B_block": "净利润操纵线索待核实。",
        "industry_comparables": "已披露",
    }
    tavily = TraceTavily(
        [
            {"title": "Apple disclosure", "url": "https://a.example", "content": "disclosure"},
        ]
    )
    report = run_agent("fraud_type_B", workpaper, llm, tavily_client=tavily, react_retry=True, max_retries=5)
    assert llm.calls == 3
    assert report["_react_attempts"] == 2
