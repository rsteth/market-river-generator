from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.contracts import (
    FailureMetadata,
    InstrumentSnapshot,
    ManifestItem,
    MarketSnapshot,
    MarketSummary,
    PipelineRunArtifact,
    RunMetadata,
    RunRequest,
)
from app.image_model import GeneratedImage
from app.pipeline import PipelineDependencies, run_pipeline
from app.prompts import PromptResult, PromptTemplate, sha256_text
from app.publish import PublishResult, PublishedObject, StagedPublishResult
from tests.helpers import make_settings


class PipelineTests(unittest.TestCase):
    def test_run_pipeline_uses_injected_dependencies_for_each_weather_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_provider = FakeImageProvider(root)
            publisher = FakePublisher()
            deps = PipelineDependencies(
                settings=make_settings(root),
                market_data=FakeMarketData(),
                prompt_templates=FakePromptTemplates(),
                image_provider=image_provider,
                publisher=publisher,
                now=lambda: "2026-01-02T10:00:00Z",
                new_run_id=lambda: "base123",
            )
            image_provider.events = publisher.events

            result = run_pipeline(RunRequest(slot="open", weather_conditions=("sunny", "rainy")), deps)

            self.assertTrue(result.succeeded)
            self.assertEqual([variant.run_id for variant in result.variants], ["base123-sunny", "base123-rainy"])
            self.assertEqual([call["run_id"] for call in image_provider.calls], ["base123-sunny", "base123-rainy"])
            self.assertEqual([metadata.weather for metadata in publisher.successes], ["sunny", "rainy"])
            self.assertEqual([artifact.status for artifact in publisher.pipeline_runs], ["started", "succeeded"])
            self.assertLess(publisher.events.index("pipeline:started"), publisher.events.index("image:base123-sunny"))
            self.assertGreater(publisher.events.index("manifest"), publisher.events.index("stage:base123-rainy"))

    def test_run_pipeline_publishes_failure_metadata_when_stage_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publisher = FakePublisher()
            deps = PipelineDependencies(
                settings=make_settings(root),
                market_data=FailingMarketData(),
                prompt_templates=FakePromptTemplates(),
                image_provider=FakeImageProvider(root),
                publisher=publisher,
                now=lambda: "2026-01-02T10:00:00Z",
                new_run_id=lambda: "base123",
            )

            with self.assertLogs("app.pipeline", level="ERROR"):
                result = run_pipeline(RunRequest(slot="midday", weather_conditions=("cloudy",)), deps)

            self.assertFalse(result.succeeded)
            self.assertEqual(result.error_type, "RuntimeError")
            self.assertEqual(publisher.pipeline_runs, [])
            self.assertEqual(publisher.failures[0].slot, "midday")
            self.assertEqual(publisher.failures[0].run_id, "base123")


class FakeMarketData:
    def fetch_snapshot(self) -> MarketSnapshot:
        return MarketSnapshot(
            as_of="2026-01-02T10:00:00Z",
            source="test",
            instruments={
                "SPY": InstrumentSnapshot(last=100, previous_close=99, change_pct=1.0101),
                "QQQ": InstrumentSnapshot(last=100, previous_close=99, change_pct=1.0101),
                "^VIX": InstrumentSnapshot(last=20, previous_close=20, change_pct=0),
            },
            summary=MarketSummary(
                spy_change_pct=1.0101,
                qqq_change_pct=1.0101,
                vix_change_pct=0,
                avg_risk_change_pct=1.0101,
            ),
        )


class FailingMarketData:
    def fetch_snapshot(self) -> MarketSnapshot:
        raise RuntimeError("market unavailable")


class FakePromptTemplates:
    def load_template(self) -> PromptTemplate:
        text = "Weather: {weather}\nTime: {time_of_day}\nMarket: {market_condition}"
        return PromptTemplate(
            prompt_id="river_city",
            version="test",
            text=text,
            source="test",
            sha256=sha256_text(text),
        )


class FakeImageProvider:
    name = "fake"

    def __init__(self, root: Path):
        self.root = root
        self.calls: list[dict[str, str]] = []
        self.events: list[str] | None = None

    def generate_image(
        self,
        prompt_result: PromptResult,
        run_id: str,
        output_dir: Path,
        slot: str,
        market_mood: str,
        volatility_mood: str,
    ) -> GeneratedImage:
        self.calls.append({"run_id": run_id, "slot": slot, "market_mood": market_mood})
        if self.events is not None:
            self.events.append(f"image:{run_id}")
        path = self.root / f"{run_id}.svg"
        path.write_text("<svg></svg>", encoding="utf-8")
        return GeneratedImage(provider=self.name, path=path, content_type="image/svg+xml", format="svg")


class FakePublisher:
    def __init__(self) -> None:
        self.successes: list[RunMetadata] = []
        self.failures: list[FailureMetadata] = []
        self.pipeline_runs: list[PipelineRunArtifact] = []
        self.events: list[str] = []

    def publish_success(
        self,
        *,
        metadata: RunMetadata,
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> PublishResult:
        staged = self.stage_success(
            metadata=metadata,
            image_path=image_path,
            image_content_type=image_content_type,
            image_format=image_format,
        )
        latest = self.publish_latest_manifest([staged.manifest_item], updated_at=metadata.created_at)
        return PublishResult(image=staged.image, metadata=staged.metadata, latest=latest)

    def stage_success(
        self,
        *,
        metadata: RunMetadata,
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> StagedPublishResult:
        self.successes.append(metadata)
        run_id = metadata.run_id
        self.events.append(f"stage:{run_id}")
        return StagedPublishResult(
            image=PublishedObject(key=f"images/{run_id}.svg", url=f"https://example.test/images/{run_id}.svg"),
            metadata=PublishedObject(key=f"metadata/{run_id}.json", url=f"https://example.test/metadata/{run_id}.json"),
            manifest_item=metadata_to_manifest_item(metadata),
        )

    def publish_latest_manifest(self, items: list[ManifestItem], *, updated_at: str) -> PublishedObject:
        self.events.append("manifest")
        return PublishedObject(key="manifests/latest.json", url="https://example.test/manifests/latest.json")

    def publish_failure(self, metadata: FailureMetadata) -> PublishedObject:
        self.failures.append(metadata)
        return PublishedObject(key=f"failures/{metadata.run_id}.json", url=f"https://example.test/failures/{metadata.run_id}.json")

    def publish_pipeline_run(self, artifact: PipelineRunArtifact) -> PublishedObject:
        self.pipeline_runs.append(artifact)
        self.events.append(f"pipeline:{artifact.status}")
        return PublishedObject(
            key=f"pipeline-runs/{artifact.run_id}.json",
            url=f"https://example.test/pipeline-runs/{artifact.run_id}.json",
        )


def metadata_to_manifest_item(metadata: RunMetadata) -> ManifestItem:
    return ManifestItem.from_run_metadata(
        metadata,
        image_url=f"https://example.test/images/{metadata.run_id}.svg",
        metadata_url=f"https://example.test/metadata/{metadata.run_id}.json",
    )


if __name__ == "__main__":
    unittest.main()
