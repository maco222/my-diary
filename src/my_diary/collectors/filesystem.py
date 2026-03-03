"""Filesystem collector — recently modified files."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class FilesystemCollector(BaseCollector):
    """Find files modified on the target date."""

    async def collect(self) -> CollectorResult:
        scan_paths = self.config.get("scan_paths", [str(Path.home() / "projects")])
        exclude = self.config.get("exclude_patterns", [
            "node_modules", ".git", "__pycache__", ".venv", ".cache",
        ])

        date_str = self.target_date.isoformat()
        all_files: list[str] = []

        for scan_path in scan_paths:
            expanded = Path(scan_path).expanduser()
            if not expanded.exists():
                continue

            args = [
                "find", str(expanded), "-type", "f",
                "-newermt", f"{date_str} 00:00:00",
                "-not", "-newermt", f"{date_str} 23:59:59",
            ]
            for pat in exclude:
                args.extend(["-not", "-path", f"*/{pat}/*"])

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout.strip():
                all_files.extend(stdout.decode().strip().split("\n"))

        # Group by project / extension
        by_extension: dict[str, int] = defaultdict(int)
        by_project: dict[str, list[str]] = defaultdict(list)

        for f in all_files:
            p = Path(f)
            ext = p.suffix or "(no ext)"
            by_extension[ext] += 1

            # Try to extract project name from path
            parts = p.parts
            for scan_path in scan_paths:
                sp = Path(scan_path).parts
                if parts[: len(sp)] == sp and len(parts) > len(sp):
                    project = parts[len(sp)]
                    by_project[project].append(str(p.relative_to(scan_path)))
                    break

        return CollectorResult(
            source=self.name,
            data={
                "total_files": len(all_files),
                "by_extension": dict(sorted(by_extension.items(), key=lambda x: -x[1])),
                "by_project": {k: v for k, v in sorted(by_project.items())},
            },
            summary=f"{len(all_files)} files modified",
        )
