"""CLI for LOW manual validation export and reporting."""
from __future__ import annotations

from pathlib import Path

import click

from .export import EXPORT_FILENAME, export_annotation_bundle
from .import_report import generate_validation_report

DEFAULT_EXPORT_DIR = Path("annotation")
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "low_db.json"

CONTEXT_SETTINGS = {"help_option_names": ["-h", "-?", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
def main() -> None:
    """Export LOW data for human annotation and aggregate completed reviews."""


@main.command()
@click.option(
    "--output",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_EXPORT_DIR,
    show_default=True,
    help="Root annotation directory (writes exports/ and ANNOTATOR_GUIDE.md).",
)
@click.option(
    "--db-path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=DEFAULT_DB,
    show_default=True,
    help="Path to low_db.json.",
)
@click.option("--seed", type=int, default=42, show_default=True, help="Random seed.")
@click.option(
    "--no-risk",
    is_flag=True,
    default=False,
    help="Skip high-risk overlay records.",
)
@click.option(
    "--max-samples",
    type=int,
    default=None,
    help="Cap each sheet to at most N randomly selected rows.",
)
def export(
    output_dir: Path,
    db_path: Path,
    seed: int,
    no_risk: bool,
    max_samples: int | None,
) -> None:
    """Export a stratified annotation workbook for all LOW datasets."""
    exports_dir = export_annotation_bundle(
        output_dir,
        db_path=db_path,
        seed=seed,
        include_risk=not no_risk,
        max_samples=max_samples,
    )
    click.echo(f"Wrote {EXPORT_FILENAME} to {exports_dir}")


@main.command()
@click.option(
    "--input",
    "input_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory with the completed annotation workbook (or CSV files).",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_EXPORT_DIR / "reports",
    show_default=True,
    help="Directory for summary.md, summary.json, flagged_records.csv.",
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help="Optional export manifest.json for provenance.",
)
def report(input_dir: Path, output_dir: Path, manifest_path: Path | None) -> None:
    """Generate a validation report from completed annotation files."""
    report_dir = generate_validation_report(
        input_dir,
        output_dir,
        manifest_path=manifest_path,
    )
    click.echo(f"Wrote validation report to {report_dir}")
