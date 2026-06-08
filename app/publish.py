from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import Settings
from app.contracts import FailureMetadata, ManifestItem, RunMetadata
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
        metadata: RunMetadata,
        image_path: Path | None,
        image_content_type: str | None,
        image_format: str | None,
    ) -> PublishResult:
        slot = metadata.slot
        created_at = metadata.created_at
        date_path = _date_path(created_at)
        run_id = metadata.run_id

        image_obj = None
        if image_path is not None and image_format is not None:
            image_key = f"images/{date_path}/{slot}-{run_id}.{image_format}"
            image_obj = self.upload_file(image_path, image_key, image_content_type or "application/octet-stream")
            metadata = metadata.with_outputs(image_s3_key=image_key, image_url=image_obj.url)

        metadata_key = f"metadata/{date_path}/{slot}-{run_id}.json"
        metadata = metadata.with_outputs(metadata_s3_key=metadata_key, metadata_url=self.url_for_key(metadata_key))
        metadata_obj = self.upload_json(metadata.to_dict(), metadata_key)

        manifest_item = ManifestItem.from_run_metadata(metadata, image_url=image_obj.url if image_obj else None, metadata_url=metadata_obj.url)
        existing = self.read_json(LATEST_KEY)
        latest = update_latest_manifest(existing, manifest_item, updated_at=metadata.created_at)
        latest_obj = self.upload_json(latest, LATEST_KEY)
        return PublishResult(image=image_obj, metadata=metadata_obj, latest=latest_obj)

    def publish_failure(self, metadata: FailureMetadata | dict[str, Any]) -> PublishedObject:
        payload = metadata.to_dict() if isinstance(metadata, FailureMetadata) else metadata
        created_at = payload["created_at"]
        date_path = _date_path(created_at)
        key = f"failures/{date_path}/{payload['slot']}-{payload['run_id']}.json"
        return self.upload_json(payload, key)

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
