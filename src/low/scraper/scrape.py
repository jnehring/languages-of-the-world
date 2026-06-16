from __future__ import annotations

import csv
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

import requests
from tqdm import tqdm

from .aggregate import parse_speaker_count
from .cache import FileCache
from .robots import RobotsChecker
from .rounds import batch_suffix


LOG = logging.getLogger("low.scraper")
_ROBOTS_LOG = LOG.getChild("robots")


class _QuietChildFilter(logging.Filter):
    """Drop INFO/DEBUG noise from child loggers (e.g. low.scraper.robots).

    The parent ``low.scraper`` logger handles round-level summaries; child
    loggers handle per-URL chatter that should stay file-only.
    """

    def __init__(self, parent_name: str = "low.scraper") -> None:
        super().__init__()
        self._parent = parent_name

    def filter(self, record: logging.LogRecord) -> bool:
        is_child = record.name != self._parent and record.name.startswith(self._parent + ".")
        if is_child and record.levelno < logging.WARNING:
            return False
        return True


def configure_logging(log_file: Path, console_level: int = logging.INFO) -> None:
    """Configure file + console logging.

    * **File** (``log_file``): every record at ``INFO`` or above.
    * **Console** (stderr): records from ``low.scraper`` at ``console_level``+.
      Records from child loggers (e.g. ``low.scraper.robots``) are only echoed
      to the console at ``WARNING`` or above, keeping per-URL chatter off the
      terminal.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Reset handlers so repeated calls don't double-log.
    for h in list(LOG.handlers):
        LOG.removeHandler(h)
        h.close()

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s")
    )
    LOG.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    console_handler.addFilter(_QuietChildFilter())
    LOG.addHandler(console_handler)

    LOG.setLevel(logging.INFO)
    LOG.propagate = False  # don't double-print via the root logger


SERPER_URL = "https://google.serper.dev/search"
USER_AGENT = (
    "Mozilla/5.0 (compatible; low-scraper/0.1; "
    "+https://github.com/your-org/low)"
)
INSTRUCTIONS = (
    "You are given a web page (in Markdown) as context. "
    "Extract the total number of speakers of the language {language} in {country}. "
    "Combine L1 (native) and L2 (second-language) speakers into a single total — do not distinguish them. "
    "Output ONLY a single integer with no thousands separators, no units, no commentary. "
    "If the page does not contain enough information to determine the number, output exactly: UNKNOWN"
)


@dataclass(frozen=True)
class MissingPair:
    country_code: str
    country: str
    language_part3: str
    language: str


def find_missing_pairs() -> List[MissingPair]:
    """Country/language pairs that have no per-country speaker count in `low`."""
    import low

    db = low.LanguagesOfTheWorld()
    pairs: List[MissingPair] = []
    for country in db.countries:
        known = {sc.language.part3 for sc in country.speaker_counts}
        for lang in country.languages:
            if lang.part3 in known:
                continue
            pairs.append(
                MissingPair(
                    country_code=country.code,
                    country=country.label,
                    language_part3=lang.part3,
                    language=lang.label,
                )
            )
    return pairs


def load_previous_results(
    paths: Iterable[Path], response_column: str
) -> Tuple[Set[Tuple[str, str]], Dict[Tuple[str, str], Set[str]]]:
    """Return (solved pairs, urls already tried per pair) from previous loom CSVs.

    A pair is "solved" if any row has a parseable (non-UNKNOWN) response.
    Any URL that already appeared for a pair — regardless of outcome — counts as tried,
    so the next round picks fresh search results.
    """
    solved: Set[Tuple[str, str]] = set()
    tried: Dict[Tuple[str, str], Set[str]] = {}
    for path in paths:
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = set(reader.fieldnames or [])
            required = {"country", "language", "url", response_column}
            missing = required - fields
            if missing:
                raise SystemExit(
                    f"Previous-results file {path} missing columns: {sorted(missing)}"
                )
            for row in reader:
                key = (row["country"], row["language"])
                tried.setdefault(key, set()).add(row["url"])
                if parse_speaker_count(row.get(response_column, "")) is not None:
                    solved.add(key)
    return solved, tried


SERPER_MAX_ATTEMPTS = 5  # initial try + 4 retries
SERPER_BACKOFF_BASE = 1.5  # seconds; doubles each retry


def _serper_call(api_key: str, query: str) -> dict:
    """Single serper POST. Raises on non-200."""
    resp = requests.post(
        SERPER_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": 10},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _serper_call_with_retry(api_key: str, query: str) -> dict:
    """POST to serper with exponential backoff on transient failures.

    Retries on network errors, 429 rate-limits, and 5xx responses. Returns the
    parsed JSON on success; raises the last exception if every attempt fails.
    """
    last_exc: Exception | None = None
    for attempt in range(SERPER_MAX_ATTEMPTS):
        try:
            return _serper_call(api_key, query)
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", 0)
            # Retry rate-limits and server errors; bail immediately on 4xx auth/quota errors.
            if status != 429 and status < 500:
                raise
            last_exc = e
        except requests.RequestException as e:
            last_exc = e
        if attempt < SERPER_MAX_ATTEMPTS - 1:
            time.sleep(SERPER_BACKOFF_BASE * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


def serper_search(cache: FileCache, api_key: str, query: str) -> dict:
    return cache.get_or_set_json(
        "serper", query, lambda: _serper_call_with_retry(api_key, query)
    )


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


HTML_FETCH_ATTEMPTS = 3
HTML_FETCH_BACKOFF = 1.0


def fetch_url(cache: FileCache, url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a URL with a couple of retries on transient errors.

    On terminal failure (4xx, exhausted retries) returns None; the cache stores
    an empty string so future runs don't keep retrying. Successful 200s are
    cached as their text body.
    """
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

    return cache.get_or_set_text("html", url, fetch)


def html_to_markdown(cache: FileCache, url: str, html: str) -> Optional[str]:
    import trafilatura

    def convert() -> Optional[str]:
        return trafilatura.extract(html, output_format="markdown", with_metadata=False) or ""

    md = cache.get_or_set_text("markdown", url, convert)
    return md or None


def build_prompt(pair: MissingPair, markdown: str) -> str:
    instructions = INSTRUCTIONS.format(language=pair.language, country=pair.country)
    return (
        f"{instructions}\n\n"
        f"Question: What is the number of {pair.language} speakers in {pair.country}?\n\n"
        f"--- WEB PAGE (Markdown) ---\n{markdown}\n"
    )


def process_pair(
    pair: MissingPair,
    cache: FileCache,
    api_key: str,
    results_per_pair: int,
    already_tried: Dict[Tuple[str, str], Set[str]],
    robots: Optional[RobotsChecker] = None,
) -> List[Tuple[str, str, str, str]]:
    """Return [(country, language, url, prompt), ...] for one pair.

    Diagnostic messages go through the ``low.scraper`` logger (file + ERROR-level
    console). Failures return an empty list rather than raising.
    """
    query = f"{pair.language} language number of speakers in {pair.country}"
    try:
        response = serper_search(cache, api_key, query)
    except requests.HTTPError as e:
        LOG.error("serper %r: %s", query, e)
        return []
    except requests.RequestException as e:
        LOG.error("serper-net %r: %s", query, e)
        return []

    skip = already_tried.get((pair.country, pair.language), set())
    fresh = [u for u in all_organic_urls(response) if u not in skip]
    out: List[Tuple[str, str, str, str]] = []
    for url in fresh:
        if len(out) >= results_per_pair:
            break
        if robots is not None and not robots.allowed(url):
            _ROBOTS_LOG.info("skip (disallowed by robots.txt): %s", url)
            continue
        html = fetch_url(cache, url)
        if not html:
            continue
        md = html_to_markdown(cache, url, html)
        if not md:
            continue
        out.append((pair.country, pair.language, url, build_prompt(pair, md)))
    return out


