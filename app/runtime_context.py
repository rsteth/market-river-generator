from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


def load_runtime_log_context() -> dict[str, Any]:
    context: dict[str, Any] = {
        "app_name": os.getenv("APP_NAME"),
        "aws_region": os.getenv("AWS_REGION"),
        "aws_execution_env": os.getenv("AWS_EXECUTION_ENV"),
        "schedule_name": os.getenv("SCHEDULE_NAME"),
        "schedule_slot": os.getenv("SCHEDULE_SLOT"),
    }
    context.update(_task_input_context())
    context.update(_ecs_metadata_context())
    return {key: value for key, value in context.items() if value}


def _task_input_context() -> dict[str, Any]:
    raw = os.getenv("TASK_INPUT_JSON")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "scheduler_slot": payload.get("slot"),
        "scheduler_name": payload.get("schedule_name"),
        "scheduler_group": payload.get("schedule_group"),
    }


def _ecs_metadata_context() -> dict[str, Any]:
    base_url = os.getenv("ECS_CONTAINER_METADATA_URI_V4")
    if not base_url:
        return {}
    try:
        with urlopen(f"{base_url}/task", timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError, TimeoutError):
        return {"ecs_metadata_uri": base_url}
    if not isinstance(payload, dict):
        return {"ecs_metadata_uri": base_url}
    return {
        "ecs_metadata_uri": base_url,
        "ecs_task_arn": payload.get("TaskARN"),
        "ecs_cluster": payload.get("Cluster"),
        "ecs_task_family": payload.get("Family"),
        "ecs_task_revision": payload.get("Revision"),
        "ecs_availability_zone": payload.get("AvailabilityZone"),
    }
