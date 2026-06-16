"""Round bookkeeping in the data directory.

Layout (each round may be split into batches a, b, c, ...):

    scraper-data/
        prompts1a.csv                    # round-1 batch a (written by `scrape`)
        prompts1a_results_*.csv          # round-1 batch a loom output
        prompts1b.csv                    # round-1 batch b
        prompts1b_results_*.csv
        prompts2a.csv                    # round-2 batch a
        ...
        speakers.json                    # final aggregation

Backward compatibility: prompts files without a batch letter (e.g.
``prompts1.csv`` / ``prompts1_results_*.csv``) are also recognised and treated
as a single-batch round.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


# Round number + optional batch letter(s). Batch suffix is one or more lowercase
# letters (a, b, ..., z, aa, ab, ...). Empty suffix is legal (legacy layout).
PROMPTS_RE = re.compile(r"^prompts(\d+)([a-z]*)\.csv$")
RESULTS_RE = re.compile(r"^prompts(\d+)([a-z]*)_results_.+\.csv$")


@dataclass
class RoundState:
    data_dir: Path
    completed_rounds: List[int]                              # every batch has results
    pending_prompts_round: Optional[int]                     # latest round with batches missing results
    pending_batches: List[str]                               # batch letters in the pending round still awaiting loom
    results_files: List[Path]                                # all results files across all rounds & batches
    prompts_by_round: Dict[int, List[str]]                   # round -> sorted batch suffixes that exist on disk
    next_round: int                                          # round number to write next


def scan_data_dir(data_dir: Path) -> RoundState:
    data_dir.mkdir(parents=True, exist_ok=True)

    prompts_by_round: Dict[int, List[str]] = {}
    # (round, batch) -> [results files]
    results_by_batch: Dict[tuple[int, str], List[Path]] = {}

    for entry in data_dir.iterdir():
        if not entry.is_file():
            continue
        m = PROMPTS_RE.match(entry.name)
        if m:
            prompts_by_round.setdefault(int(m.group(1)), []).append(m.group(2))
            continue
        m = RESULTS_RE.match(entry.name)
        if m:
            results_by_batch.setdefault((int(m.group(1)), m.group(2)), []).append(entry)

    for r in prompts_by_round:
        prompts_by_round[r].sort()

    completed: List[int] = []
    pending_round: Optional[int] = None
    pending_batches: List[str] = []
    for r, batches in sorted(prompts_by_round.items()):
        missing = [b for b in batches if not results_by_batch.get((r, b))]
        if not missing:
            completed.append(r)
        else:
            # Track the highest round with pending batches.
            if pending_round is None or r > pending_round:
                pending_round = r
                pending_batches = missing

    all_results: List[Path] = []
    for key in sorted(results_by_batch):
        all_results.extend(sorted(results_by_batch[key]))

    if not prompts_by_round:
        next_round = 1
    elif pending_round is not None:
        next_round = pending_round
    else:
        next_round = max(prompts_by_round) + 1

    return RoundState(
        data_dir=data_dir,
        completed_rounds=completed,
        pending_prompts_round=pending_round,
        pending_batches=pending_batches,
        results_files=all_results,
        prompts_by_round=prompts_by_round,
        next_round=next_round,
    )


# --- batch-suffix helpers ---------------------------------------------------


def batch_suffix(index: int) -> str:
    """0 -> 'a', 1 -> 'b', ..., 25 -> 'z', 26 -> 'aa', 27 -> 'ab', ..."""
    if index < 0:
        raise ValueError("batch index must be non-negative")
    letters = string.ascii_lowercase
    out = ""
    i = index
    while True:
        out = letters[i % 26] + out
        i = i // 26 - 1
        if i < 0:
            return out


def prompts_path(data_dir: Path, round_num: int, batch: str = "") -> Path:
    """Path to a prompts file. `batch` is the suffix returned by ``batch_suffix``."""
    return data_dir / f"prompts{round_num}{batch}.csv"


def existing_prompts_paths(data_dir: Path, round_num: int) -> List[Path]:
    """All on-disk prompts files for a round, sorted by batch suffix."""
    state = scan_data_dir(data_dir)
    return [
        prompts_path(data_dir, round_num, b)
        for b in state.prompts_by_round.get(round_num, [])
    ]
