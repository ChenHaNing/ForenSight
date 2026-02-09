import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class AppConfig:
    llm_provider: str
    llm_model_name: str
    llm_api_key: str
    llm_base_url: str
    llm_timeout_seconds: int
    llm_max_retries: int
    agent_max_concurrency: int
    tavily_api_key: str
    debug: bool


def load_config() -> AppConfig:
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    if provider != "deepseek":
        provider = "deepseek"

    try:
        agent_max_concurrency = int(os.getenv("AGENT_MAX_CONCURRENCY", "4"))
    except ValueError:
        agent_max_concurrency = 4
    agent_max_concurrency = max(1, min(agent_max_concurrency, 16))

    return AppConfig(
        llm_provider=provider,
        llm_model_name=os.getenv("LLM_MODEL_NAME", "deepseek-chat"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        agent_max_concurrency=agent_max_concurrency,
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )
