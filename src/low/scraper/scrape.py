from __future__ import annotations

import csv
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from tqdm import tqdm

from .cache import FileCache
from .fetch import (
    USER_AGENT,
    all_organic_urls,
    fetch_url,
    html_to_markdown,
    serper_search,
)
from .robots import RobotsChecker
from .rounds import batch_suffix
from .tasks.speakers import SpeakerCountTask, parse_speaker_count

LOG = logging.getLogger("low.scraper")
_ROBOTS_LOG = LOG.getChild("robots")

class _QuietChildFilter(logging.Filter):
    def __init__(self, parent_name: str = "low.scraper") -> None:
        super().__init__()
        self._parent = parent_name

    def filter(self, record: logging.LogRecord) -> bool:
        is_child = record.name != self._parent and record.name.startswith(self._parent + ".")
        if is_child and record.levelno < logging.WARNING:
            return False
        return True


def configure_logging(log_file: Path, console_level: int = logging.INFO) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)

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
    LOG.propagate = False


def find_missing_pairs():
    """Legacy helper — returns SpeakerCountTask items as simple named tuples."""
    from types import SimpleNamespace

    task = SpeakerCountTask()
    return [
        SimpleNamespace(**item.fields)
        for item in task.discover_items()
    ]


def load_previous_results(
    paths: Iterable[Path], response_column: str
) -> Tuple[Set[Tuple[str, str]], Dict[Tuple[str, str], Set[str]]]:
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


def process_pair(
    pair,
    cache: FileCache,
    api_key: str,
    results_per_pair: int,
    already_tried: Dict[Tuple[str, str], Set[str]],
    robots: Optional[RobotsChecker] = None,
) -> List[Tuple[str, str, str, str]]:
    task = SpeakerCountTask()
    from .tasks.base import ScrapeItem

    item = ScrapeItem(
        fields={
            "country_code": getattr(pair, "country_code", ""),
            "country": pair.country,
            "language_part3": getattr(pair, "language_part3", ""),
            "language": pair.language,
        }
    )
    query = task.search_query(item)
    import requests

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
        out.append((pair.country, pair.language, url, task.build_prompt(item, md)))
    return out


def iter_prompt_rows(
    pairs,
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
            except Exception as e:
                LOG.error("worker for %r: %s", futures[fut], e)
                rows = []
            for row in rows:
                yield row
            if progress is not None:
                progress.update(1)


class _BatchWriter:
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
