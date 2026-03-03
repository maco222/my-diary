"""Pipeline orchestrator: collect → synthesize → write."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import structlog

from my_diary.collectors import get_collectors
from my_diary.config import AppConfig, Secrets
from my_diary.models import CollectorResult, DiaryEntry, PipelineResult
from my_diary.synthesis.engine import SynthesisEngine
from my_diary.writers import get_writers

log = structlog.get_logger()

_CACHE_DIR = Path(__file__).resolve().parents[2] / "output" / ".cache"


class Pipeline:
    def __init__(
        self,
        config: AppConfig,
        secrets: Secrets,
        target_date: date,
        dry_run: bool = False,
        retry_writers: bool = False,
        collector_filter: list[str] | None = None,
        writer_filter: list[str] | None = None,
    ):
        self.config = config
        self.secrets = secrets
        self.target_date = target_date
        self.dry_run = dry_run
        self.retry_writers = retry_writers
        self.collector_filter = collector_filter
        self.writer_filter = writer_filter

    async def run(self) -> PipelineResult:
        result = PipelineResult(target_date=self.target_date)

        if self.retry_writers:
            return await self._run_retry_writers(result)

        # Phase 1: Collect
        log.info("collecting", date=str(self.target_date))
        collector_results = await self._collect()
        result.collector_results = collector_results

        successful = [r for r in collector_results if r.has_data]
        log.info("collection_done", total=len(collector_results), successful=len(successful))

        if self.dry_run:
            return result

        if not successful:
            result.errors.append("No data collected from any source.")
            return result

        # Phase 2: Synthesize
        log.info("synthesizing")
        try:
            engine = SynthesisEngine(
                model=self.config.synthesis.model,
                language=self.config.synthesis.language,
                user_name=self.config.synthesis.user_name,
            )
            diary_entry = await engine.synthesize(successful, self.target_date)
            result.diary_entry = diary_entry
        except Exception as e:
            log.error("synthesis_failed", error=str(e))
            result.errors.append(f"Synthesis failed: {e}")
            return result

        # Save cache for --retry-writers
        self._save_cache(diary_entry, collector_results)

        # Phase 3: Write
        log.info("writing")
        result.write_results = await self._write(diary_entry, collector_results)

        return result

    async def _run_retry_writers(self, result: PipelineResult) -> PipelineResult:
        """Re-run writers using cached data from a previous run."""
        cache = self._load_cache()
        if not cache:
            result.errors.append(
                f"No cached data for {self.target_date}. Run full pipeline first."
            )
            return result

        diary_entry, collector_results = cache
        result.diary_entry = diary_entry
        result.collector_results = collector_results

        log.info("retry_writers", date=str(self.target_date))
        result.write_results = await self._write(diary_entry, collector_results)
        return result

    def _save_cache(
        self, entry: DiaryEntry, collector_results: list[CollectorResult]
    ) -> None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = _CACHE_DIR / f"{self.target_date.isoformat()}.json"
        cache_path.write_text(
            json.dumps({
                "entry": entry.model_dump(mode="json"),
                "collectors": [cr.model_dump(mode="json") for cr in collector_results],
            }, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.debug("cache_saved", path=str(cache_path))

    def _load_cache(self) -> tuple[DiaryEntry, list[CollectorResult]] | None:
        cache_path = _CACHE_DIR / f"{self.target_date.isoformat()}.json"
        if not cache_path.exists():
            return None

        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        entry = DiaryEntry.model_validate(raw["entry"])
        collectors = [CollectorResult.model_validate(cr) for cr in raw["collectors"]]
        log.debug("cache_loaded", path=str(cache_path))
        return entry, collectors

    async def _collect(self) -> list[CollectorResult]:
        collectors = get_collectors(
            self.config, self.secrets, self.target_date, self.collector_filter
        )
        tasks = [c.safe_collect() for c in collectors]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _write(
        self, entry: DiaryEntry, collector_results: list[CollectorResult]
    ) -> dict[str, bool]:
        writers = get_writers(self.config, self.secrets, self.writer_filter)
        results: dict[str, bool] = {}

        async def _run_writer(writer):
            try:
                await writer.write(entry, collector_results, self.target_date)
                results[writer.name] = True
                log.info("writer_done", writer=writer.name)
            except Exception as e:
                results[writer.name] = False
                log.error("writer_failed", writer=writer.name, error=str(e))

        await asyncio.gather(*[_run_writer(w) for w in writers])
        return results
