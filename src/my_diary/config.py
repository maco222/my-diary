"""Configuration loading from YAML + .env."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.yaml"


class CollectorConfig(BaseModel):
    enabled: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class SynthesisConfig(BaseModel):
    model: str = "sonnet"
    language: str = "pl"
    user_name: str = ""


class MarkdownWriterConfig(BaseModel):
    enabled: bool = True
    output_dir: str = "./output"


class ObsidianWriterConfig(BaseModel):
    enabled: bool = True
    vault_path: str = ""
    daily_subdir: str = "Daily"


class NotionWriterConfig(BaseModel):
    enabled: bool = True
    database_name: str = "Daily Diary"
    database_id: str = ""  # If set, skip search — use this DB directly


class WritersConfig(BaseModel):
    markdown: MarkdownWriterConfig = Field(default_factory=MarkdownWriterConfig)
    obsidian: ObsidianWriterConfig = Field(default_factory=ObsidianWriterConfig)
    notion: NotionWriterConfig = Field(default_factory=NotionWriterConfig)


class Secrets(BaseSettings):
    """Secrets loaded from environment / .env file."""

    linear_api_key: str = ""
    slack_user_token: str = ""
    notion_api_token: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


class AppConfig(BaseModel):
    collectors: dict[str, Any] = Field(default_factory=dict)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)
    writers: WritersConfig = Field(default_factory=WritersConfig)


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load configuration from YAML file."""
    path = config_path or _default_config_path()
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}
    return AppConfig.model_validate(raw)


def load_secrets() -> Secrets:
    """Load secrets from .env file."""
    load_dotenv()
    return Secrets()
