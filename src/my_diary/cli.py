"""CLI interface for my-diary."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog
from rich.console import Console

from my_diary.config import load_config, load_secrets
from my_diary.pipeline import Pipeline

console = Console()
log = structlog.get_logger()

_LAST_RUN_PATH = Path(__file__).resolve().parents[2] / "output" / ".last_run"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="my-diary",
        description="Automated daily scribe — collects activity and synthesizes a diary entry",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to auto-detect with catch-up.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect data and print raw output without AI synthesis or writing.",
    )
    parser.add_argument(
        "--collectors",
        type=lambda s: s.split(","),
        default=None,
        help="Comma-separated list of collectors to run (e.g. local_git,terminal).",
    )
    parser.add_argument(
        "--writers",
        type=lambda s: s.split(","),
        default=None,
        help="Comma-separated list of writers to use (e.g. markdown,obsidian).",
    )
    parser.add_argument(
        "--retry-writers",
        action="store_true",
        help="Re-run writers using cached data from a previous run (skip collect + synthesize).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging.",
    )
    return parser.parse_args(argv)


def _latest_diary_date() -> date:
    """The most recent date we should generate a diary for.

    Before 6 AM → yesterday, otherwise → today.
    """
    now = datetime.now()
    if now.hour < 6:
        return (now - timedelta(days=1)).date()
    return now.date()


def _read_last_run() -> date | None:
    """Read last successfully generated date from .last_run file."""
    if _LAST_RUN_PATH.exists():
        try:
            return date.fromisoformat(_LAST_RUN_PATH.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def _save_last_run(d: date) -> None:
    """Save last successfully generated date."""
    _LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_PATH.write_text(d.isoformat())


def _dates_to_generate(explicit_date: date | None) -> list[date]:
    """Determine which dates need diary generation.

    If --date is given, return just that date.
    Otherwise, generate all missing dates from last_run+1 to latest_diary_date.
    """
    if explicit_date:
        return [explicit_date]

    target = _latest_diary_date()
    last_run = _read_last_run()

    if last_run and last_run >= target:
        # Already up to date — re-run today's
        return [target]

    if last_run:
        start = last_run + timedelta(days=1)
    else:
        # First run ever — just do target date
        return [target]

    # Generate all missed dates (cap at 7 days to avoid runaway)
    dates = []
    current = start
    while current <= target:
        dates.append(current)
        current += timedelta(days=1)
        if len(dates) >= 7:
            break

    return dates


def _run_for_date(args: argparse.Namespace, config, secrets, target_date: date) -> bool:
    """Run the pipeline for a single date. Returns True on success."""
    console.print(f"\n[bold]my-diary[/bold] — generating diary for [cyan]{target_date}[/cyan]")

    pipeline = Pipeline(
        config=config,
        secrets=secrets,
        target_date=target_date,
        dry_run=args.dry_run,
        retry_writers=args.retry_writers,
        collector_filter=args.collectors,
        writer_filter=args.writers,
    )

    result = asyncio.run(pipeline.run())

    if args.dry_run:
        console.print("\n[bold yellow]--- DRY RUN: Raw collector data ---[/bold yellow]\n")
        for cr in result.collector_results:
            status = "[green]OK[/green]" if cr.success else f"[red]FAIL: {cr.error}[/red]"
            console.print(f"[bold]{cr.source}[/bold] {status}")
            if cr.has_data:
                console.print_json(data=cr.data)
            console.print()
    else:
        console.print(f"[bold green]Done![/bold green] Date: {target_date}")
        for writer_name, success in result.write_results.items():
            status = "[green]OK[/green]" if success else "[red]FAIL[/red]"
            console.print(f"  {writer_name}: {status}")

    if result.errors:
        console.print("[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  - {err}")

    return not result.errors


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            "DEBUG" if args.verbose else "INFO"
        ),
    )

    config = load_config()
    secrets = load_secrets()

    dates = _dates_to_generate(args.date)

    if len(dates) > 1:
        console.print(f"[bold]my-diary[/bold] — catching up {len(dates)} days: {dates[0]} → {dates[-1]}")

    any_errors = False
    for target_date in dates:
        ok = _run_for_date(args, config, secrets, target_date)
        if ok and not args.dry_run:
            _save_last_run(target_date)
        if not ok:
            any_errors = True

    sys.exit(1 if any_errors and not args.dry_run else 0)
