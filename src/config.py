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
    tavily_api_key: str
    debug: bool


def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
        llm_model_name=os.getenv("LLM_MODEL_NAME", "deepseek-chat"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )
