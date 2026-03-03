"""Base writer ABC."""

from __future__ import annotations

import abc
from datetime import date
from typing import Any

from my_diary.config import Secrets
from my_diary.models import CollectorResult, DiaryEntry


class BaseWriter(abc.ABC):
    """Abstract base writer."""

    def __init__(self, name: str, config: Any, secrets: Secrets):
        self.name = name
        self.config = config
        self.secrets = secrets

    @abc.abstractmethod
    async def write(
        self,
        entry: DiaryEntry,
        collector_results: list[CollectorResult],
        target_date: date,
    ) -> None:
        """Write the diary entry to the target destination."""
        ...
