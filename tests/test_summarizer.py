from src.summarizer import summarize_text


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def generate_json(self, system_prompt, user_prompt, schema=None, temperature=0.2):
        return self.responses.pop(0)


def test_summarize_text_chunks_and_merge():
    llm = FakeLLM([
        {"summary": "part1"},
        {"summary": "part2"},
        {"summary": "final"},
    ])
    text = "A" * 5000 + "B" * 5000
    result = summarize_text(text, llm, chunk_size=6000)
    assert result == "final"


def test_summarize_text_limits_chunks():
    llm = FakeLLM([
        {"summary": "part1"},
        {"summary": "part2"},
        {"summary": "final"},
    ])
    text = "A" * 4000 + "B" * 4000 + "C" * 4000
    result = summarize_text(text, llm, chunk_size=3000, max_chunks=2)
    assert result == "final"
