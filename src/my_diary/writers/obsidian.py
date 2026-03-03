"""Obsidian writer — saves diary entry to Obsidian vault with frontmatter + update logic."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import structlog

from my_diary.models import CollectorResult, DiaryEntry
from my_diary.writers.base import BaseWriter
from my_diary.writers.markdown import _render

log = structlog.get_logger()

_FRONTMATTER = """\
---
tags: [daily-diary, auto-generated]
date: {date}
---
"""

_AUTO_START = "%% AUTO-GENERATED-START %%"
_AUTO_END = "%% AUTO-GENERATED-END %%"


class ObsidianWriter(BaseWriter):
    """Write diary entry to Obsidian vault with YAML frontmatter.

    Re-run replaces the auto-generated section between markers.
    Manual content (outside markers) is preserved.
    """

    async def write(
        self,
        entry: DiaryEntry,
        collector_results: list[CollectorResult],
        target_date: date,
    ) -> None:
        vault_path = Path(self.config.vault_path)
        daily_dir = vault_path / self.config.daily_subdir
        daily_dir.mkdir(parents=True, exist_ok=True)

        note_path = daily_dir / f"{target_date.isoformat()}.md"
        auto_content = _render(entry, collector_results, target_date)
        frontmatter = _FRONTMATTER.format(date=target_date.isoformat())
        auto_block = f"{_AUTO_START}\n{auto_content}\n{_AUTO_END}"

        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8")

            if _AUTO_START in existing and _AUTO_END in existing:
                # Re-run: replace auto section, keep everything else
                start_idx = existing.index(_AUTO_START)
                end_idx = existing.index(_AUTO_END) + len(_AUTO_END)
                updated = existing[:start_idx] + auto_block + existing[end_idx:]
                note_path.write_text(updated, encoding="utf-8")
                log.info("obsidian_updated", path=str(note_path))
            else:
                # Manual note exists, no auto markers — prepend auto content
                # Strip existing frontmatter if present
                body = existing
                if body.startswith("---"):
                    end_fm = body.find("---", 3)
                    if end_fm != -1:
                        body = body[end_fm + 3:].lstrip("\n")

                combined = (
                    frontmatter + "\n"
                    + auto_block
                    + "\n\n---\n\n"
                    + body
                )
                note_path.write_text(combined, encoding="utf-8")
                log.info("obsidian_prepended", path=str(note_path))
        else:
            # New file
            content = frontmatter + "\n" + auto_block
            note_path.write_text(content, encoding="utf-8")
            log.info("obsidian_created", path=str(note_path))
