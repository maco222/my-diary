"""Collector registry."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from my_diary.collectors.base import BaseCollector
    from my_diary.config import AppConfig, Secrets

# Registry: name → module.ClassName
_COLLECTOR_MAP: dict[str, str] = {
    "local_git": "my_diary.collectors.local_git.LocalGitCollector",
    "terminal": "my_diary.collectors.terminal.TerminalCollector",
    "filesystem": "my_diary.collectors.filesystem.FilesystemCollector",
    "weather": "my_diary.collectors.weather.WeatherCollector",
    "gitlab": "my_diary.collectors.gitlab.GitLabCollector",
    "linear": "my_diary.collectors.linear.LinearCollector",
    "notion": "my_diary.collectors.notion.NotionCollector",
    "slack": "my_diary.collectors.slack.SlackCollector",
    "google_cal": "my_diary.collectors.google_cal.GoogleCalendarCollector",
    "google_drive": "my_diary.collectors.google_drive.GoogleDriveCollector",
    "gmail": "my_diary.collectors.gmail.GmailCollector",
}


def _import_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_collectors(
    config: AppConfig,
    secrets: Secrets,
    target_date: date,
    filter_names: list[str] | None = None,
) -> list[BaseCollector]:
    """Instantiate enabled collectors, optionally filtered by name."""
    collectors = []
    for name, dotted_path in _COLLECTOR_MAP.items():
        if filter_names and name not in filter_names:
            continue

        collector_cfg = config.collectors.get(name, {})
        if isinstance(collector_cfg, dict) and not collector_cfg.get("enabled", True):
            continue

        try:
            cls = _import_class(dotted_path)
            collectors.append(cls(
                name=name,
                config=collector_cfg if isinstance(collector_cfg, dict) else {},
                secrets=secrets,
                target_date=target_date,
            ))
        except Exception as e:
            import structlog
            structlog.get_logger().warning("collector_import_failed", name=name, error=str(e))

    return collectors
