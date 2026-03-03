"""Terminal history collector — parses zsh_history."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult

# zsh extended history format: : TIMESTAMP:DURATION;COMMAND
_ZSH_HISTORY_RE = re.compile(r"^:\s*(\d+):\d+;(.+)$")

# Commands worth highlighting
_INTERESTING_PREFIXES = (
    "docker", "git", "pip", "uv", "kubectl", "make", "ssh", "scp",
    "rsync", "deploy", "ansible", "terraform", "helm", "cargo",
    "npm", "yarn", "bun", "pnpm", "python", "pytest", "claude",
    "systemctl", "journalctl", "curl", "wget", "brew", "apt",
    "glab", "gh", "jq", "sed", "awk", "find", "xargs",
)


class TerminalCollector(BaseCollector):
    """Parse zsh history for interesting commands on the target date."""

    async def collect(self) -> CollectorResult:
        history_file = Path(
            self.config.get("history_file", str(Path.home() / ".zsh_history"))
        )
        boring = set(self.config.get("boring_commands", []))

        if not history_file.exists():
            return CollectorResult(
                source=self.name,
                success=False,
                error=f"History file not found: {history_file}",
            )

        # Use naive datetime so .timestamp() treats it as local time
        # (zsh history timestamps are epoch seconds — same reference frame)
        day_start = datetime.combine(
            self.target_date, datetime.min.time()
        ).timestamp()
        day_end = datetime.combine(
            self.target_date, datetime.max.time()
        ).timestamp()

        commands: list[dict] = []
        interesting: list[dict] = []

        # Read with errors='replace' to handle encoding issues
        raw = history_file.read_bytes()
        for line in raw.decode("utf-8", errors="replace").split("\n"):
            m = _ZSH_HISTORY_RE.match(line)
            if not m:
                continue

            ts = int(m.group(1))
            cmd = m.group(2).strip()

            if not (day_start <= ts <= day_end):
                continue
            if len(cmd) < 5:
                continue

            base_cmd = cmd.split()[0].split("/")[-1] if cmd.split() else ""
            if base_cmd in boring:
                continue

            entry = {
                "time": datetime.fromtimestamp(ts).strftime("%H:%M"),
                "command": cmd,
            }
            commands.append(entry)

            if any(cmd.startswith(p) for p in _INTERESTING_PREFIXES):
                interesting.append(entry)

        return CollectorResult(
            source=self.name,
            data={
                "total_commands": len(commands),
                "interesting_commands": interesting,
                "all_commands": commands,
            },
            summary=f"{len(commands)} commands, {len(interesting)} interesting",
        )
