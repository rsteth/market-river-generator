from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class RunRequest:
    slot: str
    weather_conditions: tuple[str, ...]


@dataclass(frozen=True)
class InstrumentSnapshot:
    last: float | None
    previous_close: float | None
    change_pct: float | None
    as_of: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "InstrumentSnapshot":
        return cls(
            last=_optional_float(payload.get("last")),
            previous_close=_optional_float(payload.get("previous_close")),
            change_pct=_optional_float(payload.get("change_pct")),
            as_of=_optional_str(payload.get("as_of")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "last": self.last,
            "previous_close": self.previous_close,
            "change_pct": self.change_pct,
            "as_of": self.as_of,
        }


@dataclass(frozen=True)
class MarketSummary:
    spy_change_pct: float | None
    qqq_change_pct: float | None
    vix_change_pct: float | None
    avg_risk_change_pct: float | None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MarketSummary":
        return cls(
            spy_change_pct=_optional_float(payload.get("spy_change_pct")),
            qqq_change_pct=_optional_float(payload.get("qqq_change_pct")),
            vix_change_pct=_optional_float(payload.get("vix_change_pct")),
            avg_risk_change_pct=_optional_float(payload.get("avg_risk_change_pct")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "spy_change_pct": self.spy_change_pct,
            "qqq_change_pct": self.qqq_change_pct,
            "vix_change_pct": self.vix_change_pct,
            "avg_risk_change_pct": self.avg_risk_change_pct,
        }


@dataclass(frozen=True)
class MarketSnapshot:
    as_of: str
    source: str
    instruments: dict[str, InstrumentSnapshot]
    summary: MarketSummary
    errors: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "MarketSnapshot":
        instruments_payload = _mapping(payload.get("instruments"), "market_snapshot.instruments", allow_none=True)
        return cls(
            as_of=_required_str(payload, "as_of", default="unknown"),
            source=_required_str(payload, "source", default="unknown"),
            instruments={
                str(ticker): InstrumentSnapshot.from_mapping(_mapping(value, f"instruments.{ticker}"))
                for ticker, value in instruments_payload.items()
            },
            summary=MarketSummary.from_mapping(_mapping(payload.get("summary"), "market_snapshot.summary", allow_none=True)),
            errors={str(key): str(value) for key, value in _mapping(payload.get("errors"), "errors", allow_none=True).items()},
        )

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "as_of": self.as_of,
            "source": self.source,
            "instruments": {ticker: instrument.to_dict() for ticker, instrument in self.instruments.items()},
            "summary": self.summary.to_dict(),
        }
        if self.errors:
            payload["errors"] = dict(self.errors)
        return payload


@dataclass(frozen=True)
class WeatherState:
    condition: str

    def to_dict(self) -> JsonDict:
        return {"condition": self.condition}


@dataclass(frozen=True)
class TimeOfDayState:
    slot: str

    def to_dict(self) -> JsonDict:
        return {"slot": self.slot}


@dataclass(frozen=True)
class RiverState:
    speed: str
    depth: str
    surface: str
    color: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RiverState":
        return cls(
            speed=_required_str(payload, "speed"),
            depth=_required_str(payload, "depth"),
            surface=_required_str(payload, "surface"),
            color=_required_str(payload, "color"),
        )

    def to_dict(self) -> JsonDict:
        return {
            "speed": self.speed,
            "depth": self.depth,
            "surface": self.surface,
            "color": self.color,
        }


@dataclass(frozen=True)
class CityState:
    lighting: str
    mood: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CityState":
        return cls(lighting=_required_str(payload, "lighting"), mood=_required_str(payload, "mood"))

    def to_dict(self) -> JsonDict:
        return {"lighting": self.lighting, "mood": self.mood}


@dataclass(frozen=True)
class VisualState:
    market_mood: str
    volatility_mood: str
    weather: WeatherState
    time_of_day: TimeOfDayState
    river: RiverState
    city: CityState

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "VisualState":
        return cls(
            market_mood=_required_str(payload, "market_mood"),
            volatility_mood=_required_str(payload, "volatility_mood"),
            weather=WeatherState(condition=_required_str(_mapping(payload.get("weather"), "visual_state.weather"), "condition")),
            time_of_day=TimeOfDayState(
                slot=_required_str(_mapping(payload.get("time_of_day"), "visual_state.time_of_day"), "slot")
            ),
            river=RiverState.from_mapping(_mapping(payload.get("river"), "visual_state.river")),
            city=CityState.from_mapping(_mapping(payload.get("city"), "visual_state.city")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "market_mood": self.market_mood,
            "volatility_mood": self.volatility_mood,
            "weather": self.weather.to_dict(),
            "time_of_day": self.time_of_day.to_dict(),
            "river": self.river.to_dict(),
            "city": self.city.to_dict(),
        }


@dataclass(frozen=True)
class PromptMetadata:
    id: str
    template_version: str
    source: str
    template_sha256: str | None
    template_s3_key: str | None
    active_s3_key: str | None
    positive: str
    negative: str
    provider: str
    hash: str

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "template_version": self.template_version,
            "source": self.source,
            "template_sha256": self.template_sha256,
            "template_s3_key": self.template_s3_key,
            "active_s3_key": self.active_s3_key,
            "positive": self.positive,
            "negative": self.negative,
            "provider": self.provider,
            "hash": self.hash,
        }


@dataclass(frozen=True)
class ModelMetadata:
    provider: str
    parameters: JsonDict

    def to_dict(self) -> JsonDict:
        return {"provider": self.provider, "parameters": dict(self.parameters)}


@dataclass(frozen=True)
class RunMetadata:
    id: str
    run_id: str
    slot: str
    weather: str
    created_at: str
    market_snapshot: MarketSnapshot
    derived_state: VisualState
    caption: str
    prompt: PromptMetadata
    model: ModelMetadata
    outputs: JsonDict = field(default_factory=dict)

    def with_outputs(self, **outputs: Any) -> "RunMetadata":
        return replace(self, outputs={**self.outputs, **outputs})

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "slot": self.slot,
            "weather": self.weather,
            "created_at": self.created_at,
            "market_snapshot": self.market_snapshot.to_dict(),
            "derived_state": self.derived_state.to_dict(),
            "caption": self.caption,
            "prompt": self.prompt.to_dict(),
            "model": self.model.to_dict(),
            "outputs": dict(self.outputs),
        }


