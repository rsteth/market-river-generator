from __future__ import annotations

import json
from typing import Any

import boto3

from app.config import Settings
from app.prompts import PromptTemplate, bundled_prompt_template, sha256_text


class PromptRegistryError(RuntimeError):
    pass


def load_active_prompt_template(settings: Settings) -> PromptTemplate:
    if not settings.s3_bucket:
        return bundled_prompt_template()

    try:
        return _load_s3_prompt_template(settings)
    except Exception:
        if settings.allow_bundled_prompt_fallback:
            return bundled_prompt_template()
        raise


def _load_s3_prompt_template(settings: Settings) -> PromptTemplate:
    client = boto3.client("s3", region_name=settings.aws_region)
    active = _read_json(client, settings.s3_bucket, settings.prompt_active_key)

    prompt_id = _required_str(active, "prompt_id")
    version = _required_str(active, "version")
    template_key = _required_str(active, "template_key")
    expected_sha256 = _required_str(active, "sha256")

    response = client.get_object(Bucket=settings.s3_bucket, Key=template_key)
    text = response["Body"].read().decode("utf-8")
    actual_sha256 = sha256_text(text)
    if actual_sha256 != expected_sha256:
        raise PromptRegistryError(
            f"prompt template hash mismatch for {template_key}: expected {expected_sha256}, got {actual_sha256}"
        )

    return PromptTemplate(
        prompt_id=prompt_id,
        version=version,
        text=text,
        source="s3",
        sha256=actual_sha256,
        template_s3_key=template_key,
        active_s3_key=settings.prompt_active_key,
    )


def _read_json(client: Any, bucket: str, key: str) -> dict[str, Any]:
    response = client.get_object(Bucket=bucket, Key=key)
    payload = json.loads(response["Body"].read())
    if not isinstance(payload, dict):
        raise PromptRegistryError(f"{key} must contain a JSON object")
    return payload


def _required_str(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise PromptRegistryError(f"active prompt pointer is missing {name}")
    return value.strip()
