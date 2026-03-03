"""Slack collector — messages sent/received via Slack Web API."""

from __future__ import annotations

from slack_sdk.web.async_client import AsyncWebClient

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class SlackCollector(BaseCollector):
    """Collect Slack messages sent and received on target date."""

    async def collect(self) -> CollectorResult:
        token = self.secrets.slack_user_token
        if not token:
            return CollectorResult(
                source=self.name,
                success=False,
                error="SLACK_USER_TOKEN not set",
            )

        client = AsyncWebClient(token=token)
        date_str = self.target_date.isoformat()

        # Search messages sent by me and mentions of me
        sent, mentions = await self._search_messages(client, date_str)

        # Collect unique channels
        channels = set()
        for msg in sent + mentions:
            ch = msg.get("channel", {})
            if isinstance(ch, dict):
                channels.add(ch.get("name", ""))

        return CollectorResult(
            source=self.name,
            data={
                "sent": sent,
                "mentions": mentions,
                "channels_active": list(channels),
                "total_sent": len(sent),
                "total_mentions": len(mentions),
            },
            summary=f"{len(sent)} sent, {len(mentions)} mentions",
        )

    async def _search_messages(
        self, client: AsyncWebClient, date_str: str
    ) -> tuple[list[dict], list[dict]]:
        sent: list[dict] = []
        mentions: list[dict] = []

        # Messages sent by me on the target date
        try:
            resp = await client.search_messages(
                query=f"from:me on:{date_str}",
                sort="timestamp",
                count=100,
            )
            for match in resp.get("messages", {}).get("matches", []):
                sent.append(self._parse_message(match))
        except Exception:
            pass

        # Messages mentioning me
        try:
            resp = await client.search_messages(
                query=f"to:me on:{date_str}",
                sort="timestamp",
                count=100,
            )
            for match in resp.get("messages", {}).get("matches", []):
                mentions.append(self._parse_message(match))
        except Exception:
            pass

        return sent, mentions

    @staticmethod
    def _parse_message(match: dict) -> dict:
        channel = match.get("channel", {})
        return {
            "text": match.get("text", "")[:500],
            "channel": channel.get("name", "") if isinstance(channel, dict) else str(channel),
            "timestamp": match.get("ts", ""),
            "permalink": match.get("permalink", ""),
        }
