"""Read-only daily verification of scheduled publication outcomes."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from app.logging_utils import configure_logging, get_logger
from app.session import NEW_YORK, assess_slot, parse_timestamp

PACIFIC = ZoneInfo("America/Los_Angeles")
PUBLICATION_GRACE = timedelta(hours=2)
SCHEDULE_PATTERN = re.compile(r"cron\((\d{1,2}) (\d{1,2}) \? \* MON-FRI \*\)")
logger = get_logger(__name__)


@dataclass(frozen=True)
class Outcome:
    status: str
    alarm: int
    expected_skip: str | None = None


def scheduled_slots(day: datetime, schedules: Mapping[str, str]) -> dict[str, datetime]:
    """Derive occurrence timestamps from the same Terraform cron expressions."""
    local = day.astimezone(PACIFIC)
    if set(schedules) != {"open", "midday", "close"}:
        raise ValueError("watchdog requires open, midday and close schedules")
    slots = {}
    for slot, expression in schedules.items():
        match = SCHEDULE_PATTERN.fullmatch(expression)
        if not match:
            raise ValueError(f"unsupported publication schedule: {expression}")
        minute, hour = map(int, match.groups())
        slots[slot] = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return slots


def matching_records(
    records: Iterable[Mapping[str, Any]], *, app_name: str, slot: str, scheduled_at: datetime,
) -> list[Mapping[str, Any]]:
    """Never let manual runs, neighboring dates, or other slots satisfy an occurrence."""
    matched = []
    for record in records:
        if record.get("schedule_name") != f"{app_name}-{slot}" or record.get("schedule_slot") != slot:
            continue
        try:
            actual = parse_timestamp(record["scheduled_at"])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if actual == scheduled_at:
            matched.append(record)
    return matched


def classify(slot: str, scheduled_at: datetime, records: Iterable[Mapping[str, Any]]) -> Outcome:
    """Use the intended time, never the time of a delayed worker or verifier."""
    if scheduled_at.astimezone(PACIFIC).weekday() >= 5:
        return Outcome("weekend_no_schedule", 0)
    expected = assess_slot(slot, scheduled_at, scheduled_at).skip_reason
    evidence = list(records)
    if not evidence:
        # Scheduler still launches the worker on closed weekdays. No log means
        # missed execution, not an observed calendar skip.
        return Outcome("missed_execution", 1, expected)
    published = any(r.get("message") == "published latest manifest" and r.get("slot") == slot for r in evidence)
    if expected:
        if published:
            return Outcome("unexpected_publication", 1, expected)
        skipped = any(
            r.get("message") == "market slot skipped by calendar"
            and r.get("slot") == slot and r.get("reason") == expected
            and r.get("session_date") == scheduled_at.astimezone(NEW_YORK).date().isoformat()
            for r in evidence
        )
        return Outcome("expected_calendar_skip", 0, expected) if skipped else Outcome("missing_calendar_skip", 1, expected)
    if published:
        return Outcome("published", 0)
    # An eligible occurrence must publish; duplicates, errors, stale data and
    # calendar skips caused by late execution do not count as success.
    return Outcome("failed_publication", 1)


def read_records(logs: Any, group: str, start: datetime, end: datetime) -> list[Mapping[str, Any]]:
    result = []
    pages = logs.get_paginator("filter_log_events").paginate(
        logGroupName=group,
        startTime=int(start.timestamp() * 1000),
        endTime=int(end.timestamp() * 1000),
        filterPattern='{ $.scheduled_at = * }',
    )
    for page in pages:
        for event in page.get("events", []):
            try:
                payload = json.loads(event["message"])
            except (KeyError, TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                result.append(payload)
    return result


def check_day(
    *, logs: Any, group: str, app_name: str, schedules: Mapping[str, str],
    check_at: datetime, now: datetime,
) -> dict[str, Outcome]:
    slots = scheduled_slots(check_at, schedules)
    if now < check_at or check_at < max(slots.values()) + PUBLICATION_GRACE:
        raise ValueError("watchdog invoked before publication grace elapsed")
    # A retry audits the date originally scheduled, not whichever day it starts.
    # Bound reads to the original daily cutoff, allowing later delivery of logs
    # whose event timestamps were within the original window.
    records = [] if check_at.astimezone(PACIFIC).weekday() >= 5 else read_records(logs, group, min(slots.values()), check_at)
    return {
        slot: classify(slot, timestamp, matching_records(records, app_name=app_name, slot=slot, scheduled_at=timestamp))
        for slot, timestamp in slots.items()
    }


def main() -> int:
    configure_logging("INFO")
    try:
        import boto3

        check_at = parse_timestamp(os.environ["WATCHDOG_SCHEDULED_AT"])
        now = datetime.now(ZoneInfo("UTC"))
        outcomes = check_day(
            logs=boto3.client("logs", region_name=os.environ["AWS_REGION"]), group=os.environ["WATCHDOG_LOG_GROUP"],
            app_name=os.environ["APP_NAME"], schedules=json.loads(os.environ["WATCHDOG_SCHEDULES"]),
            check_at=check_at, now=now,
        )
        for slot, outcome in outcomes.items():
            logger.info("publication watchdog result", extra={
                "_slot": slot, "_session_date": check_at.astimezone(PACIFIC).date().isoformat(),
                "_status": outcome.status, "_alarm": outcome.alarm, "_expected_skip": outcome.expected_skip,
            })
        # Do not let a delayed retry stand in for today's missing verifier.
        if check_at.astimezone(PACIFIC).date() == now.astimezone(PACIFIC).date():
            logger.info("publication watchdog completed")
        else:
            logger.warning("publication watchdog completed late")
        return 0
    except Exception:
        # Existing RunFailures remains a separate, immediate signal.
        logger.exception("publication watchdog failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
