"""Notion collector — REST API for pages created/edited on target date."""

from __future__ import annotations

import httpx

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult

_NOTION_API_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


class NotionCollector(BaseCollector):
    """Collect Notion pages created or edited on the target date."""

    async def collect(self) -> CollectorResult:
        token = self.secrets.notion_api_token
        if not token:
            return CollectorResult(
                source=self.name,
                success=False,
                error="NOTION_API_TOKEN not set",
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            # Search for recently edited pages (paginated)
            all_pages: list[dict] = []
            start_cursor = None
            while True:
                body: dict = {
                    "filter": {"property": "object", "value": "page"},
                    "sort": {
                        "direction": "descending",
                        "timestamp": "last_edited_time",
                    },
                    "page_size": 100,
                }
                if start_cursor:
                    body["start_cursor"] = start_cursor

                resp = await client.post(f"{_NOTION_API_URL}/search", json=body)
                resp.raise_for_status()
                data = resp.json()
                all_pages.extend(data.get("results", []))

                # Stop paginating once we've gone past our target date
                results = data.get("results", [])
                if results:
                    last_edited = results[-1].get("last_edited_time", "")[:10]
                    if last_edited < self.target_date.isoformat():
                        break

                if not data.get("has_more"):
                    break
                start_cursor = data.get("next_cursor")

        date_str = self.target_date.isoformat()
        pages_today = []

        for page in all_pages:
            edited = page.get("last_edited_time", "")[:10]
            created = page.get("created_time", "")[:10]

            if edited != date_str and created != date_str:
                continue

            # Extract title from properties
            title = ""
            for prop in page.get("properties", {}).values():
                if prop.get("type") == "title":
                    title_parts = prop.get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                    break

            pages_today.append({
                "title": title or "(untitled)",
                "url": page.get("url", ""),
                "created": created == date_str,
                "edited": edited == date_str,
                "last_edited_time": page.get("last_edited_time", ""),
            })

        return CollectorResult(
            source=self.name,
            data={
                "pages": pages_today,
                "total": len(pages_today),
            },
            summary=f"{len(pages_today)} Notion pages touched",
        )