def iter_prompt_rows(
    pairs: Iterable[MissingPair],
    cache: FileCache,
    api_key: str,
    results_per_pair: int,
    request_delay: float,
    already_tried: Dict[Tuple[str, str], Set[str]],
    workers: int = 1,
    progress: Optional["tqdm"] = None,
    robots: Optional[RobotsChecker] = None,
) -> Iterator[Tuple[str, str, str, str]]:
    pairs_list = list(pairs)
    if workers <= 1:
        for pair in pairs_list:
            rows = process_pair(
                pair, cache, api_key, results_per_pair, already_tried, robots
            )
            for row in rows:
                yield row
            time.sleep(request_delay)
            if progress is not None:
                progress.update(1)
        return

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(
                process_pair, pair, cache, api_key, results_per_pair, already_tried, robots
            ): pair
            for pair in pairs_list
        }
        for fut in as_completed(futures):
            try:
                rows = fut.result()
            except Exception as e:  # pragma: no cover - defensive
                LOG.error("worker for %r: %s", futures[fut], e)
                rows = []
            for row in rows:
                yield row
            if progress is not None:
                progress.update(1)


class _BatchWriter:
    """Streams CSV rows to a sequence of files, rolling over every ``batch_size`` rows.

    Files are named via ``naming(batch_letter) -> Path``; each gets the header
    row written on first use.
    """

    HEADER = ["country", "language", "url", "prompt"]

    def __init__(self, naming, batch_size: int) -> None:
        self._naming = naming
        self._batch_size = batch_size
        self._batch_idx = 0
        self._rows_in_batch = 0
        self._total_rows = 0
        self._fh = None
        self._writer = None
        self._paths: List[Path] = []

    def write(self, row: Tuple[str, str, str, str]) -> None:
        if self._fh is None or self._rows_in_batch >= self._batch_size:
            self._roll()
        self._writer.writerow(row)
        self._rows_in_batch += 1
        self._total_rows += 1
        self._fh.flush()

    def _roll(self) -> None:
        if self._fh is not None:
            self._fh.close()
        path = self._naming(batch_suffix(self._batch_idx))
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(self.HEADER)
        self._paths.append(path)
        self._batch_idx += 1
        self._rows_in_batch = 0

    def close(self) -> List[Path]:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        return list(self._paths)

    @property
    def total_rows(self) -> int:
        return self._total_rows


def run_scrape(
    naming,
    cache_dir: Path,
    results_per_pair: int,
    limit: Optional[int],
    request_delay: float,
    batch_size: int,
    previous_results: Iterable[Path] = (),
    response_column: str = "llm_response",
    workers: int = 8,
    respect_robots: bool = True,
    log_file: Optional[Path] = None,
) -> List[Path]:
    """Run one scrape round, writing prompts split across batches.

    ``naming`` is a callable ``str -> Path``: it receives a batch suffix
    (``"a"``, ``"b"``, ...) and returns the output CSV path for that batch.
    Returns the list of paths actually written.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise SystemExit("SERPER_API_KEY environment variable is required.")

    if log_file is not None:
        configure_logging(log_file)

    cache = FileCache(cache_dir)
    robots: Optional[RobotsChecker] = (
        RobotsChecker(cache, user_agent=USER_AGENT) if respect_robots else None
    )
    previous_paths = list(previous_results)
    solved, tried = load_previous_results(previous_paths, response_column)
    if previous_paths:
        LOG.info(
            "Loaded %d prior attempts covering %d pairs; %d already solved.",
            sum(len(v) for v in tried.values()), len(tried), len(solved),
        )
        unresolved = {key for key in tried if key not in solved}
        pairs = [
            p for p in find_missing_pairs()
            if (p.country, p.language) in unresolved
        ]
    else:
        pairs = find_missing_pairs()
    if limit is not None:
        pairs = pairs[:limit]

    writer = _BatchWriter(naming, batch_size)
    try:
        with tqdm(total=len(pairs), unit="pair", desc="scraping") as progress:
            for row in iter_prompt_rows(
                pairs, cache, api_key, results_per_pair, request_delay,
                tried, workers=workers, progress=progress, robots=robots,
            ):
                writer.write(row)
                progress.set_postfix(rows=writer.total_rows, batches=len(writer._paths))
    finally:
        paths = writer.close()

    if paths:
        LOG.info(
            "Done. Wrote %d rows across %d batch file(s): %s",
            writer.total_rows, len(paths), ", ".join(p.name for p in paths),
        )
    else:
        LOG.info("Done. No rows produced; no batch file written.")
    LOG.info("Cache stats — %s", cache.stats_summary())
    return paths
