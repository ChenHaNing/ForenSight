from typing import List


SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}


def _chunk_text(text: str, chunk_size: int) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


def summarize_text(text: str, llm, chunk_size: int = 6000, max_chunks: int = 2) -> str:
    chunks = _chunk_text(text, chunk_size)[:max_chunks]
    partials: List[str] = []
    for chunk in chunks:
        resp = llm.generate_json(
            "你是财务文档摘要助手。",
            f"请对以下文本生成简明摘要（不超过200字）：\n{chunk}",
            SUMMARY_SCHEMA,
        )
        partials.append(resp.get("summary", ""))

    if len(partials) == 1:
        return partials[0]

    merged = "\n".join(partials)
    final = llm.generate_json(
        "你是财务文档摘要助手。",
        f"请对以下分段摘要再次压缩为最终摘要（不超过300字）：\n{merged}",
        SUMMARY_SCHEMA,
    )
    return final.get("summary", "")
