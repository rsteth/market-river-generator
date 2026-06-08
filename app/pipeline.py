from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from app.config import Settings
from app.contracts import (
    FailureMetadata,
    MarketSnapshot,
    ModelMetadata,
    PromptMetadata,
    RunMetadata,
    RunRequest,
    VisualState,
)
from app.image_model import GeneratedImage, ImageProvider, get_image_provider, provider_prompt
from app.logging_utils import get_logger
from app.market import fetch_market_snapshot
from app.prompt_registry import load_active_prompt_template
from app.prompts import PromptResult, PromptTemplate, compose_prompt
from app.publish import PublishResult, Publisher
from app.state import caption_for_state, derive_visual_state


logger = get_logger(__name__)


class MarketDataProvider(Protocol):
    def fetch_snapshot(self) -> MarketSnapshot:
        ...


class PromptTemplateProvider(Protocol):
    def load_template(self) -> PromptTemplate:
        ...


class PublisherProtocol(Protocol):
    def publish_success(
        self,
        *,
        metadata: RunMetadata,
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> PublishResult:
        ...

    def publish_failure(self, metadata: FailureMetadata) -> object:
        ...


@dataclass(frozen=True)
class PipelineDependencies:
    settings: Settings
    market_data: MarketDataProvider
    prompt_templates: PromptTemplateProvider
    image_provider: ImageProvider
    publisher: PublisherProtocol
    now: Callable[[], str]
    new_run_id: Callable[[], str]


@dataclass(frozen=True)
class PublishedVariant:
    weather: str
    run_id: str
    image_key: str | None
    metadata_key: str
    latest_key: str


@dataclass(frozen=True)
class RunResult:
    run_id: str
    slot: str
    created_at: str
    succeeded: bool
    variants: tuple[PublishedVariant, ...] = ()
    error_type: str | None = None
    error_message: str | None = None


class YFinanceMarketDataProvider:
    def fetch_snapshot(self) -> MarketSnapshot:
        return fetch_market_snapshot()


class ActivePromptTemplateProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load_template(self) -> PromptTemplate:
        return load_active_prompt_template(self.settings)


def default_dependencies(settings: Settings) -> PipelineDependencies:
    return PipelineDependencies(
        settings=settings,
        market_data=YFinanceMarketDataProvider(),
        prompt_templates=ActivePromptTemplateProvider(settings),
        image_provider=get_image_provider(settings),
        publisher=Publisher(settings),
        now=_utc_now,
        new_run_id=_new_run_id,
    )


def run_pipeline(request: RunRequest, dependencies: PipelineDependencies) -> RunResult:
    run_id = dependencies.new_run_id()
    created_at = dependencies.now()
    slot = request.slot

    try:
        logger.info(
            "starting run",
            extra={
                "_run_id": run_id,
                "_slot": slot,
                "_provider": dependencies.settings.image_provider,
                "_weather": ",".join(request.weather_conditions),
            },
        )

        market_snapshot = dependencies.market_data.fetch_snapshot()
        prompt_template = dependencies.prompt_templates.load_template()
        model = _model_metadata(dependencies.settings, dependencies.image_provider.name)
        published: list[PublishedVariant] = []

        for weather_condition in request.weather_conditions:
            variant_run_id = _variant_run_id(run_id, weather_condition, request.weather_conditions)
            visual_state = derive_visual_state(market_snapshot, weather_condition=weather_condition, slot=slot)
            prompt = compose_prompt(visual_state, template=prompt_template)
            image = dependencies.image_provider.generate_image(
                prompt_result=prompt,
                run_id=variant_run_id,
                output_dir=dependencies.settings.output_dir / "generated",
                slot=slot,
                market_mood=visual_state.market_mood,
                volatility_mood=visual_state.volatility_mood,
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
            publish_result = _publish_success(dependencies.publisher, metadata, image)
            published.append(
                PublishedVariant(
                    weather=weather_condition,
                    run_id=variant_run_id,
                    image_key=publish_result.image.key if publish_result.image else None,
                    metadata_key=publish_result.metadata.key,
                    latest_key=publish_result.latest.key,
                )
            )
            logger.info(
                "published run",
                extra={
                    "_run_id": variant_run_id,
                    "_slot": slot,
                    "_weather": weather_condition,
                    "_metadata_key": publish_result.metadata.key,
                    "_latest_key": publish_result.latest.key,
                },
            )
        return RunResult(
            run_id=run_id,
            slot=slot,
            created_at=created_at,
            succeeded=True,
            variants=tuple(published),
        )

    except Exception as exc:
        logger.exception("run failed", extra={"_run_id": run_id, "_slot": slot})
        try:
            dependencies.publisher.publish_failure(_failure_metadata(run_id, slot, created_at, exc))
        except Exception:
            logger.exception("failed to publish failure metadata", extra={"_run_id": run_id, "_slot": slot})
        return RunResult(
            run_id=run_id,
            slot=slot,
            created_at=created_at,
            succeeded=False,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )


def _publish_success(publisher: PublisherProtocol, metadata: RunMetadata, image: GeneratedImage) -> PublishResult:
    return publisher.publish_success(
        metadata=metadata,
        image_path=image.path,
        image_content_type=image.content_type,
        image_format=image.format,
    )


def _success_metadata(
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


def _model_metadata(settings: Settings, provider: str) -> ModelMetadata:
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


def _variant_run_id(base_run_id: str, weather_condition: str, weather_conditions: tuple[str, ...]) -> str:
    if len(weather_conditions) == 1:
        return base_run_id
    return f"{base_run_id}-{weather_condition}"


def _failure_metadata(run_id: str, slot: str, created_at: str, exc: Exception) -> FailureMetadata:
    return FailureMetadata(
        id=f"{created_at[:10]}-{slot}-{run_id}-failure",
        run_id=run_id,
        slot=slot,
        created_at=created_at,
        error_type=exc.__class__.__name__,
        error_message=str(exc),
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
