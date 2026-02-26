import requests
import pytest

from src.llm_client import LLMClient


def test_llm_client_retries_on_timeout():
    calls = {"count": 0}

    def fake_post(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.Timeout("timeout")
        class Resp:
            def raise_for_status(self):
                return None
            def json(self):
                return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}
        return Resp()

    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="key",
        base_url="https://api.deepseek.com",
        timeout=1,
        max_retries=3,
        post_fn=fake_post,
    )
    result = client.generate_json("sys", "user")
    assert result["ok"] is True
    assert calls["count"] == 3


def test_llm_client_rejects_non_deepseek_provider():
    client = LLMClient(
        provider="zhipu",
        model="GLM-4.7",
        api_key="zhipu-key",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
    )
    with pytest.raises(ValueError, match="Unsupported provider"):
        client.generate_json("sys", "user")


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/",
        "https://api.deepseek.com/v1",
        "https://api.deepseek.com/v1/",
        "https://api.deepseek.com/v1/chat/completions",
    ],
)
def test_llm_client_normalizes_base_url_for_chat_completion_endpoint(base_url):
    called = {"url": ""}

    def fake_post(url, **_kwargs):
        called["url"] = url

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

        return Resp()

    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="key",
        base_url=base_url,
        post_fn=fake_post,
    )

    result = client.generate_json("sys", "user")
    assert result["ok"] is True
    assert called["url"] == "https://api.deepseek.com/v1/chat/completions"
