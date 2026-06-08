from __future__ import annotations

import hashlib

from app.config import Settings
from app.contracts import FailureMetadata, MarketSnapshot, ModelMetadata, PromptMetadata, RunMetadata, VisualState
from app.image_model import provider_prompt
from app.prompts import PromptResult
from app.state import caption_for_state


def success_metadata(
    *,
    run_id: str,
    slot: str,
    created_at: str,
    market_snapshot: MarketSnapshot,
    visual_state: VisualState,
    prompt: PromptResult,
    model: ModelMetadata,
) -> RunMetadata:
    rendered_prompt = provider_prompt(prompt)
    return RunMetadata(
        id=f"{created_at[:10]}-{slot}-{run_id}",
        run_id=run_id,
        slot=slot,
        weather=visual_state.weather.condition,
        created_at=created_at,
        market_snapshot=market_snapshot,
        derived_state=visual_state,
        caption=caption_for_state(visual_state),
        prompt=PromptMetadata(
            id=prompt.prompt_id,
            template_version=prompt.template_version,
            source=prompt.source,
            template_sha256=prompt.template_sha256,
            template_s3_key=prompt.template_s3_key,
            active_s3_key=prompt.active_s3_key,
            positive=prompt.positive_prompt,
            negative=prompt.negative_prompt,
            provider=rendered_prompt,
            hash=_sha256(rendered_prompt),
        ),
        model=model,
    )


def failure_metadata(run_id: str, slot: str, created_at: str, exc: Exception) -> FailureMetadata:
    return FailureMetadata(
        id=f"{created_at[:10]}-{slot}-{run_id}-failure",
        run_id=run_id,
        slot=slot,
        created_at=created_at,
        error_type=exc.__class__.__name__,
        error_message=str(exc),
    )


def model_metadata(settings: Settings, provider: str) -> ModelMetadata:
    if provider == "fal":
        return ModelMetadata(
            provider=provider,
            parameters={
                "model": settings.fal_model,
                "image_size": settings.fal_image_size,
                "output_format": settings.fal_output_format,
                "num_inference_steps": settings.fal_num_inference_steps,
                "acceleration": settings.fal_acceleration,
                "enable_safety_checker": settings.fal_enable_safety_checker,
            },
        )
    if provider == "replicate":
        parameters = {
            "model": settings.replicate_model,
            "aspect_ratio": settings.replicate_aspect_ratio,
            "resolution": settings.replicate_resolution,
            "output_format": settings.replicate_output_format,
            "output_quality": settings.replicate_output_quality,
            "safety_tolerance": settings.replicate_safety_tolerance,
        }
        if settings.replicate_seed is not None:
            parameters["seed"] = settings.replicate_seed
        return ModelMetadata(provider=provider, parameters=parameters)
    return ModelMetadata(provider=provider, parameters={})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
