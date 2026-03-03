"""Pydantic models for my-diary."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class CollectorResult(BaseModel):
    """Result from a single collector."""

    source: str
    collected_at: datetime = Field(default_factory=datetime.now)
    success: bool = True
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""

    @property
    def has_data(self) -> bool:
        return self.success and bool(self.data)


class DiaryEntry(BaseModel):
    """AI-synthesized diary entry."""

    target_date: date
    tldr: str = ""
    key_decisions: list[str] = Field(default_factory=list)
    development_narrative: str = ""
    tasks_narrative: str = ""
    communication_narrative: str = ""
    local_activity_narrative: str = ""
    meetings_narrative: str = ""
    documents_narrative: str = ""
    action_items: list[str] = Field(default_factory=list)
    raw_sections: dict[str, str] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    """Result of the full pipeline run."""

    target_date: date
    collector_results: list[CollectorResult] = Field(default_factory=list)
    diary_entry: DiaryEntry | None = None
    write_results: dict[str, bool] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
