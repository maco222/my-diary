"""Markdown writer — saves diary entry to output/ directory."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import structlog

from my_diary.models import CollectorResult, DiaryEntry
from my_diary.writers.base import BaseWriter

log = structlog.get_logger()


class MarkdownWriter(BaseWriter):
    """Write diary entry as a plain Markdown file."""

    async def write(
        self,
        entry: DiaryEntry,
        collector_results: list[CollectorResult],
        target_date: date,
    ) -> None:
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        content = _render(entry, collector_results, target_date)
        output_path = output_dir / f"{target_date.isoformat()}.md"
        output_path.write_text(content, encoding="utf-8")

        log.info("markdown_written", path=str(output_path))


def _render(
    entry: DiaryEntry,
    collector_results: list[CollectorResult],
    target_date: date,
) -> str:
    """Render diary entry using Jinja2 template."""
    from jinja2 import Environment, FileSystemLoader

    templates_dir = Path(__file__).resolve().parents[3] / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("daily_note.md.j2")

    weekday_names_pl = [
        "poniedziałek", "wtorek", "środa", "czwartek",
        "piątek", "sobota", "niedziela",
    ]

    # Extract weather data if available
    weather = None
    for cr in collector_results:
        if cr.source == "weather" and cr.has_data:
            weather = cr.data
            break

    return template.render(
        target_date=target_date.isoformat(),
        weekday=weekday_names_pl[target_date.weekday()],
        entry=entry,
        weather=weather,
    )
