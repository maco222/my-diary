"""Google Calendar collector — events on target date."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from my_diary.auth.google_oauth import get_google_credentials
from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class GoogleCalendarCollector(BaseCollector):
    """Collect Google Calendar events for the target date."""

    async def collect(self) -> CollectorResult:
        creds = get_google_credentials()
        if not creds:
            return CollectorResult(
                source=self.name,
                success=False,
                error="Google OAuth credentials not available. Run setup first.",
            )

        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=creds)

        time_min = datetime.combine(
            self.target_date, datetime.min.time(), tzinfo=timezone.utc
        ).isoformat()
        time_max = datetime.combine(
            self.target_date, datetime.max.time(), tzinfo=timezone.utc
        ).isoformat()

        request = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        events_result = await asyncio.to_thread(request.execute)

        events = []
        for event in events_result.get("items", []):
            start = event.get("start", {})
            end = event.get("end", {})
            attendees = event.get("attendees", [])

            # Find my response status (accepted/declined/tentative/needsAction)
            my_status = ""
            for a in attendees:
                if a.get("self", False):
                    my_status = a.get("responseStatus", "")
                    break

            events.append({
                "summary": event.get("summary", "(no title)"),
                "start": start.get("dateTime", start.get("date", "")),
                "end": end.get("dateTime", end.get("date", "")),
                "attendees": [
                    a.get("email", "") for a in attendees if not a.get("self", False)
                ],
                "attendee_count": len(attendees),
                "my_response": my_status,
                "description": (event.get("description", "") or "")[:200],
                "location": event.get("location", ""),
                "hangout_link": event.get("hangoutLink", ""),
                "html_link": event.get("htmlLink", ""),
                "status": event.get("status", ""),
            })

        return CollectorResult(
            source=self.name,
            data={"events": events, "total": len(events)},
            summary=f"{len(events)} calendar events",
        )
