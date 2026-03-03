"""Notion writer — creates or updates a page in a Notion database."""

from __future__ import annotations

from datetime import date

import httpx
import structlog

from my_diary.models import CollectorResult, DiaryEntry
from my_diary.writers.base import BaseWriter

log = structlog.get_logger()

_NOTION_API_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"

_AUTO_TAG = "auto-generated"


class NotionWriter(BaseWriter):
    """Write diary entry as a Notion page in a database.

    - If auto-generated page for the date exists → replace its content
    - If manual page for the date exists → append diary content at the end
    - If no page exists → create new
    """

    async def write(
        self,
        entry: DiaryEntry,
        collector_results: list[CollectorResult],
        target_date: date,
    ) -> None:
        token = self.secrets.notion_api_token
        if not token:
            raise RuntimeError("NOTION_API_TOKEN not set")

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            db_id = await self._get_database_id(client)
            db_props = await self._ensure_db_properties(client, db_id)
            existing = await self._find_existing_page(
                client, db_id, target_date, has_date_prop="Date" in db_props
            )

            if existing:
                page_id = existing["id"]
                is_auto = self._is_auto_generated(existing)

                if is_auto:
                    await self._delete_all_blocks(client, page_id)
                    await self._append_blocks(client, page_id, self._build_blocks(entry))
                    log.info("notion_page_updated", date=str(target_date))
                else:
                    separator = [_paragraph(""), _heading2("--- Auto-generated diary ---")]
                    await self._append_blocks(
                        client, page_id, separator + self._build_blocks(entry)
                    )
                    await self._add_auto_tag(client, page_id)
                    log.info("notion_page_appended", date=str(target_date))
            else:
                await self._create_page(client, db_id, entry, target_date)
                log.info("notion_page_created", date=str(target_date))

    async def _get_database_id(self, client: httpx.AsyncClient) -> str:
        if self.config.database_id:
            return self.config.database_id

        db_name = self.config.database_name
        resp = await client.post(
            f"{_NOTION_API_URL}/search",
            json={
                "query": db_name,
                "filter": {"property": "object", "value": "database"},
            },
        )
        resp.raise_for_status()

        for db in resp.json().get("results", []):
            title_parts = db.get("title", [])
            title = "".join(t.get("plain_text", "") for t in title_parts)
            if title == db_name:
                return db["id"]

        raise RuntimeError(
            f"Notion database '{db_name}' not found. "
            f"Create it manually and set database_id in config.yaml."
        )

    async def _ensure_db_properties(
        self, client: httpx.AsyncClient, db_id: str
    ) -> dict[str, str]:
        """Check DB schema and add missing Date/Tags properties. Return property name→type map."""
        resp = await client.get(f"{_NOTION_API_URL}/databases/{db_id}")
        resp.raise_for_status()
        props = resp.json().get("properties", {})
        existing = {name: p["type"] for name, p in props.items()}

        updates: dict = {}
        if "Date" not in existing:
            updates["Date"] = {"date": {}}
        if "Tags" not in existing:
            updates["Tags"] = {"multi_select": {}}

        if updates:
            resp = await client.patch(
                f"{_NOTION_API_URL}/databases/{db_id}",
                json={"properties": updates},
            )
            resp.raise_for_status()
            log.info("notion_db_properties_added", added=list(updates.keys()))
            existing.update({k: list(v.keys())[0] for k, v in updates.items()})

        return existing

    async def _find_existing_page(
        self,
        client: httpx.AsyncClient,
        db_id: str,
        target_date: date,
        has_date_prop: bool = True,
    ) -> dict | None:
        """Find a page in the database for the given date."""
        if has_date_prop:
            query_filter = {
                "property": "Date",
                "date": {"equals": target_date.isoformat()},
            }
        else:
            # Fallback: search by title prefix
            weekday_names_pl = [
                "poniedziałek", "wtorek", "środa", "czwartek",
                "piątek", "sobota", "niedziela",
            ]
            weekday = weekday_names_pl[target_date.weekday()]
            title_prefix = f"Dziennik — {target_date.isoformat()} ({weekday})"
            query_filter = {
                "property": "Name",
                "title": {"equals": title_prefix},
            }

        resp = await client.post(
            f"{_NOTION_API_URL}/databases/{db_id}/query",
            json={"filter": query_filter, "page_size": 1},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    @staticmethod
    def _is_auto_generated(page: dict) -> bool:
        tags_prop = page.get("properties", {}).get("Tags", {})
        if tags_prop.get("type") == "multi_select":
            return any(
                opt.get("name") == _AUTO_TAG
                for opt in tags_prop.get("multi_select", [])
            )
        return False

    async def _delete_all_blocks(self, client: httpx.AsyncClient, page_id: str) -> None:
        start_cursor = None
        while True:
            url = f"{_NOTION_API_URL}/blocks/{page_id}/children?page_size=100"
            if start_cursor:
                url += f"&start_cursor={start_cursor}"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            for block in data.get("results", []):
                await client.delete(f"{_NOTION_API_URL}/blocks/{block['id']}")
            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")

    async def _append_blocks(
        self, client: httpx.AsyncClient, page_id: str, blocks: list[dict]
    ) -> None:
        for i in range(0, len(blocks), 100):
            chunk = blocks[i : i + 100]
            resp = await client.patch(
                f"{_NOTION_API_URL}/blocks/{page_id}/children",
                json={"children": chunk},
            )
            resp.raise_for_status()

    async def _add_auto_tag(self, client: httpx.AsyncClient, page_id: str) -> None:
        resp = await client.patch(
            f"{_NOTION_API_URL}/pages/{page_id}",
            json={
                "properties": {
                    "Tags": {
                        "multi_select": [
                            {"name": "daily-diary"},
                            {"name": _AUTO_TAG},
                        ]
                    }
                }
            },
        )
        resp.raise_for_status()

    async def _create_page(
        self,
        client: httpx.AsyncClient,
        db_id: str,
        entry: DiaryEntry,
        target_date: date,
    ) -> None:
        weekday_names_pl = [
            "poniedziałek", "wtorek", "środa", "czwartek",
            "piątek", "sobota", "niedziela",
        ]
        weekday = weekday_names_pl[target_date.weekday()]
        title = f"Dziennik — {target_date.isoformat()} ({weekday})"
        children = self._build_blocks(entry)

        resp = await client.post(
            f"{_NOTION_API_URL}/pages",
            json={
                "parent": {"database_id": db_id},
                "properties": {
                    "Name": {"title": [{"text": {"content": title}}]},
                    "Date": {"date": {"start": target_date.isoformat()}},
                    "Tags": {
                        "multi_select": [
                            {"name": "daily-diary"},
                            {"name": _AUTO_TAG},
                        ]
                    },
                },
                "children": children,
            },
        )
        resp.raise_for_status()

    def _build_blocks(self, entry: DiaryEntry) -> list[dict]:
        blocks: list[dict] = []

        if entry.tldr:
            blocks.append(_heading2("TL;DR"))
            blocks.append(_paragraph(entry.tldr))

        if entry.key_decisions:
            blocks.append(_heading2("Kluczowe decyzje i ustalenia"))
            for decision in entry.key_decisions:
                blocks.append(_bulleted_list_item(decision))

        narratives = [
            ("Development", entry.development_narrative),
            ("Zadania (Linear)", entry.tasks_narrative),
            ("Dokumentacja", entry.documents_narrative),
            ("Komunikacja (Slack)", entry.communication_narrative),
            ("Spotkania (Calendar)", entry.meetings_narrative),
            ("Aktywność lokalna", entry.local_activity_narrative),
        ]
        for heading, text in narratives:
            if text:
                blocks.append(_heading2(heading))
                blocks.append(_paragraph(text))

        if entry.action_items:
            blocks.append(_heading2("Action items i follow-upy"))
            for item in entry.action_items:
                blocks.append(_to_do(item))

        return blocks


def _heading2(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _paragraph(text: str) -> dict:
    chunks = [text[i : i + 2000] for i in range(0, len(text), 2000)]
    if not chunks:
        chunks = [""]
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": chunk}} for chunk in chunks
            ]
        },
    }


def _bulleted_list_item(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        },
    }


def _to_do(text: str) -> dict:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [{"type": "text", "text": {"content": text}}],
            "checked": False,
        },
    }
