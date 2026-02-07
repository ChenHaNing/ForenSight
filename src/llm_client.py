import json
import time
from typing import Any, Dict, List, Optional, Callable
import requests


class LLMClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 2,
        post_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._post = post_fn or requests.post

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        if self.provider.lower() == "deepseek":
            return self._deepseek_chat(system_prompt, user_prompt, schema, temperature)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _deepseek_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[Dict[str, Any]],
        temperature: float,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        schema_hint = ""
        if schema:
            schema_hint = (
                "\n\nReturn JSON only that matches this schema (no markdown):\n"
                + json.dumps(schema, ensure_ascii=False)
            )
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt + schema_hint},
            ],
        }
        resp = None
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_err = exc
                time.sleep(min(2 ** attempt, 4))
        if resp is None:
            raise last_err
        content = data["choices"][0]["message"]["content"]
        return _safe_json_parse(content)


class FakeLLM:
    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self._responses = list(responses)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        if not self._responses:
            raise RuntimeError("FakeLLM has no more responses")
        time.sleep(0.01)
        return self._responses.pop(0)


def _safe_json_parse(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])
