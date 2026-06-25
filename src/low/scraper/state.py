from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .tasks.base import ScrapeTask

# Raise CSV field size limit for rows with embedded markdown prompts.
_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_limit)
        break
    except OverflowError:
        _limit //= 2

ROUND_RESULTS_RE = re.compile(r"^round(\d+)_results\.csv$")
RESPONSE_COLUMN = "llm_response"


@dataclass
class PipelineState:
    """Tracks solved items, tried URLs, and best values across rounds."""

    solved_keys: Set[Tuple[str, ...]] = field(default_factory=set)
    tried_urls: Dict[Tuple[str, ...], Set[str]] = field(default_factory=dict)
    best: Dict[Tuple[str, ...], Tuple[Any, str, Dict[str, str]]] = field(default_factory=dict)
    completed_rounds: List[int] = field(default_factory=list)


def round_results_path(data_dir: Path, round_num: int) -> Path:
    return data_dir / f"round{round_num}_results.csv"


def scan_round_files(data_dir: Path) -> List[Path]:
    if not data_dir.is_dir():
        return []
    files: List[Path] = []
    for entry in data_dir.iterdir():
        if entry.is_file() and ROUND_RESULTS_RE.match(entry.name):
            files.append(entry)
    return sorted(files, key=lambda p: int(ROUND_RESULTS_RE.match(p.name).group(1)))


def result_csv_header(task: ScrapeTask) -> List[str]:
    return [*task.result_columns(), "url", "prompt", RESPONSE_COLUMN]


def load_pipeline_state(data_dir: Path, task: ScrapeTask) -> PipelineState:
    """Load solved/tried/best from all existing round{N}_results.csv files."""
    state = PipelineState()
    for path in scan_round_files(data_dir):
        m = ROUND_RESULTS_RE.match(path.name)
        assert m is not None
        round_num = int(m.group(1))
        _load_round_file(path, task, state)
        state.completed_rounds.append(round_num)
    return state


def _load_round_file(path: Path, task: ScrapeTask, state: PipelineState) -> None:
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = set(result_csv_header(task))
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"Results file {path} missing columns: {sorted(missing)}"
            )
        for row in reader:
            key_fields = {col: row[col] for col in task.result_columns()}
            key = tuple(row[col] for col in task.result_columns())
            state.tried_urls.setdefault(key, set()).add(row["url"])
            parsed = task.parse_response(row.get(RESPONSE_COLUMN, ""))
            if task.is_solved(parsed):
                state.solved_keys.add(key)
                prev = state.best.get(key)
                if prev is None or not task.is_solved(prev[0]):
                    state.best[key] = (parsed, row["url"], key_fields)
                else:
                    merged = task.merge_values(prev[0], parsed)
                    win_url = row["url"] if merged != prev[0] else prev[1]
                    state.best[key] = (merged, win_url, key_fields)


def write_output_json(
    data_dir: Path,
    task: ScrapeTask,
    state: PipelineState,
) -> Path:
    output_path = data_dir / task.output_filename()
    records = []
    for key, (value, url, fields) in sorted(state.best.items()):
        if not task.is_solved(value):
            continue
        item = task.item_for_key(key, fields)
        records.append(task.to_output_record(item, value, url))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


class RoundWriter:
    """Append rows to a round checkpoint CSV."""

    def __init__(self, path: Path, task: ScrapeTask) -> None:
        self.path = path
        self._columns = result_csv_header(task)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=self._columns)
        self._writer.writeheader()
        self.row_count = 0

    def write_row(
        self,
        task: ScrapeTask,
        item_fields: Dict[str, str],
        url: str,
        prompt: str,
        llm_response: str,
    ) -> None:
        row = {col: item_fields.get(col, "") for col in task.result_columns()}
        row["url"] = url
        row["prompt"] = prompt
        row[RESPONSE_COLUMN] = llm_response
        self._writer.writerow(row)
        self.row_count += 1
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
