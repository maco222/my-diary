"""Google OAuth2 flow + token persistence."""

from __future__ import annotations

from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parents[3]
_CREDENTIALS_PATH = _PROJECT_DIR / "google_credentials.json"
_TOKEN_PATH = _PROJECT_DIR / "google_token.json"


_ALL_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def get_google_credentials():
    """Get valid Google OAuth2 credentials, refreshing or running flow as needed.

    Always uses _ALL_SCOPES so all Google collectors share one token.
    Returns None if credentials.json is not found (setup not done).
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    scopes = _ALL_SCOPES
    creds = None

    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception:
            pass

    if not _CREDENTIALS_PATH.exists():
        return None

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_PATH), scopes)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def _save_token(creds) -> None:
    """Persist token to disk."""
    _TOKEN_PATH.write_text(creds.to_json())
