import time
from typing import Any, Dict, List, Optional


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
