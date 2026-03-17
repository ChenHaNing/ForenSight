import json
import logging
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)


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
        self.base_url = _normalize_base_url(base_url)
        self.timeout = timeout
        self.max_retries = max_retries
        self._post = post_fn or requests.post

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        provider = self.provider.lower().strip()
        if provider == "deepseek":
            result = self._openai_chat_completion(
                endpoint_path="/v1/chat/completions",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                temperature=temperature,
            )
            if schema:
                _soft_validate(result, schema)
            return result
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _openai_chat_completion(
        self,
        endpoint_path: str,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict[str, Any]],
        temperature: float,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint_path}"
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
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt + schema_hint},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = self._post_with_retry(url, headers, payload)
        content = data["choices"][0]["message"]["content"]
        return _safe_json_parse(content)

    def _post_with_retry(self, url: str, headers: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        resp = None
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.HTTPError as exc:
                response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)
                detail = ""
                if response is not None:
                    body = (response.text or "").strip()
                    if body:
                        detail = f" | response: {body[:800]}"

                # HTTP 429 (rate limit) — retry with backoff
                if status == 429:
                    retry_after = _parse_retry_after(response)
                    wait = retry_after if retry_after else min(2 ** (attempt + 1), 8)
                    logger.warning("LLM API rate limited (429), retrying in %.1fs", wait)
                    last_err = exc
                    time.sleep(wait)
                    continue

                # HTTP 400 with context_length_exceeded — clear error
                if status == 400 and response is not None:
                    body_text = (response.text or "").lower()
                    if "context_length_exceeded" in body_text:
                        raise RuntimeError(
                            f"LLM context window exceeded at {url}{detail}"
                        ) from exc

                raise RuntimeError(f"LLM API HTTP {status or 'unknown'} at {url}{detail}") from exc
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_err = exc
                time.sleep(min(2 ** attempt, 4))
        if last_err is not None:
            raise RuntimeError(f"LLM request failed after {self.max_retries + 1} attempts") from last_err
        raise RuntimeError("LLM request failed without response payload")


def _safe_json_parse(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _parse_retry_after(response) -> Optional[float]:
    """Extract wait time from Retry-After header, if present."""
    if response is None:
        return None
    raw = getattr(response, "headers", {}).get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _soft_validate(data: dict[str, Any], schema: dict[str, Any]) -> None:
    """Warn if *data* doesn't match *schema*. Never raises."""
    try:
        import jsonschema
        jsonschema.validate(data, schema)
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("LLM response failed schema validation (soft): %s", exc)


def _normalize_base_url(base_url: str) -> str:
    """Accept root URL, /v1 URL, or full chat completions endpoint and normalize."""
    raw = (base_url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/")

    path = parsed.path.rstrip("/")
    lowered = path.lower()
    chat_suffix = "/chat/completions"
    v1_suffix = "/v1"

    if lowered.endswith(chat_suffix):
        path = path[: -len(chat_suffix)]
        lowered = path.lower()
    if lowered.endswith(v1_suffix):
        path = path[: -len(v1_suffix)]

    normalized = parsed._replace(path=path, params="", query="", fragment="")
    return urlunparse(normalized).rstrip("/")
