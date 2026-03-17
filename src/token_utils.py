"""Token estimation and prompt truncation utilities.

Uses heuristic character-to-token ratios to estimate token counts
without requiring a tokenizer dependency.  Conservative (overestimates)
to prevent context-window overflow.
"""

import json
from typing import Any

# DeepSeek V3 context window ~64K tokens; leave room for output.
DEFAULT_MAX_PROMPT_TOKENS = 56000


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    Heuristic: CJK chars ≈ 1.5 chars/token, ASCII ≈ 4 chars/token.
    """
    if not text:
        return 0
    cjk = 0
    ascii_count = 0
    for ch in text:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0xF900 <= cp <= 0xFAFF
            or 0x2E80 <= cp <= 0x2EFF
            or 0x20000 <= cp <= 0x2A6DF
        ):
            cjk += 1
        else:
            ascii_count += 1
    return int(cjk / 1.5 + ascii_count / 4) + 1


def fit_to_token_budget(text: str, max_tokens: int) -> str:
    """Truncate *text* with head+tail preservation to fit a token budget."""
    if max_tokens <= 0:
        return ""
    current = estimate_tokens(text)
    if current <= max_tokens:
        return text

    ratio = max_tokens / current
    target_chars = int(len(text) * ratio * 0.92)  # 8 % safety margin
    if target_chars <= 0:
        return ""
    half = target_chars // 2
    head = text[:half]
    tail = text[-(target_chars - half):]
    return (
        head
        + "\n\n[... 中间内容已截断以控制上下文长度 ...]\n\n"
        + tail
    )


def truncate_json_for_prompt(data: Any, max_tokens: int) -> str:
    """Serialize *data* to JSON and truncate if over budget."""
    serialized = json.dumps(data, ensure_ascii=False)
    return fit_to_token_budget(serialized, max_tokens)
