from __future__ import annotations

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .aggregate import aggregate
from .cache import FileCache
from .import_speakers import import_speakers
from .pipeline import PipelineConfig, run_pipeline
from .rounds import existing_prompts_paths, prompts_path, scan_data_dir
from .scrape import LOG, configure_logging, run_scrape
from .state import load_pipeline_state, scan_round_files
from .tasks import get_task, list_tasks


DEFAULT_DATA_DIR = Path("scraper-data")

CONTEXT_SETTINGS = {"help_option_names": ["-h", "-?", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
def main() -> None:
    """low-scraper: fill missing data via web search + Gemini LLM."""
    load_dotenv()


@main.command()
@click.option(
    "--task",
    type=click.Choice(list_tasks()),
    default="speakers",
    show_default=True,
    help="Scrape task to run.",
)
@click.option(
    "--rounds",
    type=int,
    default=1,
    show_default=True,
    help="Number of search+scrape+LLM rounds to run (total, including resume).",
)
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_DATA_DIR,
    show_default=True,
    help="Directory for round checkpoints and output JSON.",
)
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Cache directory (default: <data-dir>/.cache).",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Bypass Serper and LLM caches (force fresh API calls).",
)
@click.option(
    "--results-per-pair", "-n",
    type=int, default=1, show_default=True,
    help="Number of top search results to try per item per round.",
)
@click.option(
    "--limit",
    type=int, default=None,
    help="Only process the first N unresolved items (useful for testing).",
)
@click.option(
    "--request-delay",
    type=float, default=0.5, show_default=True,
    help="Seconds between items when workers=1.",
)
@click.option(
    "--workers", "-j",
    type=int, default=8, show_default=True,
    help="Parallel threads for search, fetch, and LLM per item.",
)
@click.option(
    "--llm-workers",
    type=int, default=4, show_default=True,
    help="Reserved for future LLM-specific concurrency (currently uses --workers).",
)
@click.option(
    "--model",
    type=str, default="gemini-3.5-flash", show_default=True,
    help="Gemini model ID.",
)
@click.option(
    "--respect-robots/--ignore-robots",
    default=True, show_default=True,
    help="Honour robots.txt before downloading pages.",
)
def run(
    task: str,
    rounds: int,
    data_dir: Path,
    cache_dir: Path | None,
    no_cache: bool,
    results_per_pair: int,
    limit: int | None,
    request_delay: float,
    workers: int,
    llm_workers: int,
    model: str,
    respect_robots: bool,
) -> None:
    """Run the full pipeline: search → scrape → LLM → aggregate.

    Runs up to --rounds rounds automatically. Unresolved items are retried in
    later rounds with fresh search results. Checkpoints are written as
    round{N}_results.csv; final output is task-specific (e.g. speakers.json).
    """
    if rounds < 1:
        raise click.ClickException("--rounds must be >= 1")

    if cache_dir is None:
        cache_dir = data_dir / ".cache"

    log_path = data_dir / "scrape.log"
    configure_logging(log_path)
    LOG.info("===== run starting (task=%s, rounds=%d) =====", task, rounds)

    scrape_task = get_task(task)
    config = PipelineConfig(
        data_dir=data_dir,
        cache_dir=cache_dir,
        task=scrape_task,
        rounds=rounds,
        results_per_pair=results_per_pair,
        workers=workers,
        llm_workers=llm_workers,
        limit=limit,
        request_delay=request_delay,
        respect_robots=respect_robots,
        use_cache=not no_cache,
        model=model,
    )
    output = run_pipeline(config)
    click.echo(f"Done → {output}")


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
    """[DEPRECATED] Write prompt CSVs only — use `run` instead.

    Legacy loom workflow: run loom on each batch, then re-run scrape or aggregate.
    """
    state = scan_data_dir(data_dir)
    if cache_dir is None:
        cache_dir = data_dir / ".cache"

    log_path = data_dir / "scrape.log"
    configure_logging(log_path)
    LOG.info("===== scrape run starting (deprecated) =====")

    if state.pending_prompts_round is not None and not force_new_round:
        round_num = state.pending_prompts_round
        previous_files = state.results_files
        stale = existing_prompts_paths(data_dir, round_num)
        if stale:
            for p in stale:
                p.unlink()
    else:
        round_num = state.next_round
        previous_files = state.results_files

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
    )

    if paths:
        LOG.info(
            "Deprecated: run loom on each batch, or switch to `low-scraper run`."
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
    """[DEPRECATED] Aggregate legacy loom promptsN_results_*.csv files.

    The `run` command aggregates automatically. Use this only for old loom output.
    """
    state = scan_data_dir(data_dir)
    if not state.results_files:
        click.echo(f"No promptsN_results_*.csv files found in {data_dir}", err=True)
        sys.exit(1)
    if output_json is None:
        output_json = data_dir / "speakers.json"

    click.echo(
        f"Aggregating {len(state.results_files)} legacy result file(s)",
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
@click.option(
    "--cache-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Cache directory (default: <data-dir>/.cache).",
)
@click.option(
    "--task",
    type=click.Choice(list_tasks()),
    default="speakers",
    show_default=True,
)
def status_cmd(data_dir: Path, cache_dir: Path | None, task: str) -> None:
    """Show pipeline round state, resolved counts, and cache stats."""
    if cache_dir is None:
        cache_dir = data_dir / ".cache"

    scrape_task = get_task(task)
    click.echo(f"data dir: {data_dir}")
    click.echo(f"cache dir: {cache_dir}")

    round_files = scan_round_files(data_dir)
    if round_files:
        state = load_pipeline_state(data_dir, scrape_task)
        click.echo(f"pipeline rounds: {state.completed_rounds}")
        click.echo(f"resolved items: {len(state.solved_keys)}")
        click.echo(f"output: {scrape_task.output_filename()}")
    else:
        click.echo("pipeline rounds: —")

    legacy = scan_data_dir(data_dir)
    if legacy.results_files:
        click.echo(f"legacy loom result files: {len(legacy.results_files)}")
    if legacy.pending_prompts_round is not None:
        click.echo(f"legacy pending loom round: {legacy.pending_prompts_round}")

    if cache_dir.is_dir():
        cache = FileCache(cache_dir)
        click.echo(f"cache stats: {cache.stats_summary()}")
    else:
        click.echo("cache stats: —")


if __name__ == "__main__":
    main()
