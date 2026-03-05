"""GitLab collector — uses glab CLI (already authenticated via OAuth)."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from urllib.parse import urlencode

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class GitLabCollector(BaseCollector):
    """Collect GitLab activity via glab api subprocess."""

    async def collect(self) -> CollectorResult:
        # Cache username before parallel calls to avoid race condition
        await self._get_username()

        # Collect events, authored MRs, and review MRs in parallel
        events, authored_mrs, review_mrs = await asyncio.gather(
            self._get_events(),
            self._get_authored_mrs(),
            self._get_review_mrs(),
        )

        return CollectorResult(
            source=self.name,
            data={
                "events": events,
                "authored_mrs": authored_mrs,
                "review_mrs": review_mrs,
            },
            summary=(
                f"{len(events)} events, "
                f"{len(authored_mrs)} authored MRs, "
                f"{len(review_mrs)} review MRs"
            ),
        )

    async def _glab_api(self, endpoint: str, params: dict | None = None) -> list | dict:
        """Call glab api and return parsed JSON.

        glab api with relative paths (e.g. /events) resolves against the
        current project context, which fails for user-level endpoints.
        We build full URLs with query params embedded (--field/-f forces POST).
        """
        host = await self._get_host()
        url = f"https://{host}/api/v4{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"

        args = ["glab", "api", url]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"glab api failed: {stderr.decode()}")

        return json.loads(stdout.decode())

    async def _get_events(self) -> list[dict]:
        """Get user events for the target date."""
        try:
            # GitLab events API: after/before are exclusive, so widen the range
            day_before = (self.target_date - timedelta(days=1)).isoformat()
            day_after = (self.target_date + timedelta(days=1)).isoformat()
            raw = await self._glab_api("/events", {
                "after": day_before,
                "before": day_after,
                "per_page": "100",
            })
            if not isinstance(raw, list):
                return []
            return [
                {
                    "action": e.get("action_name", ""),
                    "target_type": e.get("target_type", ""),
                    "target_title": e.get("target_title", ""),
                    "project": e.get("project_id", ""),
                    "created_at": e.get("created_at", ""),
                }
                for e in raw
            ]
        except Exception:
            return []

    async def _get_authored_mrs(self) -> list[dict]:
        """Get MRs authored by the user, updated on target date."""
        try:
            raw = await self._glab_api("/merge_requests", {
                "scope": "all",
                "author_username": await self._get_username(),
                "updated_after": self.start_iso,
                "updated_before": self.end_iso,
                "per_page": "50",
            })
            if not isinstance(raw, list):
                return []
            return [self._parse_mr(mr) for mr in raw]
        except Exception:
            return []

    async def _get_review_mrs(self) -> list[dict]:
        """Get MRs where user is a reviewer, updated on target date."""
        try:
            raw = await self._glab_api("/merge_requests", {
                "scope": "all",
                "reviewer_username": await self._get_username(),
                "updated_after": self.start_iso,
                "updated_before": self.end_iso,
                "per_page": "50",
            })
            if not isinstance(raw, list):
                return []
            return [self._parse_mr(mr) for mr in raw]
        except Exception:
            return []

    async def _get_host(self) -> str:
        """Get the configured GitLab host (cached)."""
        if not hasattr(self, "_host"):
            proc = await asyncio.create_subprocess_exec(
                "glab", "config", "get", "host",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            self._host = stdout.decode().strip() if proc.returncode == 0 and stdout.strip() else "gitlab.com"
        return self._host

    async def _get_username(self) -> str:
        """Get current GitLab username."""
        if not hasattr(self, "_username"):
            user = await self._glab_api("/user")
            self._username = user.get("username", "")
        return self._username

    @staticmethod
    def _parse_mr(mr: dict) -> dict:
        return {
            "title": mr.get("title", ""),
            "state": mr.get("state", ""),
            "web_url": mr.get("web_url", ""),
            "source_branch": mr.get("source_branch", ""),
            "target_branch": mr.get("target_branch", ""),
            "updated_at": mr.get("updated_at", ""),
        }
