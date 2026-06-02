from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_SLOTS = {"open", "midday", "close"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    aws_region: str
    s3_bucket: str | None
    public_base_url: str | None
    image_provider: str
    output_dir: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "market-river-generator"),
            aws_region=os.getenv("AWS_REGION", "us-west-2"),
            s3_bucket=_empty_to_none(os.getenv("S3_BUCKET")),
            public_base_url=_trim_base_url(os.getenv("PUBLIC_BASE_URL")),
            image_provider=os.getenv("IMAGE_PROVIDER", "mock").strip().lower(),
            output_dir=Path(os.getenv("OUTPUT_DIR", "runs")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def _empty_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def _trim_base_url(value: str | None) -> str | None:
    clean = _empty_to_none(value)
    return clean.rstrip("/") if clean else None


def parse_task_input_json(raw: str | None = None) -> dict[str, Any]:
    text = raw if raw is not None else os.getenv("TASK_INPUT_JSON")
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("TASK_INPUT_JSON must contain a JSON object")
    return parsed


def resolve_slot(cli_slot: str | None) -> str:
    task_input = parse_task_input_json()
    slot = cli_slot or task_input.get("slot") or os.getenv("SLOT") or "open"
    if not isinstance(slot, str) or slot not in VALID_SLOTS:
        valid = ", ".join(sorted(VALID_SLOTS))
        raise ValueError(f"slot must be one of: {valid}")
    return slot

