from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.contracts import (
    FailureMetadata,
    InstrumentSnapshot,
    MarketSnapshot,
    MarketSummary,
    RunMetadata,
    RunRequest,
)
from app.image_model import GeneratedImage
from app.pipeline import PipelineDependencies, run_pipeline
from app.prompts import PromptResult, PromptTemplate, sha256_text
from app.publish import PublishResult, PublishedObject
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

            result = run_pipeline(RunRequest(slot="open", weather_conditions=("sunny", "rainy")), deps)

            self.assertTrue(result.succeeded)
            self.assertEqual([variant.run_id for variant in result.variants], ["base123-sunny", "base123-rainy"])
            self.assertEqual([call["run_id"] for call in image_provider.calls], ["base123-sunny", "base123-rainy"])
            self.assertEqual([metadata.weather for metadata in publisher.successes], ["sunny", "rainy"])

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
        path = self.root / f"{run_id}.svg"
        path.write_text("<svg></svg>", encoding="utf-8")
        return GeneratedImage(provider=self.name, path=path, content_type="image/svg+xml", format="svg")


class FakePublisher:
    def __init__(self) -> None:
        self.successes: list[RunMetadata] = []
        self.failures: list[FailureMetadata] = []

    def publish_success(
        self,
        *,
        metadata: RunMetadata,
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> PublishResult:
        self.successes.append(metadata)
        run_id = metadata.run_id
        return PublishResult(
            image=PublishedObject(key=f"images/{run_id}.svg", url=f"https://example.test/images/{run_id}.svg"),
            metadata=PublishedObject(key=f"metadata/{run_id}.json", url=f"https://example.test/metadata/{run_id}.json"),
            latest=PublishedObject(key="manifests/latest.json", url="https://example.test/manifests/latest.json"),
        )

    def publish_failure(self, metadata: FailureMetadata) -> PublishedObject:
        self.failures.append(metadata)
        return PublishedObject(key=f"failures/{metadata.run_id}.json", url=f"https://example.test/failures/{metadata.run_id}.json")


if __name__ == "__main__":
    unittest.main()
