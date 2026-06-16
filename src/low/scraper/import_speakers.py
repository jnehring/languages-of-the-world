"""Convert label-based speakers.json into ISO-coded bootstrap source records."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent / "data" / "sources" / "low_scraper_speakers.json"
)


def _label_maps(db_path: Path) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, int]]:
    raw = json.loads(db_path.read_text(encoding="utf-8"))
    country_by_label = {c["label"]: c["code"] for c in raw["countries"]}
    language_by_label: Dict[str, str] = {}
    for lang in raw["languages"]:
        label = lang["label"]
        if label not in language_by_label:
            language_by_label[label] = lang["part3"]
    population_by_code = {c["code"]: c.get("population", 0) for c in raw["countries"]}
    return country_by_label, language_by_label, population_by_code


def import_speakers(
    input_json: Path,
    output_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> Tuple[int, int]:
    """Normalize speakers.json and write low_scraper_speakers.json.

    Returns (records_written, records_skipped).
    """
    if output_path is None:
        output_path = DEFAULT_OUTPUT
    if db_path is None:
        db_path = Path(__file__).resolve().parent.parent / "data" / "low_db.json"

    if not input_json.exists():
        raise SystemExit(f"Input file not found: {input_json}")

    country_by_label, language_by_label, population_by_code = _label_maps(db_path)
    raw_records = json.loads(input_json.read_text(encoding="utf-8"))

    out: List[dict] = []
    skipped = 0
    for rec in raw_records:
        country_label = rec.get("country", "")
        language_label = rec.get("language", "")
        count = rec.get("number_of_speakers")

        cc = country_by_label.get(country_label)
        p3 = language_by_label.get(language_label)
        if not cc or not p3 or count is None:
            print(
                f"WARNING: skip unresolvable {country_label!r} / {language_label!r}",
                file=sys.stderr,
            )
            skipped += 1
            continue

        pop = population_by_code.get(cc, 0)
        fraction = round(count / pop, 6) if pop else 0.0
        out.append(
            {
                "country_code": cc,
                "iso639_3": p3,
                "speaker_count": count,
                "speaker_fraction": fraction,
            }
        )

    out.sort(key=lambda r: (r["country_code"], r["iso639_3"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(out), skipped


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import scraped speakers into bootstrap source JSON.")
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=Path("scraper-data/speakers.json"),
        help="Label-based speakers.json from low-scraper aggregate",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    count, skipped = import_speakers(args.input, args.output)
    dest = args.output or DEFAULT_OUTPUT
    print(f"Wrote {count} records ({skipped} skipped) → {dest}")


if __name__ == "__main__":
    main()
