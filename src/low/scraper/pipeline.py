from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from tqdm import tqdm

from .cache import FileCache
from .fetch import (
    USER_AGENT,
    all_organic_urls,
    fetch_url,
    html_to_markdown,
    serper_search,
)
from .llm import GeminiClient
from .robots import RobotsChecker
from .state import (
    PipelineState,
    RoundWriter,
    load_pipeline_state,
    round_results_path,
    write_output_json,
)
from .tasks.base import ScrapeItem, ScrapeTask

LOG = logging.getLogger("low.scraper")
_ROBOTS_LOG = LOG.getChild("robots")


@dataclass
class PipelineConfig:
    data_dir: Path
    cache_dir: Path
    task: ScrapeTask
    rounds: int = 1
    results_per_pair: int = 1
    workers: int = 8
    llm_workers: int = 4
    limit: Optional[int] = None
    request_delay: float = 0.5
    respect_robots: bool = True
    use_cache: bool = True
    model: str = "gemini-3.5-flash"


def _item_result_columns(item: ScrapeItem, task: ScrapeTask) -> Dict[str, str]:
    cols = task.result_columns()
    return {col: item.get(col) for col in cols}


def _process_item(
    item: ScrapeItem,
    task: ScrapeTask,
    cache: FileCache,
    serper_api_key: str,
    llm: GeminiClient,
    results_per_pair: int,
    tried_urls: Dict[Tuple[str, ...], Set[str]],
    robots: Optional[RobotsChecker],
    use_cache: bool,
) -> List[Tuple[Dict[str, str], str, str, str]]:
    """Return list of (item_fields, url, prompt, llm_response) rows."""
    key = task.item_key(item)
    query = task.search_query(item)
    try:
        response = serper_search(
            cache, serper_api_key, query, use_cache=use_cache
        )
    except requests.HTTPError as e:
        LOG.error("serper %r: %s", query, e)
        return []
    except requests.RequestException as e:
        LOG.error("serper-net %r: %s", query, e)
        return []

    skip = tried_urls.get(key, set())
    fresh = [u for u in all_organic_urls(response) if u not in skip]
    out: List[Tuple[Dict[str, str], str, str, str]] = []
    fields = _item_result_columns(item, task)

    for url in fresh:
        if len(out) >= results_per_pair:
            break
        if robots is not None and not robots.allowed(url):
            _ROBOTS_LOG.info("skip (disallowed by robots.txt): %s", url)
            continue
        html = fetch_url(cache, url, use_cache=use_cache)
        if not html:
            continue
        md = html_to_markdown(cache, url, html, use_cache=use_cache)
        if not md:
            continue
        prompt = task.build_prompt(item, md)
        raw = llm.generate(prompt)
        out.append((fields, url, prompt, raw))
        if task.is_solved(task.parse_response(raw)):
            break
    return out


def _apply_rows(
    task: ScrapeTask,
    state: PipelineState,
    rows: List[Tuple[Dict[str, str], str, str, str]],
    writer: RoundWriter,
) -> bool:
    solved = False
    for fields, url, prompt, raw in rows:
        key = tuple(fields[col] for col in task.result_columns())
        state.tried_urls.setdefault(key, set()).add(url)
        writer.write_row(task, fields, url, prompt, raw)
        parsed = task.parse_response(raw)
        if task.is_solved(parsed):
            state.solved_keys.add(key)
            solved = True
            prev = state.best.get(key)
            if prev is None or not task.is_solved(prev[0]):
                state.best[key] = (parsed, url, fields)
            else:
                merged = task.merge_values(prev[0], parsed)
                win_url = url if merged != prev[0] else prev[1]
                state.best[key] = (merged, win_url, fields)
    return solved


