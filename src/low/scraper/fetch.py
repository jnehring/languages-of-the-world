from __future__ import annotations

import logging
import time
from typing import List, Optional, Set

import requests

from .cache import FileCache

LOG = logging.getLogger("low.scraper")
_ROBOTS_LOG = LOG.getChild("robots")

SERPER_URL = "https://google.serper.dev/search"
USER_AGENT = (
    "Mozilla/5.0 (compatible; low-scraper/0.1; "
    "+https://github.com/your-org/low)"
)

SERPER_MAX_ATTEMPTS = 5
SERPER_BACKOFF_BASE = 1.5
HTML_FETCH_ATTEMPTS = 3
HTML_FETCH_BACKOFF = 1.0


def _serper_call(api_key: str, query: str) -> dict:
    resp = requests.post(
        SERPER_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": 10},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _serper_call_with_retry(api_key: str, query: str) -> dict:
    last_exc: Exception | None = None
    for attempt in range(SERPER_MAX_ATTEMPTS):
        try:
            return _serper_call(api_key, query)
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", 0)
            if status != 429 and status < 500:
                raise
            last_exc = e
        except requests.RequestException as e:
            last_exc = e
        if attempt < SERPER_MAX_ATTEMPTS - 1:
            time.sleep(SERPER_BACKOFF_BASE * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def serper_search(
    cache: FileCache,
    api_key: str,
    query: str,
    *,
    use_cache: bool = True,
) -> dict:
    if use_cache:
        return cache.get_or_set_json(
            "serper", query, lambda: _serper_call_with_retry(api_key, query)
        )
    return _serper_call_with_retry(api_key, query)


def all_organic_urls(serper_response: dict) -> List[str]:
    organic = serper_response.get("organic", []) or []
    seen: Set[str] = set()
    urls: List[str] = []
    for item in organic:
        link = item.get("link")
        if link and link not in seen:
            seen.add(link)
            urls.append(link)
    return urls


def fetch_url(
    cache: FileCache,
    url: str,
    timeout: int = 30,
    *,
    use_cache: bool = True,
) -> Optional[str]:
    def fetch() -> Optional[str]:
        for attempt in range(HTML_FETCH_ATTEMPTS):
            try:
                resp = requests.get(
                    url,
                    timeout=timeout,
                    headers={"User-Agent": USER_AGENT},
                )
            except requests.RequestException:
                if attempt < HTML_FETCH_ATTEMPTS - 1:
                    time.sleep(HTML_FETCH_BACKOFF * (2 ** attempt))
                    continue
                return None
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (429,) or resp.status_code >= 500:
                if attempt < HTML_FETCH_ATTEMPTS - 1:
                    time.sleep(HTML_FETCH_BACKOFF * (2 ** attempt))
                    continue
            return None
        return None

    if use_cache:
        return cache.get_or_set_text("html", url, fetch)
    return fetch()


def html_to_markdown(
    cache: FileCache,
    url: str,
    html: str,
    *,
    use_cache: bool = True,
) -> Optional[str]:
    import trafilatura

    def convert() -> Optional[str]:
        return trafilatura.extract(html, output_format="markdown", with_metadata=False) or ""

    if use_cache:
        md = cache.get_or_set_text("markdown", url, convert)
    else:
        md = convert()
    return md or None
