"""Rebuild the nine-snapshot archive from retained metadata; dry-run by default."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contracts import ManifestItem
from app.manifest import update_recent_manifest_items
from app.publish import RECENT_KEY


def metadata_item(payload: dict, key: str, base_url: str) -> dict:
    outputs = payload["outputs"]
    image_key = outputs["image_s3_key"]
    return ManifestItem.from_mapping({
        **payload,
        "date": payload["created_at"][:10],
        "image_url": f"{base_url}/{image_key}",
        "metadata_url": f"{base_url}/{key}",
        "market_mood": payload["derived_state"]["market_mood"],
        "volatility_mood": payload["derived_state"]["volatility_mood"],
    }).to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--profile", help="AWS profile; omit to use environment credentials")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--public-base-url")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    s3 = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3")
    base_url = (args.public_base_url or f"https://{args.bucket}.s3.{args.region}.amazonaws.com").rstrip("/")
    try:
        existing = s3.get_object(Bucket=args.bucket, Key=RECENT_KEY)
        condition = {"IfMatch": existing["ETag"]}
        previous = json.loads(existing["Body"].read())
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchKey":
            raise
        condition = {"IfNoneMatch": "*"}
        previous = None
    keys = [
        obj["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=args.bucket, Prefix="metadata/")
        for obj in page.get("Contents", []) if obj["Key"].endswith(".json")
    ]

    def read(key: str) -> tuple[dict, str]:
        response = s3.get_object(Bucket=args.bucket, Key=key)
        payload = json.loads(response["Body"].read())
        return metadata_item(payload, key, base_url), payload["outputs"]["image_s3_key"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(read, keys))
    # Repeated runs of a slot replace the older weather record deterministically.
    unique = {}
    for item, image_key in sorted(records, key=lambda record: (record[0]["created_at"], record[0]["run_id"])):
        unique[(item["date"], item["slot"], item["weather"])] = item
    manifest = update_recent_manifest_items(previous, list(unique.values()), updated_at=datetime.now(timezone.utc).isoformat())
    selected_ids = {item["run_id"] for item in manifest["items"]}
    for item, image_key in records:
        if item["run_id"] in selected_ids:
            s3.head_object(Bucket=args.bucket, Key=image_key)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    if args.apply:
        s3.put_object(Bucket=args.bucket, Key=RECENT_KEY, Body=args.output.read_bytes(), ContentType="application/json", **condition)
    print(json.dumps({"metadata_records": len(records), "items": len(manifest["items"]), "snapshots": sorted({(i["date"], i["slot"]) for i in manifest["items"]}), "output": str(args.output), "applied": args.apply}, indent=2))


if __name__ == "__main__":
    main()
