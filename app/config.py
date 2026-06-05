from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_SLOTS = {"open", "midday", "close"}
VALID_WEATHER_CONDITIONS = {"sunny", "cloudy", "rainy"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    aws_region: str
    s3_bucket: str | None
    public_base_url: str | None
    image_provider: str
    fal_model: str
    fal_image_size: str
    fal_output_format: str
    fal_num_inference_steps: int
    fal_acceleration: str
    fal_enable_safety_checker: bool
    replicate_model: str
    replicate_aspect_ratio: str
    replicate_resolution: str
    replicate_output_format: str
    replicate_output_quality: int
    replicate_safety_tolerance: int
    replicate_seed: int | None
    output_dir: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "market-river-generator"),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            s3_bucket=_empty_to_none(os.getenv("S3_BUCKET")),
            public_base_url=_trim_base_url(os.getenv("PUBLIC_BASE_URL")),
            image_provider=os.getenv("IMAGE_PROVIDER", "mock").strip().lower(),
            fal_model=os.getenv("FAL_MODEL", "fal-ai/flux/schnell").strip(),
            fal_image_size=os.getenv("FAL_IMAGE_SIZE", "landscape_4_3").strip(),
            fal_output_format=os.getenv("FAL_OUTPUT_FORMAT", "jpeg").strip().lower(),
            fal_num_inference_steps=_int_from_env("FAL_NUM_INFERENCE_STEPS", default=4),
            fal_acceleration=os.getenv("FAL_ACCELERATION", "none").strip().lower(),
            fal_enable_safety_checker=_bool_from_env("FAL_ENABLE_SAFETY_CHECKER", default=True),
            replicate_model=os.getenv("REPLICATE_MODEL", "black-forest-labs/flux-2-pro").strip(),
            replicate_aspect_ratio=os.getenv("REPLICATE_ASPECT_RATIO", "4:3").strip(),
            replicate_resolution=os.getenv("REPLICATE_RESOLUTION", "1 MP").strip(),
            replicate_output_format=os.getenv("REPLICATE_OUTPUT_FORMAT", "webp").strip().lower(),
            replicate_output_quality=_int_from_env("REPLICATE_OUTPUT_QUALITY", default=88),
            replicate_safety_tolerance=_int_from_env("REPLICATE_SAFETY_TOLERANCE", default=2),
            replicate_seed=_optional_int_from_env("REPLICATE_SEED"),
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


def _int_from_env(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _optional_int_from_env(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _bool_from_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


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


def resolve_weather_condition(cli_weather: str | None) -> str:
    task_input = parse_task_input_json()
    weather = (
        cli_weather
        or task_input.get("weather")
        or task_input.get("weather_condition")
        or os.getenv("WEATHER_CONDITION")
        or "sunny"
    )
    if not isinstance(weather, str):
        raise ValueError("weather condition must be a string")
    normalized = weather.strip().lower()
    if normalized not in VALID_WEATHER_CONDITIONS:
        valid = ", ".join(sorted(VALID_WEATHER_CONDITIONS))
        raise ValueError(f"weather condition must be one of: {valid}")
    return normalized
