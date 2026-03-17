import pytest
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


def test_llm_client_surfaces_http_400_context_length_exceeded():
    def fake_post(*_args, **_kwargs):
        response = requests.Response()
        response.status_code = 400
        response.url = "https://api.deepseek.com/v1/chat/completions"
        response._content = b'{"error":{"message":"context_length_exceeded"}}'
        raise requests.HTTPError("400 Client Error", response=response)

    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="key",
        base_url="https://api.deepseek.com",
        post_fn=fake_post,
    )

    with pytest.raises(RuntimeError, match="context window exceeded"):
        client.generate_json("sys", "user")


def test_llm_client_surfaces_http_400_other_error():
    def fake_post(*_args, **_kwargs):
        response = requests.Response()
        response.status_code = 400
        response.url = "https://api.deepseek.com/v1/chat/completions"
        response._content = b'{"error":{"message":"invalid_request"}}'
        raise requests.HTTPError("400 Client Error", response=response)

    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="key",
        base_url="https://api.deepseek.com",
        post_fn=fake_post,
    )

    with pytest.raises(RuntimeError, match="LLM API HTTP 400"):
        client.generate_json("sys", "user")


def test_llm_client_retries_on_429(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = {"count": 0}

    def fake_post(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] <= 2:
            response = requests.Response()
            response.status_code = 429
            response.url = "https://api.deepseek.com/v1/chat/completions"
            response._content = b'{"error":"rate limited"}'
            raise requests.HTTPError("429 Too Many Requests", response=response)

        class Resp:
            def raise_for_status(self):
                return None
            def json(self):
                return {"choices": [{"message": {"content": '{"ok": true}'}}]}
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


def test_llm_client_sends_response_format():
    captured = {}

    def fake_post(url, **kwargs):
        captured["payload"] = kwargs.get("json", {})

        class Resp:
            def raise_for_status(self):
                return None
            def json(self):
                return {"choices": [{"message": {"content": '{"ok": true}'}}]}
        return Resp()

    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="key",
        base_url="https://api.deepseek.com",
        post_fn=fake_post,
    )
    client.generate_json("sys", "user")
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_llm_client_schema_hint_in_system_prompt():
    captured = {}

    def fake_post(url, **kwargs):
        captured["payload"] = kwargs.get("json", {})

        class Resp:
            def raise_for_status(self):
                return None
            def json(self):
                return {"choices": [{"message": {"content": '{"a": 1}'}}]}
        return Resp()

    client = LLMClient(
        provider="deepseek",
        model="deepseek-chat",
        api_key="key",
        base_url="https://api.deepseek.com",
        post_fn=fake_post,
    )
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    client.generate_json("sys", "user", schema=schema)
    messages = captured["payload"]["messages"]
    # Schema hint should be in system prompt, not user prompt
    assert "schema" in messages[0]["content"].lower()
    assert "schema" not in messages[1]["content"].lower()
