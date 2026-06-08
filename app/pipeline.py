from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from app.config import Settings
from app.contracts import FailureMetadata, MarketSnapshot, RunMetadata, RunRequest
from app.image_model import GeneratedImage, ImageProvider, get_image_provider
from app.logging_utils import get_logger
from app.market import fetch_market_snapshot
from app.metadata import failure_metadata, model_metadata, success_metadata
from app.prompt_registry import load_active_prompt_template
from app.prompts import PromptTemplate, compose_prompt
from app.publish import PublishResult, Publisher
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
        model = model_metadata(dependencies.settings, dependencies.image_provider.name)
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

            metadata = success_metadata(
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


def _publish_success(publisher: PublisherProtocol, metadata: RunMetadata, image: GeneratedImage) -> PublishResult:
    return publisher.publish_success(
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
