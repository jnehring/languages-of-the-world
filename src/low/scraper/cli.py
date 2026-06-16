from __future__ import annotations

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .aggregate import aggregate
from .import_speakers import import_speakers
from .rounds import existing_prompts_paths, prompts_path, scan_data_dir
from .scrape import LOG, configure_logging, run_scrape


DEFAULT_DATA_DIR = Path("scraper-data")

# Make -h, -?, and --help all show help on every command and the top-level group.
CONTEXT_SETTINGS = {"help_option_names": ["-h", "-?", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
def main() -> None:
    """low-scraper: fill in missing speaker counts via web search + LLM (loom)."""
    load_dotenv()


@main.command()
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
    help="Directory holding promptsN.csv / promptsN_results_*.csv files.",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Cache directory (default: <data-dir>/.cache).",
)
@click.option(
    "--results-per-pair", "-n",
    type=int, default=1, show_default=True,
    help="Number of top search results to download per country/language pair.",
)
@click.option(
    "--limit",
    type=int, default=None,
    help="Only process the first N pairs (useful for testing).",
)
@click.option(
    "--request-delay",
    type=float, default=0.5, show_default=True,
    help=(
        "Seconds to sleep between serper queries when running single-threaded "
        "(workers=1). Ignored when workers > 1."
    ),
)
@click.option(
    "--workers", "-j",
    type=int, default=8, show_default=True,
    help="Number of parallel threads fetching search results and pages.",
)
@click.option(
    "--batch-size",
    type=int, default=1500, show_default=True,
    help=(
        "Maximum number of rows per prompts file. When exceeded, output rolls "
        "over to prompts{N}b.csv, prompts{N}c.csv, ..."
    ),
)
@click.option(
    "--response-column",
    type=str, default="llm_response", show_default=True,
    help="Column name in loom result CSVs holding the model's answer.",
)
@click.option(
    "--respect-robots/--ignore-robots",
    default=True, show_default=True,
    help=(
        "Honour each site's robots.txt before downloading a page. Disallowed "
        "URLs are skipped and the loop falls through to the next search result."
    ),
)
@click.option(
    "--force-new-round/--no-force-new-round",
    default=False,
    help=(
        "Always start a fresh round even if the highest-numbered prompts file "
        "has no results yet (which would otherwise be re-generated in place)."
    ),
)
def scrape(
    data_dir: Path,
    cache_dir: Path | None,
    results_per_pair: int,
    limit: int,
    request_delay: float,
    workers: int,
    batch_size: int,
    response_column: str,
    respect_robots: bool,
    force_new_round: bool,
) -> None:
    """Run the next scrape round.

    Inspects --data-dir and figures out what to do:

    \b
    * empty dir                 -> writes prompts1a.csv (+ b, c, ... if --batch-size exceeded)
    * round N + complete results -> writes round N+1 batches for pairs still UNKNOWN
    * round N partial / pending  -> regenerates round N (any leftover batches are removed first)

    Each round is split into batch files (prompts{N}a.csv, prompts{N}b.csv, ...)
    when the row count exceeds --batch-size. Run loom on every batch and drop
    its output as prompts{N}{batch}_results_<anything>.csv next to it; then
    re-run `low-scraper scrape`.
    """
    state = scan_data_dir(data_dir)
    if cache_dir is None:
        cache_dir = data_dir / ".cache"

    log_path = data_dir / "scrape.log"
    configure_logging(log_path)
    LOG.info("===== scrape run starting =====")
    LOG.info("Logging to %s (per-URL chatter is file-only)", log_path)

    if state.pending_prompts_round is not None and not force_new_round:
        round_num = state.pending_prompts_round
        previous_files = state.results_files
        # Remove any existing prompts{N}*.csv files for this round so we start
        # from a clean slate (batch boundaries may shift).
        stale = existing_prompts_paths(data_dir, round_num)
        if stale:
            LOG.info(
                "Round %d has unprocessed batches — regenerating. "
                "Removing %d stale file(s): %s",
                round_num, len(stale), ", ".join(p.name for p in stale),
            )
            for p in stale:
                p.unlink()
    else:
        round_num = state.next_round
        previous_files = state.results_files

    if previous_files:
        LOG.info(
            "Round %d: using %d prior result file(s) (batch size %d)",
            round_num, len(previous_files), batch_size,
        )
    else:
        LOG.info("Round %d (initial), batch size %d", round_num, batch_size)

    paths = run_scrape(
        naming=lambda batch: prompts_path(data_dir, round_num, batch),
        cache_dir=cache_dir,
        results_per_pair=results_per_pair,
        limit=limit,
        request_delay=request_delay,
        batch_size=batch_size,
        previous_results=previous_files,
        response_column=response_column,
        workers=workers,
        respect_robots=respect_robots,
        # log_file omitted: already configured above so we control the path.
    )

    if paths:
        LOG.info(
            "Next step: run loom on each batch and write its output to "
            "%s/<batch_name>_results_<model>.csv (e.g. %s_results_<model>.csv). "
            "Then re-run `low-scraper scrape` or `low-scraper aggregate`.",
            data_dir, paths[0].stem,
        )


@main.command(name="aggregate")
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
    help="Directory holding promptsN_results_*.csv files to aggregate.",
)
@click.option(
    "--output", "-o", "output_json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output JSON path (default: <data-dir>/speakers.json).",
)
@click.option(
    "--response-column",
    type=str, default="llm_response", show_default=True,
    help="Name of the column in the loom result CSVs holding the model's answer.",
)
def aggregate_cmd(
    data_dir: Path,
    output_json: Path | None,
    response_column: str,
) -> None:
    """Aggregate every promptsN_results_*.csv in --data-dir into one JSON file.

    Conflicting numbers across files/rows are unified by taking the max.
    """
    state = scan_data_dir(data_dir)
    if not state.results_files:
        click.echo(f"No promptsN_results_*.csv files found in {data_dir}", err=True)
        sys.exit(1)
    if output_json is None:
        output_json = data_dir / "speakers.json"

    click.echo(
        f"Aggregating {len(state.results_files)} result file(s): "
        f"{', '.join(p.name for p in state.results_files)}",
        err=True,
    )
    aggregate(state.results_files, output_json, response_column)


