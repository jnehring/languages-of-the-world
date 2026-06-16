"""robots.txt enforcement.

Per host, fetches /robots.txt once (cached on disk via FileCache), parses it
with stdlib ``urllib.robotparser``, and offers a thread-safe ``allowed(url)``
check using the scraper's User-Agent.

Per RFC 9309: an *unreachable* robots.txt (4xx, missing) is treated as
"allow all". Network errors and 5xx responses are treated as "disallow all"
for that host this run (no caching), to be conservative.
"""
from __future__ import annotations

import threading
from typing import Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from .cache import FileCache


# Sentinel stored in the on-disk cache when the host's robots.txt is empty
# or returned a 4xx (i.e. "no rules; allow all").
_ALLOW_ALL_MARKER = "# low-scraper: no robots.txt or 4xx; allow-all\n"


class RobotsChecker:
    def __init__(
        self,
        cache: FileCache,
        user_agent: str,
        timeout: float = 10.0,
    ) -> None:
        self._cache = cache
        self._user_agent = user_agent
        self._timeout = timeout
        self._parsers: Dict[str, Optional[RobotFileParser]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def allowed(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        host = parsed.hostname
        if not host:
            return False
        scheme = parsed.scheme or "https"

        with self._lock:
            cached = self._parsers.get(host, "missing")
        if cached != "missing":
            return cached is None or cached.can_fetch(self._user_agent, url)

        parser = self._load_parser(host, scheme)
        with self._lock:
            self._parsers[host] = parser
        if parser is None:
            # Network/5xx error: be conservative this run.
            return False
        return parser.can_fetch(self._user_agent, url)

    # ------------------------------------------------------------------
    def _load_parser(self, host: str, scheme: str) -> Optional[RobotFileParser]:
        robots_url = f"{scheme}://{host}/robots.txt"
        try:
            text = self._cache.get_or_set_text(
                "robots", robots_url, lambda: self._download(robots_url)
            )
        except requests.RequestException:
            return None
        if text is None:
            text = ""
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(text.splitlines())
        return rp

    def _download(self, robots_url: str) -> Optional[str]:
        """Return text to cache. Return ``None`` to skip caching (transient errors)."""
        try:
            resp = requests.get(
                robots_url,
                timeout=self._timeout,
                headers={"User-Agent": self._user_agent},
                allow_redirects=True,
            )
        except requests.RequestException:
            # Transient: don't cache, treat as disallow this run.
            raise
        if resp.status_code >= 500:
            # Server error: per RFC 9309 → disallow. Don't cache.
            raise requests.HTTPError(f"{resp.status_code} on {robots_url}")
        if resp.status_code >= 400:
            # 4xx: no robots.txt → allow-all. Cache the marker.
            return _ALLOW_ALL_MARKER
        return resp.text or _ALLOW_ALL_MARKER
