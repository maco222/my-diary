"""CLI interface for my-diary."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta

import structlog
from rich.console import Console

from my_diary.config import load_config, load_secrets
from my_diary.pipeline import Pipeline

console = Console()
log = structlog.get_logger()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="my-diary",
        description="Automatyczny skryba dzienny — zbiera aktywność i syntetyzuje notatkę",
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to today (or yesterday if before 6:00).",
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


def _default_date() -> date:
    """Return today, or yesterday if it's before 6 AM."""
    from datetime import datetime

    now = datetime.now()
    if now.hour < 6:
        return (now - timedelta(days=1)).date()
    return now.date()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            "DEBUG" if args.verbose else "INFO"
        ),
    )

    target_date = args.date or _default_date()
    config = load_config()
    secrets = load_secrets()

    console.print(f"[bold]my-diary[/bold] — generating diary for [cyan]{target_date}[/cyan]")

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
        console.print(f"\n[bold green]Done![/bold green] Date: {target_date}")
        for writer_name, success in result.write_results.items():
            status = "[green]OK[/green]" if success else "[red]FAIL[/red]"
            console.print(f"  {writer_name}: {status}")

    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  - {err}")

    sys.exit(1 if result.errors and not args.dry_run else 0)
