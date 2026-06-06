from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.prompts import sha256_text


DEFAULT_PROMPT_ID = "river_city"
DEFAULT_ACTIVE_KEY = "prompts/river_city/active.json"


def main() -> int:
    args = _parse_args()
    if args.command == "validate":
        text = _read_prompt_file(args.file)
        _validate_template(text)
        print(json.dumps({"file": str(args.file), "sha256": sha256_text(text)}, indent=2))
        return 0

    client = boto3.client("s3", region_name=args.region)
    if args.command == "publish":
        text = _read_prompt_file(args.file)
        _validate_template(text)
        key = _template_key(args.prompt_id, args.version)
        client.put_object(
            Bucket=args.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        print(json.dumps({"bucket": args.bucket, "key": key, "version": args.version, "sha256": sha256_text(text)}, indent=2))
        return 0

    if args.command == "promote":
        key = _template_key(args.prompt_id, args.version)
        response = client.get_object(Bucket=args.bucket, Key=key)
        text = response["Body"].read().decode("utf-8")
        _validate_template(text)
        payload = {
            "prompt_id": args.prompt_id,
            "version": args.version,
            "template_key": key,
            "sha256": sha256_text(text),
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        if args.notes:
            payload["notes"] = args.notes
        client.put_object(
            Bucket=args.bucket,
            Key=args.active_key,
            Body=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
        )
        print(json.dumps({"bucket": args.bucket, "active_key": args.active_key, "active": payload}, indent=2))
        return 0

    if args.command == "active":
        response = client.get_object(Bucket=args.bucket, Key=args.active_key)
        payload = json.loads(response["Body"].read())
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    raise ValueError(f"unknown command: {args.command}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage S3 prompt registry entries.")
    parser.add_argument("--region", default="us-east-1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--file", type=Path, required=True)

    publish = subparsers.add_parser("publish")
    _add_s3_args(publish)
    publish.add_argument("--file", type=Path, required=True)
    publish.add_argument("--version", required=True)

    promote = subparsers.add_parser("promote")
    _add_s3_args(promote)
    promote.add_argument("--version", required=True)
    promote.add_argument("--notes", default="")

    active = subparsers.add_parser("active")
    _add_s3_args(active)

    return parser.parse_args()


def _add_s3_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prompt-id", default=DEFAULT_PROMPT_ID)
    parser.add_argument("--active-key", default=DEFAULT_ACTIVE_KEY)


def _read_prompt_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _template_key(prompt_id: str, version: str) -> str:
    return f"prompts/{prompt_id}/versions/{version}.txt"


def _validate_template(text: str) -> None:
    required = {"weather", "time_of_day", "market_condition"}
    missing = [name for name in sorted(required) if "{" + name + "}" not in text]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"prompt template is missing placeholders: {joined}")


if __name__ == "__main__":
    raise SystemExit(main())
