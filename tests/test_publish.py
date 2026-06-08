from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError

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
    ManifestItem,
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

    def test_s3_latest_manifest_uses_if_match_when_existing_manifest_has_etag(self) -> None:
        fake_s3 = FakeS3(existing_payload={"items": []}, etag='"abc123"')
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.publish.boto3.client", return_value=fake_s3):
                publisher = Publisher(make_settings(Path(tmp), s3_bucket="bucket"))

                publisher.publish_latest_manifest([_manifest_item("run-1")], updated_at="2026-01-02T10:00:00Z")

        self.assertEqual(fake_s3.put_calls[0]["IfMatch"], '"abc123"')
        self.assertNotIn("IfNoneMatch", fake_s3.put_calls[0])

    def test_s3_latest_manifest_uses_if_none_match_when_manifest_is_absent(self) -> None:
        fake_s3 = FakeS3(existing_payload=None)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.publish.boto3.client", return_value=fake_s3):
                publisher = Publisher(make_settings(Path(tmp), s3_bucket="bucket"))

                publisher.publish_latest_manifest([_manifest_item("run-1")], updated_at="2026-01-02T10:00:00Z")

        self.assertEqual(fake_s3.put_calls[0]["IfNoneMatch"], "*")
        self.assertNotIn("IfMatch", fake_s3.put_calls[0])


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


def _manifest_item(run_id: str) -> ManifestItem:
    return ManifestItem.from_run_metadata(
        _metadata(run_id, "sunny"),
        image_url=f"https://example.test/{run_id}.svg",
        metadata_url=f"https://example.test/{run_id}.json",
    )


class FakeBody:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


class FakeS3:
    def __init__(self, existing_payload: dict[str, object] | None, etag: str | None = None):
        self.existing_payload = existing_payload
        self.etag = etag
        self.put_calls: list[dict[str, object]] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, object]:
        if self.existing_payload is None:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {
            "Body": FakeBody(json.dumps(self.existing_payload).encode("utf-8")),
            "ETag": self.etag,
        }

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)


if __name__ == "__main__":
    unittest.main()