@main.command(name="import")
@click.option(
    "--input", "-i", "input_json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Label-based speakers.json (default: <data-dir>/speakers.json).",
)
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
)
@click.option(
    "--output", "-o", "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Normalized source file (default: src/low/data/sources/low_scraper_speakers.json).",
)
def import_cmd(
    input_json: Path | None,
    data_dir: Path,
    output_path: Path | None,
) -> None:
    """Convert speakers.json labels to ISO codes and write the bootstrap source file."""
    if input_json is None:
        input_json = data_dir / "speakers.json"
    count, skipped = import_speakers(input_json, output_path)
    dest = output_path or import_speakers.DEFAULT_OUTPUT
    click.echo(f"Wrote {count} records ({skipped} skipped) → {dest}")


@main.command(name="status")
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
)
def status_cmd(data_dir: Path) -> None:
    """Show which rounds are present in --data-dir and what scrape would do next."""
    state = scan_data_dir(data_dir)
    click.echo(f"data dir: {data_dir}")
    click.echo(f"completed rounds (every batch has results): {state.completed_rounds or '—'}")
    if state.pending_prompts_round is not None:
        missing = ", ".join(
            f"prompts{state.pending_prompts_round}{b}.csv"
            for b in state.pending_batches
        )
        click.echo(f"pending round {state.pending_prompts_round} — awaiting loom on: {missing}")
    else:
        click.echo("pending round: —")
    for r in sorted(state.prompts_by_round):
        batches = state.prompts_by_round[r]
        click.echo(f"  round {r}: {len(batches)} batch(es) [{', '.join(b or '(none)' for b in batches)}]")
    click.echo(f"result files seen: {len(state.results_files)}")
    if state.pending_prompts_round is not None:
        click.echo(f"`scrape` would regenerate round {state.pending_prompts_round}")
    else:
        click.echo(
            f"`scrape` would write: "
            f"{prompts_path(data_dir, state.next_round, 'a').name} (+ b, c, ... as needed)"
        )


if __name__ == "__main__":
    main()
