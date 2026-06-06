from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from app.config import Settings, VALID_SLOTS, VALID_WEATHER_CONDITIONS, resolve_slot, resolve_weather_conditions
from app.image_model import get_image_provider, provider_prompt
from app.logging_utils import configure_logging, get_logger
from app.market import fetch_market_snapshot
from app.prompt_registry import load_active_prompt_template
from app.prompts import compose_prompt
from app.publish import Publisher
from app.state import caption_for_state, derive_visual_state


logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_dotenv()
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    run_id = uuid.uuid4().hex[:12]
    slot = "unknown"
    created_at = _utc_now()

    try:
        slot = resolve_slot(args.slot)
        weather_conditions = resolve_weather_conditions(args.weather)
        logger.info(
            "starting run",
            extra={
                "_run_id": run_id,
                "_slot": slot,
                "_provider": settings.image_provider,
                "_weather": ",".join(weather_conditions),
            },
        )

        market_snapshot = fetch_market_snapshot()
        prompt_template = load_active_prompt_template(settings)
        image_provider = get_image_provider(settings)
        publisher = Publisher(settings)
        model = _model_metadata(settings, image_provider.name)

        for weather_condition in weather_conditions:
            variant_run_id = _variant_run_id(run_id, weather_condition, weather_conditions)
            visual_state = derive_visual_state(market_snapshot, weather_condition=weather_condition, slot=slot)
            prompt = compose_prompt(visual_state, template=prompt_template)
            image = image_provider.generate_image(
                prompt_result=prompt,
                run_id=variant_run_id,
                output_dir=settings.output_dir / "generated",
                slot=slot,
                market_mood=visual_state["market_mood"],
                volatility_mood=visual_state["volatility_mood"],
            )

            metadata = _success_metadata(
                run_id=variant_run_id,
                slot=slot,
                created_at=created_at,
                market_snapshot=market_snapshot,
                visual_state=visual_state,
                prompt=prompt,
                model=model,
            )
            result = publisher.publish_success(
                metadata=metadata,
                image_path=image.path,
                image_content_type=image.content_type,
                image_format=image.format,
            )
            logger.info(
                "published run",
                extra={
                    "_run_id": variant_run_id,
                    "_slot": slot,
                    "_weather": weather_condition,
                    "_metadata_key": result.metadata.key,
                    "_latest_key": result.latest.key,
                },
            )
        return 0

    except Exception as exc:
        logger.exception("run failed", extra={"_run_id": run_id, "_slot": slot})
        try:
            Publisher(settings).publish_failure(_failure_metadata(run_id, slot, created_at, exc))
        except Exception:
            logger.exception("failed to publish failure metadata", extra={"_run_id": run_id, "_slot": slot})
        return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a symbolic market river image and manifest.")
    parser.add_argument("--slot", choices=sorted(VALID_SLOTS), help="Market day slot to generate.")
    parser.add_argument("--weather", choices=[*sorted(VALID_WEATHER_CONDITIONS), "all"], help="Weather variant to use.")
    return parser.parse_args(argv)


def _success_metadata(
    *,
    run_id: str,
    slot: str,
    created_at: str,
    market_snapshot: dict[str, Any],
    visual_state: dict[str, Any],
    prompt: Any,
    model: dict[str, Any],
) -> dict[str, Any]:
    rendered_prompt = provider_prompt(prompt)
    return {
        "id": f"{created_at[:10]}-{slot}-{run_id}",
        "run_id": run_id,
        "slot": slot,
        "weather": visual_state["weather"]["condition"],
        "created_at": created_at,
        "market_snapshot": market_snapshot,
        "derived_state": visual_state,
        "caption": caption_for_state(visual_state),
        "prompt": {
            "id": prompt.prompt_id,
            "template_version": prompt.template_version,
            "source": prompt.source,
            "template_sha256": prompt.template_sha256,
            "template_s3_key": prompt.template_s3_key,
            "active_s3_key": prompt.active_s3_key,
            "positive": prompt.positive_prompt,
            "negative": prompt.negative_prompt,
            "provider": rendered_prompt,
            "hash": _sha256(rendered_prompt),
        },
        "model": model,
        "outputs": {},
    }


def _model_metadata(settings: Settings, provider: str) -> dict[str, Any]:
    if provider == "fal":
        return {
            "provider": provider,
            "parameters": {
                "model": settings.fal_model,
                "image_size": settings.fal_image_size,
                "output_format": settings.fal_output_format,
                "num_inference_steps": settings.fal_num_inference_steps,
                "acceleration": settings.fal_acceleration,
                "enable_safety_checker": settings.fal_enable_safety_checker,
            },
        }
    if provider == "replicate":
        parameters: dict[str, Any] = {
            "model": settings.replicate_model,
            "aspect_ratio": settings.replicate_aspect_ratio,
            "resolution": settings.replicate_resolution,
            "output_format": settings.replicate_output_format,
            "output_quality": settings.replicate_output_quality,
            "safety_tolerance": settings.replicate_safety_tolerance,
        }
        if settings.replicate_seed is not None:
            parameters["seed"] = settings.replicate_seed
        return {"provider": provider, "parameters": parameters}
    return {"provider": provider, "parameters": {}}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _variant_run_id(base_run_id: str, weather_condition: str, weather_conditions: list[str]) -> str:
    if len(weather_conditions) == 1:
        return base_run_id
    return f"{base_run_id}-{weather_condition}"


def _failure_metadata(run_id: str, slot: str, created_at: str, exc: Exception) -> dict[str, Any]:
    return {
        "id": f"{created_at[:10]}-{slot}-{run_id}-failure",
        "run_id": run_id,
        "slot": slot,
        "created_at": created_at,
        "status": "failed",
        "error": {"type": exc.__class__.__name__, "message": str(exc)},
        "outputs": {},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    sys.exit(main())
