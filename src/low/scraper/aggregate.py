from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple

# Loom result rows include the full prompt (with embedded markdown), which
# routinely exceeds Python's default 131 KB per-field cap. Raise it to the
# largest value the platform's C `long` accepts.
_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_limit)
        break
    except OverflowError:
        _limit //= 2

from .tasks.speakers import parse_speaker_count


def aggregate(loom_csvs: Iterable[Path], output_json: Path, response_column: str) -> None:
    """Read one or more loom result CSVs, take max per (country, language), write JSON list."""
    best: Dict[Tuple[str, str], Tuple[int, str]] = {}
    seen_pairs: set[Tuple[str, str]] = set()
    total_rows = 0
    files = list(loom_csvs)

    for loom_csv in files:
        with loom_csv.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"country", "language", "url", response_column}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise SystemExit(
                    f"Input {loom_csv} is missing required columns: {sorted(missing)}. "
                    f"Found: {reader.fieldnames}"
                )

            for row in reader:
                total_rows += 1
                key = (row["country"], row["language"])
                seen_pairs.add(key)
                count = parse_speaker_count(row.get(response_column, ""))
                if count is None:
                    continue
                prev = best.get(key)
                if prev is None or count > prev[0]:
                    best[key] = (count, row["url"])

    records = [
        {
            "country": country,
            "language": language,
            "number_of_speakers": count,
            "source_url": url,
        }
        for (country, language), (count, url) in sorted(best.items())
    ]

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    unknown_pairs = len(seen_pairs) - len(best)
    print(
        f"Aggregated {total_rows} rows from {len(files)} file(s) "
        f"into {len(records)} records → {output_json}",
        file=sys.stderr,
    )
    print(
        f"Unresolved (UNKNOWN) country/language pairs: {unknown_pairs} "
        f"of {len(seen_pairs)} seen",
        file=sys.stderr,
    )
