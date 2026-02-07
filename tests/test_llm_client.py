import requests

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
