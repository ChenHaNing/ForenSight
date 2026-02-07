from typing import List, Dict, Any
import os
import requests
from requests import RequestException


class TavilyClient:
    def __init__(self, api_key: str, base_url: str = "https://api.tavily.com") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []
        if os.getenv("PYTEST_CURRENT_TEST"):
            return []
        url = f"{self.base_url}/search"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except RequestException:
            return []
