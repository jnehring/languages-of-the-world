from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .cache import FileCache

LOG = logging.getLogger("low.scraper.llm")

DEFAULT_MODEL = "gemini-3.5-flash"
MAX_ATTEMPTS = 5
BACKOFF_BASE = 1.5


def _cache_key(model: str, prompt: str) -> str:
    return f"{model}\0{prompt}"


def _call_gemini(api_key: str, model: str, prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    text = response.text
    if text is None:
        return ""
    return text.strip()


def _call_gemini_with_retry(api_key: str, model: str, prompt: str) -> str:
    last_exc: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return _call_gemini(api_key, model, prompt)
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(
                getattr(e, "response", None), "status_code", None
            )
            if status is not None and status != 429 and int(status) < 500:
                raise
            last_exc = e
            LOG.warning("Gemini attempt %d failed: %s", attempt + 1, e)
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_BASE * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


class GeminiClient:
    """Cached Gemini wrapper used by the scrape pipeline."""

    def __init__(
        self,
        cache: FileCache,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        *,
        use_cache: bool = True,
    ) -> None:
        self._cache = cache
        self._model = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._use_cache = use_cache
        if not self._api_key:
            raise SystemExit("GEMINI_API_KEY environment variable is required.")

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt: str) -> str:
        key = _cache_key(self._model, prompt)

        def produce() -> str:
            return _call_gemini_with_retry(self._api_key, self._model, prompt)

        if self._use_cache:
            result = self._cache.get_or_set_text("llm", key, produce)
            return result or ""
        return produce()
