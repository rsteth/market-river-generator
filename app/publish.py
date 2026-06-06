from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import Settings
from app.manifest import update_latest_manifest


LATEST_KEY = "manifests/latest.json"


@dataclass(frozen=True)
class PublishedObject:
    key: str
    url: str


@dataclass(frozen=True)
class PublishResult:
    image: PublishedObject | None
    metadata: PublishedObject
    latest: PublishedObject


class Publisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._s3 = boto3.client("s3", region_name=settings.aws_region) if settings.s3_bucket else None

    def publish_success(
        self,
        *,
        metadata: dict[str, Any],
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> PublishResult:
        slot = metadata["slot"]
        created_at = metadata["created_at"]
        date_path = _date_path(created_at)
        run_id = metadata["run_id"]

        image_obj = None
        if image_path is not None and image_format is not None:
            image_key = f"images/{date_path}/{slot}-{run_id}.{image_format}"
            image_obj = self.upload_file(image_path, image_key, image_content_type or "application/octet-stream")
            metadata["outputs"]["image_s3_key"] = image_key
            metadata["outputs"]["image_url"] = image_obj.url

        metadata_key = f"metadata/{date_path}/{slot}-{run_id}.json"
        metadata["outputs"]["metadata_s3_key"] = metadata_key
        metadata["outputs"]["metadata_url"] = self.url_for_key(metadata_key)
        metadata_obj = self.upload_json(metadata, metadata_key)

        manifest_item = {
            "id": metadata["id"],
            "run_id": run_id,
            "slot": slot,
            "date": created_at[:10],
            "created_at": created_at,
            "image_url": image_obj.url if image_obj else None,
            "metadata_url": metadata_obj.url,
            "market_mood": metadata["derived_state"]["market_mood"],
            "volatility_mood": metadata["derived_state"]["volatility_mood"],
            "caption": metadata.get("caption"),
            "prompt": {
                "id": metadata["prompt"]["id"],
                "template_version": metadata["prompt"]["template_version"],
                "source": metadata["prompt"]["source"],
                "template_sha256": metadata["prompt"]["template_sha256"],
                "template_s3_key": metadata["prompt"]["template_s3_key"],
                "active_s3_key": metadata["prompt"]["active_s3_key"],
                "hash": metadata["prompt"]["hash"],
                "provider": metadata["prompt"]["provider"],
            },
            "model": metadata["model"],
        }
        existing = self.read_json(LATEST_KEY)
        latest = update_latest_manifest(existing, manifest_item, updated_at=metadata["created_at"])
        latest_obj = self.upload_json(latest, LATEST_KEY)
        return PublishResult(image=image_obj, metadata=metadata_obj, latest=latest_obj)

    def publish_failure(self, metadata: dict[str, Any]) -> PublishedObject:
        created_at = metadata["created_at"]
        date_path = _date_path(created_at)
        key = f"failures/{date_path}/{metadata['slot']}-{metadata['run_id']}.json"
        return self.upload_json(metadata, key)

    def upload_file(self, source: Path, key: str, content_type: str) -> PublishedObject:
        if self._s3:
            self._s3.upload_file(
                str(source),
                self.settings.s3_bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        else:
            destination = self.settings.output_dir / "published" / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        return PublishedObject(key=key, url=self.url_for_key(key))

    def upload_json(self, payload: dict[str, Any], key: str) -> PublishedObject:
        body = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
        if self._s3:
            self._s3.put_object(
                Bucket=self.settings.s3_bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        else:
            destination = self.settings.output_dir / "published" / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        return PublishedObject(key=key, url=self.url_for_key(key))

    def read_json(self, key: str) -> dict[str, Any] | None:
        if self._s3:
            try:
                response = self._s3.get_object(Bucket=self.settings.s3_bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                    return None
                raise
            return json.loads(response["Body"].read())

        source = self.settings.output_dir / "published" / key
        if not source.exists():
            return None
        return json.loads(source.read_text(encoding="utf-8"))

    def url_for_key(self, key: str) -> str:
        if self.settings.public_base_url:
            return f"{self.settings.public_base_url}/{key}"
        if self.settings.s3_bucket:
            return f"https://{self.settings.s3_bucket}.s3.{self.settings.aws_region}.amazonaws.com/{key}"
        return str((self.settings.output_dir / "published" / key).resolve())


def _date_path(created_at: str) -> str:
    parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return parsed.strftime("%Y/%m/%d")
