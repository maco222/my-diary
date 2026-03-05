"""Obsidian note collector — reads existing manual note for the target date."""

from __future__ import annotations

from pathlib import Path

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult

_AUTO_START = "%% AUTO-GENERATED-START %%"
_AUTO_END = "%% AUTO-GENERATED-END %%"


class ObsidianNoteCollector(BaseCollector):
    """Read existing Obsidian daily note to provide manual content as context for synthesis."""

    async def collect(self) -> CollectorResult:
        vault_path = self.config.get("vault_path", "")
        daily_subdir = self.config.get("daily_subdir", "Daily")

        if not vault_path:
            return CollectorResult(
                source=self.name,
                success=False,
                error="vault_path not configured",
            )

        note_path = Path(vault_path).expanduser() / daily_subdir / f"{self.target_date.isoformat()}.md"

        if not note_path.exists():
            return CollectorResult(
                source=self.name,
                data={"has_manual_note": False},
                summary="No existing note",
            )

        raw = note_path.read_text(encoding="utf-8")

        # Strip frontmatter
        body = raw
        if body.startswith("---"):
            end_fm = body.find("---", 3)
            if end_fm != -1:
                body = body[end_fm + 3:].lstrip("\n")

        # Strip auto-generated section — we only want manual content
        if _AUTO_START in body and _AUTO_END in body:
            start_idx = body.index(_AUTO_START)
            end_idx = body.index(_AUTO_END) + len(_AUTO_END)
            body = (body[:start_idx] + body[end_idx:]).strip()

        if not body.strip():
            return CollectorResult(
                source=self.name,
                data={"has_manual_note": False},
                summary="Note exists but no manual content",
            )

        return CollectorResult(
            source=self.name,
            data={
                "has_manual_note": True,
                "manual_content": body.strip(),
            },
            summary=f"Manual note found ({len(body.strip())} chars)",
        )
