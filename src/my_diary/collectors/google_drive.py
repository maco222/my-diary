"""Google Drive & Docs collector — files modified on target date."""

from __future__ import annotations

import asyncio

from my_diary.auth.google_oauth import get_google_credentials
from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult


class GoogleDriveCollector(BaseCollector):
    """Collect Google Drive files modified on the target date."""

    async def collect(self) -> CollectorResult:
        creds = get_google_credentials()
        if not creds:
            return CollectorResult(
                source=self.name,
                success=False,
                error="Google OAuth credentials not available. Run setup first.",
            )

        from googleapiclient.discovery import build

        drive = build("drive", "v3", credentials=creds)

        start_iso = f"{self.target_date.isoformat()}T00:00:00Z"
        end_iso = f"{self.target_date.isoformat()}T23:59:59Z"

        query = (
            f"modifiedTime >= '{start_iso}' and modifiedTime <= '{end_iso}' "
            f"and trashed = false"
        )

        request = drive.files().list(
            q=query,
            fields="files(id, name, mimeType, modifiedTime, webViewLink, owners, lastModifyingUser)",
            pageSize=100,
            orderBy="modifiedTime desc",
        )
        results = await asyncio.to_thread(request.execute)

        files = []
        for f in results.get("files", []):
            mime = f.get("mimeType", "")
            file_type = _mime_to_type(mime)

            files.append({
                "name": f.get("name", ""),
                "type": file_type,
                "mime_type": mime,
                "modified_time": f.get("modifiedTime", ""),
                "url": f.get("webViewLink", ""),
                "last_modified_by": (
                    f.get("lastModifyingUser", {}).get("displayName", "")
                ),
            })

        return CollectorResult(
            source=self.name,
            data={"files": files, "total": len(files)},
            summary=f"{len(files)} Drive files modified",
        )


def _mime_to_type(mime: str) -> str:
    """Map Google MIME type to human-readable type."""
    mime_map = {
        "application/vnd.google-apps.document": "Google Doc",
        "application/vnd.google-apps.spreadsheet": "Google Sheet",
        "application/vnd.google-apps.presentation": "Google Slides",
        "application/vnd.google-apps.form": "Google Form",
        "application/pdf": "PDF",
        "application/vnd.google-apps.folder": "Folder",
    }
    return mime_map.get(mime, mime.split("/")[-1] if "/" in mime else "unknown")
