from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, VALID_SLOTS, resolve_slot
from app.image_model import get_image_provider
from app.logging_utils import configure_logging, get_logger
from app.market import fetch_market_snapshot
from app.prompts import compose_prompt
from app.publish import Publisher
from app.state import caption_for_state, derive_visual_state


logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    run_id = uuid.uuid4().hex[:12]
    slot = "unknown"
    created_at = _utc_now()

    try:
        slot = resolve_slot(args.slot)
        logger.info("starting run", extra={"_run_id": run_id, "_slot": slot, "_provider": settings.image_provider})

        market_snapshot = fetch_market_snapshot()
        visual_state = derive_visual_state(market_snapshot)
        prompt = compose_prompt(visual_state)
        image_provider = get_image_provider(settings.image_provider)
        image = image_provider.generate_image(
            prompt_result=prompt,
            run_id=run_id,
            output_dir=settings.output_dir / "generated",
            slot=slot,
            market_mood=visual_state["market_mood"],
            volatility_mood=visual_state["volatility_mood"],
        )

        metadata = _success_metadata(
            run_id=run_id,
            slot=slot,
            created_at=created_at,
            market_snapshot=market_snapshot,
            visual_state=visual_state,
            prompt=prompt,
            provider=image.provider,
        )
        publisher = Publisher(settings)
        result = publisher.publish_success(
            metadata=metadata,
            image_path=image.path,
            image_content_type=image.content_type,
            image_format=image.format,
        )
        logger.info(
            "published run",
            extra={
                "_run_id": run_id,
                "_slot": slot,
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
    return parser.parse_args(argv)


def _success_metadata(
    *,
    run_id: str,
    slot: str,
    created_at: str,
    market_snapshot: dict[str, Any],
    visual_state: dict[str, Any],
    prompt: Any,
    provider: str,
) -> dict[str, Any]:
    return {
        "id": f"{created_at[:10]}-{slot}-{run_id}",
        "run_id": run_id,
        "slot": slot,
        "created_at": created_at,
        "market_snapshot": market_snapshot,
        "derived_state": visual_state,
        "caption": caption_for_state(visual_state),
        "prompt": {
            "template_version": prompt.template_version,
            "positive": prompt.positive_prompt,
            "negative": prompt.negative_prompt,
        },
        "model": {"provider": provider},
        "outputs": {},
    }


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

