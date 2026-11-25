from __future__ import annotations

import json
from datetime import timedelta
from unittest import TestCase
from unittest.mock import Mock, patch

from app.publication_watchdog import check_day, classify, matching_records, scheduled_slots
from app.runtime_context import load_runtime_log_context
from app.session import parse_timestamp

SCHEDULES = {
    "open": "cron(45 6 ? * MON-FRI *)",
    "midday": "cron(15 10 ? * MON-FRI *)",
    "close": "cron(20 13 ? * MON-FRI *)",
}
APP = "market-river-generator"


def occurrence(day, slot):
    return scheduled_slots(parse_timestamp(f"{day}T23:20:00Z"), SCHEDULES)[slot]


def record(day, slot, message, **fields):
    return {
        "schedule_name": f"{APP}-{slot}", "schedule_slot": slot,
        "scheduled_at": occurrence(day, slot).isoformat(), "slot": slot,
        "session_date": day, "message": message, **fields,
    }


def skip(day, slot, reason):
    return record(day, slot, "market slot skipped by calendar", reason=reason)


def success(day, slot):
    return record(day, slot, "published latest manifest")


class PublicationWatchdogTests(TestCase):
    def assess(self, day, slot, evidence):
        at = occurrence(day, slot)
        return classify(slot, at, matching_records(evidence, app_name=APP, slot=slot, scheduled_at=at))

    def test_thanksgiving_all_three_expected_skips(self):
        day = "2026-11-26"
        for slot in SCHEDULES:
            with self.subTest(slot=slot):
                outcome = self.assess(day, slot, [skip(day, slot, "market_closed")])
                self.assertEqual((outcome.status, outcome.alarm), ("expected_calendar_skip", 0))

    def test_black_friday_open_and_close_publish_midday_skips(self):
        day = "2026-11-27"
        for slot in ("open", "close"):
            self.assertEqual(self.assess(day, slot, [success(day, slot)]).status, "published")
            self.assertEqual(self.assess(day, slot, []).status, "missed_execution")
            self.assertEqual(self.assess(day, slot, [skip(day, slot, "outside_session")]).alarm, 1)
        outcome = self.assess(day, "midday", [skip(day, "midday", "outside_session")])
        self.assertEqual((outcome.status, outcome.alarm), ("expected_calendar_skip", 0))

    def test_weekends_do_not_require_execution_or_publication(self):
        for day in ("2026-11-28", "2026-11-29", "2026-12-05", "2026-12-06"):
            for slot in SCHEDULES:
                with self.subTest(day=day, slot=slot):
                    self.assertEqual(self.assess(day, slot, []).alarm, 0)
                    self.assertEqual(self.assess(day, slot, []).status, "weekend_no_schedule")

    def test_normal_day_all_slots_required(self):
        for day in ("2026-11-25", "2026-11-30"):
            for slot in SCHEDULES:
                self.assertEqual(self.assess(day, slot, [success(day, slot)]).alarm, 0)
                self.assertEqual(self.assess(day, slot, []).alarm, 1)

    def test_genuine_failures_and_abandoned_paid_claim(self):
        day, slot = "2026-11-30", "close"
        for message, fields in (
            ("run failed", {"level": "ERROR"}),
            ("market slot not published", {"reason": "close_data_unavailable"}),
            ("market slot not published", {"reason": "expired_schedule"}),
            ("market slot not published", {"reason": "paid_slot_already_claimed"}),
            ("starting run", {}),
            ("staged run artifacts", {}),
            ("market slot skipped by calendar", {"reason": "outside_session"}),
        ):
            with self.subTest(message=message, fields=fields):
                outcome = self.assess(day, slot, [record(day, slot, message, **fields)])
                self.assertEqual((outcome.status, outcome.alarm), ("failed_publication", 1))

    def test_prior_success_prior_skip_wrong_slot_and_manual_run_do_not_mask_missing(self):
        day, slot = "2026-11-30", "close"
        manual = success(day, slot)
        manual.pop("schedule_name")
        bad_time = success(day, slot)
        bad_time["scheduled_at"] = "<aws.scheduler.scheduled-time>"
        evidence = [success("2026-11-27", slot), skip("2026-11-26", slot, "market_closed"),
                    success(day, "open"), manual, bad_time]
        outcome = self.assess(day, slot, evidence)
        self.assertEqual((outcome.status, outcome.alarm), ("missed_execution", 1))

    def test_closed_weekday_missing_task_and_wrong_skip_are_not_healthy(self):
        day, slot = "2026-11-26", "close"
        self.assertEqual(self.assess(day, slot, []).status, "missed_execution")
        self.assertEqual(self.assess(day, slot, [skip(day, slot, "outside_session")]).status, "missing_calendar_skip")
        self.assertEqual(self.assess(day, slot, [success(day, slot)]).status, "unexpected_publication")
        self.assertEqual(self.assess(day, slot, [record(day, slot, "starting run")]).alarm, 1)

    def test_success_on_retry_and_duplicate_claim_warning(self):
        day, slot = "2026-11-30", "close"
        evidence = [success(day, slot), record(day, slot, "market slot not published", reason="paid_slot_already_claimed")]
        self.assertEqual(self.assess(day, slot, evidence).alarm, 0)

    def test_timezone_dst(self):
        self.assertEqual(occurrence("2026-03-06", "open"), parse_timestamp("2026-03-06T14:45:00Z"))
        self.assertEqual(occurrence("2026-03-09", "open"), parse_timestamp("2026-03-09T13:45:00Z"))
        self.assertEqual(occurrence("2026-11-27", "midday"), parse_timestamp("2026-11-27T18:15:00Z"))

    def test_runtime_context_contains_scheduler_timestamp(self):
        with patch.dict("os.environ", {"SCHEDULED_AT": "2026-11-27T21:20:00Z"}, clear=True):
            self.assertEqual(load_runtime_log_context()["scheduled_at"], "2026-11-27T21:20:00Z")
        with patch.dict("os.environ", {}, clear=True):
            self.assertNotIn("scheduled_at", load_runtime_log_context())

    def test_daily_check_paginates_and_does_not_query_weekends(self):
        day = "2026-11-27"
        cutoff = parse_timestamp("2026-11-27T23:20:00Z")
        logs = Mock()
        paginator = logs.get_paginator.return_value
        paginator.paginate.return_value = [
            {"events": [{"message": json.dumps(success(day, "open"))}]},
            {"events": []},
            {"events": [{"message": json.dumps(skip(day, "midday", "outside_session"))},
                        {"message": json.dumps(success(day, "close"))}]},
        ]
        kwargs = dict(logs=logs, group="/ecs/test", app_name=APP, schedules=SCHEDULES)
        outcomes = check_day(**kwargs, check_at=cutoff, now=cutoff + timedelta(minutes=3))
        self.assertEqual([value.alarm for value in outcomes.values()], [0, 0, 0])
        self.assertEqual(paginator.paginate.call_args.kwargs["endTime"], int(cutoff.timestamp() * 1000))
        # A retry after midnight still audits the original scheduled date.
        outcomes = check_day(**kwargs, check_at=cutoff, now=cutoff + timedelta(hours=20))
        self.assertEqual([value.alarm for value in outcomes.values()], [0, 0, 0])
        logs.reset_mock()
        weekend = cutoff + timedelta(days=1)
        outcomes = check_day(**kwargs, check_at=weekend, now=weekend)
        self.assertEqual([value.alarm for value in outcomes.values()], [0, 0, 0])
        logs.get_paginator.assert_not_called()

    def test_watchdog_fails_closed_on_query_failure_or_early_invocation(self):
        cutoff = parse_timestamp("2026-11-27T23:20:00Z")
        logs = Mock()
        logs.get_paginator.side_effect = RuntimeError("log service unavailable")
        kwargs = dict(logs=logs, group="/ecs/test", app_name=APP, schedules=SCHEDULES)
        with self.assertRaisesRegex(RuntimeError, "log service unavailable"):
            check_day(**kwargs, check_at=cutoff, now=cutoff)
        with self.assertRaisesRegex(ValueError, "grace"):
            check_day(**kwargs, check_at=cutoff - timedelta(minutes=1), now=cutoff)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            scheduled_slots(cutoff, {**SCHEDULES, "open": "rate(1 day)"})
