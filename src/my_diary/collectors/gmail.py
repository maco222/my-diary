"""Gmail collector — emails sent and received on target date."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from my_diary.auth.google_oauth import get_google_credentials
from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class GmailCollector(BaseCollector):
    """Collect Gmail messages sent and received on the target date."""

    async def collect(self) -> CollectorResult:
        creds = get_google_credentials()
        if not creds:
            return CollectorResult(
                source=self.name,
                success=False,
                error="Google OAuth credentials not available. Run setup first.",
            )

        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=creds)

        # Gmail date filter is exclusive on "before", so we need day+1
        date_query = self.target_date.strftime("%Y/%m/%d")
        next_day = (self.target_date + timedelta(days=1)).strftime("%Y/%m/%d")
        date_filter = f"after:{date_query} before:{next_day}"

        sent = await self._list_messages(service, f"in:sent {date_filter}")
        received = await self._list_messages(service, f"in:inbox {date_filter}")

        return CollectorResult(
            source=self.name,
            data={
                "sent": sent,
                "received": received,
                "total_sent": len(sent),
                "total_received": len(received),
            },
            summary=f"{len(sent)} sent, {len(received)} received",
        )

    async def _list_messages(self, service, query: str) -> list[dict]:
        """Fetch messages matching query and extract headers."""
        # Let API errors (403, 401) propagate — they indicate setup issues
        request = service.users().messages().list(
            userId="me", q=query, maxResults=50,
        )
        resp = await asyncio.to_thread(request.execute)

        results = []
        for msg_ref in resp.get("messages", []):
            try:
                request = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Date"],
                )
                msg = await asyncio.to_thread(request.execute)

                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }

                results.append({
                    "subject": headers.get("Subject", "(no subject)"),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", "")[:200],
                })
            except Exception:
                continue

        return results
