"""Linear collector — GraphQL API."""

from __future__ import annotations

import httpx

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult

_LINEAR_API_URL = "https://api.linear.app/graphql"

_ISSUES_QUERY = """
query($after: DateTimeOrDuration!) {
  viewer {
    assignedIssues(
      filter: { updatedAt: { gte: $after } }
      first: 100
      orderBy: updatedAt
    ) {
      nodes {
        identifier
        title
        state { name type }
        priority
        labels { nodes { name } }
        updatedAt
        completedAt
        description
        url
        history(first: 20) {
          nodes {
            fromState { name }
            toState { name }
            createdAt
          }
        }
        comments(first: 10) {
          nodes {
            body
            createdAt
            user { name }
          }
        }
      }
    }
  }
}
"""


class LinearCollector(BaseCollector):
    """Collect Linear issues assigned to the user, updated on target date."""

    async def collect(self) -> CollectorResult:
        api_key = self.secrets.linear_api_key
        if not api_key:
            return CollectorResult(
                source=self.name,
                success=False,
                error="LINEAR_API_KEY not set",
            )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _LINEAR_API_URL,
                headers={
                    "Authorization": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "query": _ISSUES_QUERY,
                    "variables": {"after": self.start_iso},
                },
            )
            resp.raise_for_status()
            data = resp.json()

        errors = data.get("errors")
        if errors:
            return CollectorResult(
                source=self.name,
                success=False,
                error=str(errors),
            )

        issues_raw = (
            data.get("data", {})
            .get("viewer", {})
            .get("assignedIssues", {})
            .get("nodes", [])
        )

        completed = []
        in_progress = []
        created = []

        for issue in issues_raw:
            state = issue.get("state", {})
            state_type = state.get("type", "")
            parsed = {
                "id": issue.get("identifier", ""),
                "title": issue.get("title", ""),
                "state": state.get("name", ""),
                "state_type": state_type,
                "url": issue.get("url", ""),
                "labels": [l["name"] for l in issue.get("labels", {}).get("nodes", [])],
                "transitions": [
                    {
                        "from": h.get("fromState", {}).get("name", "") if h.get("fromState") else "",
                        "to": h.get("toState", {}).get("name", "") if h.get("toState") else "",
                        "at": h.get("createdAt", ""),
                    }
                    for h in issue.get("history", {}).get("nodes", [])
                ],
                "comments": [
                    {
                        "body": c.get("body", "")[:200],
                        "author": c.get("user", {}).get("name", ""),
                        "at": c.get("createdAt", ""),
                    }
                    for c in issue.get("comments", {}).get("nodes", [])
                ],
            }

            if state_type == "completed":
                completed.append(parsed)
            elif state_type in ("started", "unstarted"):
                in_progress.append(parsed)
            else:
                created.append(parsed)

        return CollectorResult(
            source=self.name,
            data={
                "completed": completed,
                "in_progress": in_progress,
                "other": created,
                "total": len(issues_raw),
            },
            summary=f"{len(completed)} completed, {len(in_progress)} in progress",
        )