@dataclass(frozen=True)
class FailureMetadata:
    id: str
    run_id: str
    slot: str
    created_at: str
    error_type: str
    error_message: str
    outputs: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "slot": self.slot,
            "created_at": self.created_at,
            "status": "failed",
            "error": {"type": self.error_type, "message": self.error_message},
            "outputs": dict(self.outputs),
        }


@dataclass(frozen=True)
class PipelineRunArtifact:
    id: str
    run_id: str
    slot: str
    weather_conditions: tuple[str, ...]
    created_at: str
    status: str
    market_snapshot: MarketSnapshot
    prompt_id: str
    prompt_version: str
    prompt_source: str
    prompt_template_sha256: str | None
    prompt_template_s3_key: str | None
    prompt_active_s3_key: str | None
    model: ModelMetadata
    error_type: str | None = None
    error_message: str | None = None

    def with_status(
        self,
        status: str,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> "PipelineRunArtifact":
        return replace(self, status=status, error_type=error_type, error_message=error_message)

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {
            "id": self.id,
            "run_id": self.run_id,
            "slot": self.slot,
            "weather_conditions": list(self.weather_conditions),
            "created_at": self.created_at,
            "status": self.status,
            "market_snapshot": self.market_snapshot.to_dict(),
            "prompt": {
                "id": self.prompt_id,
                "template_version": self.prompt_version,
                "source": self.prompt_source,
                "template_sha256": self.prompt_template_sha256,
                "template_s3_key": self.prompt_template_s3_key,
                "active_s3_key": self.prompt_active_s3_key,
            },
            "model": self.model.to_dict(),
        }
        if self.error_type or self.error_message:
            payload["error"] = {"type": self.error_type, "message": self.error_message}
        return payload


@dataclass(frozen=True)
class ManifestPrompt:
    id: str
    template_version: str
    source: str
    template_sha256: str | None
    template_s3_key: str | None
    active_s3_key: str | None
    hash: str
    provider: str

    @classmethod
    def from_prompt_metadata(cls, prompt: PromptMetadata) -> "ManifestPrompt":
        return cls(
            id=prompt.id,
            template_version=prompt.template_version,
            source=prompt.source,
            template_sha256=prompt.template_sha256,
            template_s3_key=prompt.template_s3_key,
            active_s3_key=prompt.active_s3_key,
            hash=prompt.hash,
            provider=prompt.provider,
        )

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "template_version": self.template_version,
            "source": self.source,
            "template_sha256": self.template_sha256,
            "template_s3_key": self.template_s3_key,
            "active_s3_key": self.active_s3_key,
            "hash": self.hash,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class ManifestItem:
    id: str
    run_id: str
    slot: str
    weather: str
    date: str
    created_at: str
    image_url: str | None
    metadata_url: str
    market_mood: str
    volatility_mood: str
    caption: str | None
    prompt: ManifestPrompt
    model: ModelMetadata

    @classmethod
    def from_run_metadata(cls, metadata: RunMetadata, *, image_url: str | None, metadata_url: str) -> "ManifestItem":
        return cls(
            id=metadata.id,
            run_id=metadata.run_id,
            slot=metadata.slot,
            weather=metadata.weather,
            date=metadata.created_at[:10],
            created_at=metadata.created_at,
            image_url=image_url,
            metadata_url=metadata_url,
            market_mood=metadata.derived_state.market_mood,
            volatility_mood=metadata.derived_state.volatility_mood,
            caption=metadata.caption,
            prompt=ManifestPrompt.from_prompt_metadata(metadata.prompt),
            model=metadata.model,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ManifestItem":
        prompt = _mapping(payload.get("prompt"), "manifest.prompt")
        model = _mapping(payload.get("model"), "manifest.model")
        return cls(
            id=_required_str(payload, "id"),
            run_id=_required_str(payload, "run_id"),
            slot=_required_str(payload, "slot"),
            weather=_required_str(payload, "weather"),
            date=_required_str(payload, "date"),
            created_at=_required_str(payload, "created_at"),
            image_url=_optional_str(payload.get("image_url")),
            metadata_url=_required_str(payload, "metadata_url", default=""),
            market_mood=_required_str(payload, "market_mood", default=""),
            volatility_mood=_required_str(payload, "volatility_mood", default=""),
            caption=_optional_str(payload.get("caption")),
            prompt=ManifestPrompt(
                id=_required_str(prompt, "id", default=""),
                template_version=_required_str(prompt, "template_version", default=""),
                source=_required_str(prompt, "source", default=""),
                template_sha256=_optional_str(prompt.get("template_sha256")),
                template_s3_key=_optional_str(prompt.get("template_s3_key")),
                active_s3_key=_optional_str(prompt.get("active_s3_key")),
                hash=_required_str(prompt, "hash", default=""),
                provider=_required_str(prompt, "provider", default=""),
            ),
            model=ModelMetadata(
                provider=_required_str(model, "provider", default=""),
                parameters=dict(_mapping(model.get("parameters"), "manifest.model.parameters", allow_none=True)),
            ),
        )

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "slot": self.slot,
            "weather": self.weather,
            "date": self.date,
            "created_at": self.created_at,
            "image_url": self.image_url,
            "metadata_url": self.metadata_url,
            "market_mood": self.market_mood,
            "volatility_mood": self.volatility_mood,
            "caption": self.caption,
            "prompt": self.prompt.to_dict(),
            "model": self.model.to_dict(),
        }


def _mapping(value: Any, name: str, *, allow_none: bool = False) -> Mapping[str, Any]:
    if value is None and allow_none:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _required_str(payload: Mapping[str, Any], name: str, *, default: str | None = None) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ValueError("value must be numeric")
    return float(value)
