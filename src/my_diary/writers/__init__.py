"""Writer registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from my_diary.config import AppConfig, Secrets
    from my_diary.writers.base import BaseWriter

_WRITER_MAP: dict[str, str] = {
    "markdown": "my_diary.writers.markdown.MarkdownWriter",
    "obsidian": "my_diary.writers.obsidian.ObsidianWriter",
    "notion": "my_diary.writers.notion.NotionWriter",
}


def _import_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_writers(
    config: AppConfig,
    secrets: Secrets,
    filter_names: list[str] | None = None,
) -> list[BaseWriter]:
    """Instantiate enabled writers, optionally filtered by name."""
    writers = []
    writer_configs = {
        "markdown": config.writers.markdown,
        "obsidian": config.writers.obsidian,
        "notion": config.writers.notion,
    }

    for name, dotted_path in _WRITER_MAP.items():
        if filter_names and name not in filter_names:
            continue

        wcfg = writer_configs.get(name)
        if wcfg and not wcfg.enabled:
            continue

        try:
            cls = _import_class(dotted_path)
            writers.append(cls(name=name, config=wcfg, secrets=secrets))
        except Exception as e:
            import structlog
            structlog.get_logger().warning("writer_import_failed", name=name, error=str(e))

    return writers
