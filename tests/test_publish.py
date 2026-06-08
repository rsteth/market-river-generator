from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.contracts import (
    CityState,
    MarketSnapshot,
    MarketSummary,
    ModelMetadata,
    PromptMetadata,
    RiverState,
    RunMetadata,
    TimeOfDayState,
    VisualState,
    WeatherState,
)
from app.publish import LATEST_KEY, Publisher
from tests.helpers import make_settings


class PublishTests(unittest.TestCase):
    def test_local_publish_writes_image_metadata_and_latest_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.svg"
            image.write_text("<svg></svg>", encoding="utf-8")
            publisher = Publisher(make_settings(root))

            result = publisher.publish_success(
                metadata=_metadata("run-1", "sunny"),
                image_path=image,
                image_content_type="image/svg+xml",
                image_format="svg",
            )

            self.assertTrue((root / "published" / result.image.key).exists())
            self.assertTrue((root / "published" / result.metadata.key).exists())
            latest = json.loads((root / "published" / LATEST_KEY).read_text(encoding="utf-8"))
            self.assertEqual(latest["items"][0]["run_id"], "run-1")
            self.assertEqual(latest["items"][0]["market_mood"], "flat")


def _metadata(run_id: str, weather: str) -> RunMetadata:
    return RunMetadata(
        id=f"2026-01-02-open-{run_id}",
        run_id=run_id,
        slot="open",
        weather=weather,
        created_at="2026-01-02T10:00:00Z",
        market_snapshot=MarketSnapshot(
            as_of="2026-01-02T10:00:00Z",
            source="test",
            instruments={},
            summary=MarketSummary(
                spy_change_pct=None,
                qqq_change_pct=None,
                vix_change_pct=None,
                avg_risk_change_pct=None,
            ),
        ),
        derived_state=VisualState(
            market_mood="flat",
            volatility_mood="stable",
            weather=WeatherState(condition=weather),
            time_of_day=TimeOfDayState(slot="open"),
            river=RiverState(speed="slow", depth="steady", surface="quiet", color="blue"),
            city=CityState(lighting="muted", mood="still"),
        ),
        caption="a sunny morning",
        prompt=PromptMetadata(
            id="river_city",
            template_version="test",
            source="test",
            template_sha256="abc",
            template_s3_key=None,
            active_s3_key=None,
            positive="positive",
            negative="negative",
            provider="provider",
            hash="hash",
        ),
        model=ModelMetadata(provider="mock", parameters={}),
    )


if __name__ == "__main__":
    unittest.main()
