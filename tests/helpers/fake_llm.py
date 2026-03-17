import time
from typing import Any, Optional


class FakeLLM:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if not self._responses:
            raise RuntimeError("FakeLLM has no more responses")
        time.sleep(0.01)
        return self._responses.pop(0)
