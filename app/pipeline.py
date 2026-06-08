from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, Protocol

from app.config import Settings
from app.contracts import FailureMetadata, ManifestItem, MarketSnapshot, PipelineRunArtifact, RunMetadata, RunRequest
from app.image_model import GeneratedImage, ImageProvider, get_image_provider
from app.logging_utils import get_logger
from app.market import fetch_market_snapshot
from app.metadata import failure_metadata, model_metadata, pipeline_run_artifact, success_metadata
from app.prompt_registry import load_active_prompt_template
from app.prompts import PromptTemplate, compose_prompt
from app.publish import PublishedObject, Publisher, StagedPublishResult
from app.state import derive_visual_state


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
    ) -> object:
        ...

    def stage_success(
        self,
        *,
        metadata: RunMetadata,
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> StagedPublishResult:
        ...

    def publish_latest_manifest(self, items: list[ManifestItem], *, updated_at: str) -> PublishedObject:
        ...

    def publish_failure(self, metadata: FailureMetadata) -> object:
        ...

    def publish_pipeline_run(self, artifact: PipelineRunArtifact) -> object:
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
    audit_artifact: PipelineRunArtifact | None = None

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

        market_fetch_started = perf_counter()
        market_snapshot = dependencies.market_data.fetch_snapshot()
        market_fetch_ms = _elapsed_ms(market_fetch_started)

        prompt_load_started = perf_counter()
        prompt_template = dependencies.prompt_templates.load_template()
        prompt_load_ms = _elapsed_ms(prompt_load_started)

        model = model_metadata(dependencies.settings, dependencies.image_provider.name)
        audit_artifact = pipeline_run_artifact(
            run_id=run_id,
            created_at=created_at,
            request=request,
            market_snapshot=market_snapshot,
            prompt_template=prompt_template,
            model=model,
        )
        dependencies.publisher.publish_pipeline_run(audit_artifact)
        staged_variants: list[tuple[str, str, StagedPublishResult]] = []

        for weather_condition in request.weather_conditions:
            variant_run_id = _variant_run_id(run_id, weather_condition, request.weather_conditions)
            visual_state = derive_visual_state(market_snapshot, weather_condition=weather_condition, slot=slot)

            prompt_compose_started = perf_counter()
            prompt = compose_prompt(visual_state, template=prompt_template)
            prompt_compose_ms = _elapsed_ms(prompt_compose_started)

            image_generation_started = perf_counter()
            image = dependencies.image_provider.generate_image(
                prompt_result=prompt,
                run_id=variant_run_id,
                output_dir=dependencies.settings.output_dir / "generated",
                slot=slot,
                market_mood=visual_state.market_mood,
                volatility_mood=visual_state.volatility_mood,
            )
            image_generation_ms = _elapsed_ms(image_generation_started)

            metadata = success_metadata(
                run_id=variant_run_id,
                slot=slot,
                created_at=created_at,
                market_snapshot=market_snapshot,
                visual_state=visual_state,
                prompt=prompt,
                model=model,
            )
            publish_started = perf_counter()
            staged = _stage_success(dependencies.publisher, metadata, image)
            publish_ms = _elapsed_ms(publish_started)
            staged_variants.append((weather_condition, variant_run_id, staged))
            logger.info(
                "staged run artifacts",
                extra={
                    "_run_id": variant_run_id,
                    "_slot": slot,
                    "_weather": weather_condition,
                    "_provider": dependencies.image_provider.name,
                    "_metadata_key": staged.metadata.key,
                    "_market_fetch_ms": market_fetch_ms,
                    "_prompt_load_ms": prompt_load_ms,
                    "_prompt_compose_ms": prompt_compose_ms,
                    "_image_generation_ms": image_generation_ms,
                    "_publish_ms": publish_ms,
                },
            )
        manifest_publish_started = perf_counter()
        latest = dependencies.publisher.publish_latest_manifest(
            [staged.manifest_item for _, _, staged in staged_variants],
            updated_at=created_at,
        )
        manifest_publish_ms = _elapsed_ms(manifest_publish_started)
        published = tuple(
            PublishedVariant(
                weather=weather_condition,
                run_id=variant_run_id,
                image_key=staged.image.key if staged.image else None,
                metadata_key=staged.metadata.key,
                latest_key=latest.key,
            )
            for weather_condition, variant_run_id, staged in staged_variants
        )
        logger.info(
            "published latest manifest",
            extra={
                "_run_id": run_id,
                "_slot": slot,
                "_provider": dependencies.image_provider.name,
                "_weather": ",".join(request.weather_conditions),
                "_latest_key": latest.key,
                "_manifest_publish_ms": manifest_publish_ms,
            },
        )
        dependencies.publisher.publish_pipeline_run(audit_artifact.with_status("succeeded"))
        return RunResult(
            run_id=run_id,
            slot=slot,
            created_at=created_at,
            succeeded=True,
            variants=published,
        )

    except Exception as exc:
        logger.exception("run failed", extra={"_run_id": run_id, "_slot": slot})
        try:
            if audit_artifact is not None:
                dependencies.publisher.publish_pipeline_run(
                    audit_artifact.with_status(
                        "failed",
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                )
            dependencies.publisher.publish_failure(failure_metadata(run_id, slot, created_at, exc))
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


def _stage_success(publisher: PublisherProtocol, metadata: RunMetadata, image: GeneratedImage) -> StagedPublishResult:
    return publisher.stage_success(
        metadata=metadata,
        image_path=image.path,
        image_content_type=image.content_type,
        image_format=image.format,
    )


def _variant_run_id(base_run_id: str, weather_condition: str, weather_conditions: tuple[str, ...]) -> str:
    if len(weather_conditions) == 1:
        return base_run_id
    return f"{base_run_id}-{weather_condition}"


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _elapsed_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
