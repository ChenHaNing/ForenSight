"""Tests for src.token_utils — token estimation and prompt truncation."""

from src.token_utils import estimate_tokens, fit_to_token_budget, truncate_json_for_prompt


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_pure_ascii(self):
        text = "hello world"  # 11 ASCII chars → ~11/4 + 1 = 3
        tokens = estimate_tokens(text)
        assert tokens >= 1
        assert tokens <= 10

    def test_pure_chinese(self):
        text = "你好世界"  # 4 CJK chars → ~4/1.5 + 1 ≈ 3
        tokens = estimate_tokens(text)
        assert tokens >= 2
        assert tokens <= 10

    def test_mixed_text(self):
        text = "Hello你好World世界"
        tokens = estimate_tokens(text)
        assert tokens > 0

    def test_scales_with_length(self):
        short = estimate_tokens("a" * 100)
        long = estimate_tokens("a" * 1000)
        assert long > short


class TestFitToTokenBudget:
    def test_short_text_unchanged(self):
        text = "short text"
        result = fit_to_token_budget(text, 1000)
        assert result == text

    def test_truncation_preserves_head_and_tail(self):
        head = "HEAD_MARKER_" * 50
        tail = "_TAIL_MARKER" * 50
        middle = "x" * 5000
        text = head + middle + tail
        result = fit_to_token_budget(text, 100)
        assert "HEAD_MARKER_" in result
        assert "_TAIL_MARKER" in result
        assert "中间内容已截断" in result

    def test_zero_budget_returns_empty(self):
        assert fit_to_token_budget("anything", 0) == ""

    def test_negative_budget_returns_empty(self):
        assert fit_to_token_budget("anything", -5) == ""

    def test_result_shorter_than_original(self):
        text = "a" * 10000
        result = fit_to_token_budget(text, 50)
        assert len(result) < len(text)


class TestTruncateJsonForPrompt:
    def test_small_dict(self):
        data = {"key": "value"}
        result = truncate_json_for_prompt(data, 1000)
        assert '"key"' in result
        assert '"value"' in result

    def test_large_dict_truncated(self):
        data = {"field": "x" * 50000}
        result = truncate_json_for_prompt(data, 500)
        assert len(result) < 50000
        assert "中间内容已截断" in result

    def test_chinese_content(self):
        data = {"描述": "这是一段很长的中文" * 500}
        result = truncate_json_for_prompt(data, 200)
        assert len(result) < len("这是一段很长的中文") * 500

    def test_list_data(self):
        data = [{"id": i, "text": f"item {i}"} for i in range(10)]
        result = truncate_json_for_prompt(data, 5000)
        assert "item 0" in result
