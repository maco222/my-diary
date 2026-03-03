"""AI synthesis engine — calls claude CLI in non-interactive mode."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date

import structlog

from my_diary.models import CollectorResult, DiaryEntry
from my_diary.synthesis.prompts import build_prompt

log = structlog.get_logger()


class SynthesisEngine:
    def __init__(self, model: str = "sonnet", language: str = "pl", user_name: str = ""):
        self.model = model
        self.language = language
        self.user_name = user_name

    async def synthesize(
        self, collector_results: list[CollectorResult], target_date: date
    ) -> DiaryEntry:
        """Run Claude CLI to synthesize collector data into a diary entry."""
        prompt = build_prompt(collector_results, target_date, user_name=self.user_name)

        log.debug("synthesis_prompt_length", chars=len(prompt))

        # Strip CLAUDECODE env var so claude CLI doesn't refuse to run
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        proc = await asyncio.create_subprocess_exec(
            "claude", "-p",
            "--output-format", "json",
            "--model", self.model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()),
                timeout=300,  # 5 minutes
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("claude CLI timed out after 5 minutes")

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"claude CLI failed (rc={proc.returncode}): {error_msg}")

        raw_output = stdout.decode().strip()
        log.debug("synthesis_raw_output_length", chars=len(raw_output))

        # Parse the claude CLI JSON output
        # The output format is {"type":"result","subtype":"success","cost_usd":...,"result":"..."}
        try:
            cli_response = json.loads(raw_output)
            result_text = cli_response.get("result", raw_output)
        except json.JSONDecodeError:
            result_text = raw_output

        # Parse the actual diary content from result_text
        diary_data = self._parse_result(result_text)

        return DiaryEntry(
            target_date=target_date,
            **diary_data,
        )

    def _parse_result(self, result_text: str) -> dict:
        """Parse the AI result text into diary entry fields."""
        import re

        # Try direct JSON parse first
        try:
            data = json.loads(result_text)
            if isinstance(data, dict):
                return self._normalize_fields(data)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks (various formats)
        # Match ```json ... ``` or ``` ... ``` with flexible whitespace
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", result_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1).strip())
                if isinstance(data, dict):
                    return self._normalize_fields(data)
            except json.JSONDecodeError:
                pass

        # Try finding the first { ... } block (outermost braces)
        brace_match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
                if isinstance(data, dict):
                    return self._normalize_fields(data)
            except json.JSONDecodeError:
                pass

        # Fallback: use the raw text as tldr
        log.warning("synthesis_parse_fallback", text_length=len(result_text))
        return {"tldr": result_text[:500], "raw_sections": {"full_text": result_text}}

    @staticmethod
    def _normalize_fields(data: dict) -> dict:
        """Ensure all expected fields exist with correct types."""
        fields = {
            "tldr": "",
            "key_decisions": [],
            "development_narrative": "",
            "tasks_narrative": "",
            "communication_narrative": "",
            "meetings_narrative": "",
            "documents_narrative": "",
            "local_activity_narrative": "",
            "action_items": [],
        }
        result = {}
        for key, default in fields.items():
            val = data.get(key, default)
            if isinstance(default, list) and not isinstance(val, list):
                val = [val] if val else []
            if isinstance(default, str) and not isinstance(val, str):
                val = str(val) if val else ""
            result[key] = val
        return result
