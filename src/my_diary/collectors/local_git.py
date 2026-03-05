"""Local git repositories collector."""

from __future__ import annotations

import asyncio
from pathlib import Path

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class LocalGitCollector(BaseCollector):
    """Scan local git repos for commits by the user on the target date."""

    async def collect(self) -> CollectorResult:
        scan_paths = self.config.get("scan_paths", [str(Path.home() / "projects")])
        author_email = self.config.get("author_email", "")

        # Find all .git directories
        git_dirs: list[Path] = []
        for scan_path in scan_paths:
            root = Path(scan_path).expanduser()
            if not root.exists():
                continue
            for git_dir in root.rglob(".git"):
                if git_dir.is_dir() and not any(
                    p in git_dir.parts for p in ("node_modules", ".venv", "__pycache__")
                ):
                    git_dirs.append(git_dir.parent)

        # Collect commits from each repo
        repos_data: list[dict] = []
        date_str = self.target_date.isoformat()

        tasks = [
            self._collect_repo(repo, author_email, date_str) for repo in git_dirs
        ]
        results = await asyncio.gather(*tasks)

        for data in results:
            if data and data.get("commits"):
                repos_data.append(data)

        return CollectorResult(
            source=self.name,
            data={"repos": repos_data, "total_commits": sum(len(r["commits"]) for r in repos_data)},
            summary=f"Found {len(repos_data)} repos with commits",
        )

    async def _collect_repo(
        self, repo_path: Path, author_email: str, date_str: str
    ) -> dict | None:
        args = ["git", "-C", str(repo_path), "log"]
        if author_email:
            # Support multiple emails separated by comma — git --author takes regex
            pattern = r"\|".join(e.strip() for e in author_email.split(","))
            args.append(f"--author={pattern}")
        args.extend([
            f"--after={date_str}T00:00:00",
            f"--before={date_str}T23:59:59",
            "--format=%H|||%s|||%an|||%ai",
            "--all",
        ])

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0 or not stdout.strip():
            return None

        commits = []
        for line in stdout.decode().strip().split("\n"):
            if not line.strip():
                continue
            parts = line.strip().split("|||")
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                })

        if not commits:
            return None

        # Get current branch
        proc2 = await asyncio.create_subprocess_exec(
            "git", "-C", str(repo_path), "branch", "--show-current",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        branch_out, _ = await proc2.communicate()
        branch = branch_out.decode().strip() if proc2.returncode == 0 else "unknown"

        return {
            "repo": repo_path.name,
            "path": str(repo_path),
            "branch": branch,
            "commits": commits,
        }
