"""Base collector with safe_collect wrapper."""

from __future__ import annotations

import abc
from datetime import date, datetime, time, timezone
from typing import Any

import structlog

from my_diary.config import Secrets
from my_diary.models import CollectorResult

log = structlog.get_logger()


class BaseCollector(abc.ABC):
    """Abstract base collector with graceful error handling."""

    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        secrets: Secrets,
        target_date: date,
    ):
        self.name = name
        self.config = config
        self.secrets = secrets
        self.target_date = target_date

    @property
    def start_dt(self) -> datetime:
        """Start of the target day (midnight UTC)."""
        return datetime.combine(self.target_date, time.min, tzinfo=timezone.utc)

    @property
    def end_dt(self) -> datetime:
        """End of the target day (23:59:59 UTC)."""
        return datetime.combine(self.target_date, time.max, tzinfo=timezone.utc)

    @property
    def start_iso(self) -> str:
        return self.start_dt.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end_dt.isoformat()

    @abc.abstractmethod
    async def collect(self) -> CollectorResult:
        """Collect data. Subclasses implement this."""
        ...

    async def safe_collect(self) -> CollectorResult:
        """Run collect() with exception handling — graceful degradation."""
        try:
            log.info("collecting", collector=self.name)
            result = await self.collect()
            log.info("collected", collector=self.name, success=result.success)
            return result
        except Exception as e:
            log.error("collector_failed", collector=self.name, error=str(e))
            return CollectorResult(
                source=self.name,
                success=False,
                error=str(e),
            )