def run_pipeline(config: PipelineConfig) -> Path:
    """Run the full search → scrape → LLM → aggregate pipeline."""
    if config.rounds < 1:
        raise ValueError("rounds must be >= 1")

    serper_api_key = os.environ.get("SERPER_API_KEY")
    if not serper_api_key:
        raise SystemExit("SERPER_API_KEY environment variable is required.")

    config.data_dir.mkdir(parents=True, exist_ok=True)
    cache = FileCache(config.cache_dir)
    llm = GeminiClient(
        cache,
        model=config.model,
        use_cache=config.use_cache,
    )
    robots: Optional[RobotsChecker] = (
        RobotsChecker(cache, user_agent=USER_AGENT)
        if config.respect_robots
        else None
    )

    state = load_pipeline_state(config.data_dir, config.task)
    existing_rounds = set(state.completed_rounds)
    start_round = max(existing_rounds, default=0) + 1

    if existing_rounds:
        LOG.info(
            "Resumed from %d prior round file(s); %d items already solved.",
            len(existing_rounds),
            len(state.solved_keys),
        )

    if start_round > config.rounds:
        tqdm.write(
            f"All {config.rounds} round(s) already complete — writing output from checkpoint data."
        )
        output_path = write_output_json(config.data_dir, config.task, state)
        tqdm.write(f"Wrote {output_path.name} ({len(state.solved_keys)} resolved)")
        LOG.info("Cache stats — %s", cache.stats_summary())
        return output_path

    rounds_to_run = config.rounds - start_round + 1
    total_newly_solved = 0

    with tqdm(total=rounds_to_run, unit="round", desc="overall", position=0) as round_bar:
        for round_num in range(start_round, config.rounds + 1):
            all_items = config.task.discover_items()
            unresolved = [
                item
                for item in all_items
                if config.task.item_key(item) not in state.solved_keys
            ]
            if config.limit is not None:
                unresolved = unresolved[: config.limit]

            tqdm.write(
                f"Round {round_num}/{config.rounds}: "
                f"{len(unresolved)} unresolved items, {config.workers} workers"
            )

            if not unresolved:
                tqdm.write(f"Round {round_num}: nothing left to scrape.")
                round_bar.update(1)
                continue

            round_path = round_results_path(config.data_dir, round_num)
            writer = RoundWriter(round_path, config.task)
            round_solved = 0
            urls_processed = 0

            try:
                items_bar = tqdm(
                    total=len(unresolved),
                    unit="item",
                    desc=f"round {round_num}",
                    position=1,
                    leave=False,
                )
                if config.workers <= 1:
                    for item in unresolved:
                        rows = _process_item(
                            item,
                            config.task,
                            cache,
                            serper_api_key,
                            llm,
                            config.results_per_pair,
                            state.tried_urls,
                            robots,
                            config.use_cache,
                        )
                        if _apply_rows(config.task, state, rows, writer):
                            round_solved += 1
                        urls_processed += len(rows)
                        items_bar.set_postfix(solved=round_solved, urls=urls_processed)
                        items_bar.update(1)
                        time.sleep(config.request_delay)
                else:
                    with ThreadPoolExecutor(max_workers=config.workers) as ex:
                        futures = {
                            ex.submit(
                                _process_item,
                                item,
                                config.task,
                                cache,
                                serper_api_key,
                                llm,
                                config.results_per_pair,
                                state.tried_urls,
                                robots,
                                config.use_cache,
                            ): item
                            for item in unresolved
                        }
                        for fut in as_completed(futures):
                            try:
                                rows = fut.result()
                            except Exception as e:
                                LOG.error("worker failed: %s", e)
                                rows = []
                            if _apply_rows(config.task, state, rows, writer):
                                round_solved += 1
                            urls_processed += len(rows)
                            items_bar.set_postfix(solved=round_solved, urls=urls_processed)
                            items_bar.update(1)
                items_bar.close()
            finally:
                writer.close()
                state.completed_rounds.append(round_num)

            total_newly_solved += round_solved
            still_unknown = len(unresolved) - round_solved
            tqdm.write(
                f"Round {round_num}/{config.rounds} complete: "
                f"{round_solved} newly resolved, {still_unknown} still unknown "
                f"({writer.row_count} rows → {round_path.name})"
            )
            round_bar.update(1)

    output_path = write_output_json(config.data_dir, config.task, state)
    tqdm.write(
        f"Wrote {output_path.name} ({len(state.best)} records, "
        f"{len(state.solved_keys)} resolved)"
    )
    LOG.info("Cache stats — %s", cache.stats_summary())
    return output_path
