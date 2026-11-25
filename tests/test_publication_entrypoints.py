"""Exercise worker and watchdog entry points without network or paid generation."""
from __future__ import annotations

import io
import json
import logging
import os
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from app.main import main as worker_main
from app.pipeline import PipelineDependencies, deterministic_run_id
from app.publication_watchdog import main as watchdog_main
from app.session import parse_timestamp
from tests.helpers import make_settings
from tests.test_pipeline import FakeImageProvider, FakeMarketData, FakePromptTemplates, FakePublisher
from tests.test_publication_watchdog import APP, SCHEDULES, occurrence


class PublicationEntrypointTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        root_logger = logging.getLogger()
        handlers, level = root_logger.handlers[:], root_logger.level
        self.addCleanup(lambda: setattr(root_logger, "handlers", handlers))
        self.addCleanup(root_logger.setLevel, level)

    def worker(self, day, slot, *, failure=False, duplicate=False, stale=False):
        intended = occurrence(day, slot)
        market = Mock()
        snapshot = FakeMarketData().fetch_snapshot()
        bar_date = "2026-11-25" if stale else day
        market.fetch_snapshot.return_value = replace(snapshot, instruments={
            ticker: replace(bar, as_of=bar_date + "T05:00:00Z")
            for ticker, bar in snapshot.instruments.items()
        })
        image = FakeImageProvider(self.root)
        # Exercise paid-claim handling with a local fake, never a paid provider.
        image.name = "replicate"
        if failure:
            image.generate_image = Mock(side_effect=TimeoutError("uncertain provider outcome"))
        publisher = FakePublisher()
        publisher.claim_paid_slot = Mock(return_value=not duplicate)
        prompts = Mock(wraps=FakePromptTemplates())
        dependencies = PipelineDependencies(
            settings=make_settings(self.root), market_data=market,
            prompt_templates=prompts, image_provider=image, publisher=publisher,
            now=lambda: (intended + timedelta(seconds=2)).isoformat(),
            new_run_id=deterministic_run_id, sleep=lambda seconds: None,
        )
        env = {
            "APP_NAME": APP, "AWS_REGION": "us-east-1", "IMAGE_PROVIDER": "mock",
            "OUTPUT_DIR": str(self.root), "SCHEDULE_NAME": f"{APP}-{slot}",
            "SCHEDULE_SLOT": slot, "SCHEDULED_AT": intended.isoformat(),
            "TASK_INPUT_JSON": json.dumps({"slot": slot, "weather": "sunny"}),
        }
        output = io.StringIO()
        with (
            patch.dict(os.environ, env, clear=True), patch("app.main.load_dotenv"),
            patch("app.main.default_dependencies", return_value=dependencies), redirect_stdout(output),
        ):
            code = worker_main([])
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        for record in records:
            self.assertEqual(record["scheduled_at"], intended.isoformat())
            self.assertEqual(record["schedule_name"], f"{APP}-{slot}")
            self.assertEqual(record["schedule_slot"], slot)
        return code, records, market, image, publisher, prompts

    def watchdog(self, day, records, *, query_error=False, late=False):
        cutoff = parse_timestamp(day + "T23:20:00Z")
        logs = Mock()
        if query_error:
            logs.get_paginator.side_effect = RuntimeError("log query unavailable")
        else:
            logs.get_paginator.return_value.paginate.return_value = [
                {"events": [{"message": json.dumps(record)} for record in records]},
            ]
        env = {
            "APP_NAME": APP, "AWS_REGION": "us-east-1", "WATCHDOG_LOG_GROUP": "/ecs/test",
            "WATCHDOG_SCHEDULES": json.dumps(SCHEDULES), "WATCHDOG_SCHEDULED_AT": cutoff.isoformat(),
        }
        output = io.StringIO()
        with (
            patch.dict(os.environ, env, clear=True), patch("boto3.client", return_value=logs) as client,
            patch("app.publication_watchdog.datetime", wraps=datetime) as clock,
            patch("replicate.run") as paid_generation, redirect_stdout(output),
        ):
            clock.now.return_value = cutoff + timedelta(days=1 if late else 0)
            code = watchdog_main()
        client.assert_called_once_with("logs", region_name="us-east-1")
        paid_generation.assert_not_called()
        return code, [json.loads(line) for line in output.getvalue().splitlines()], logs

    def test_thanksgiving_through_both_entrypoints(self):
        records = []
        for slot in SCHEDULES:
            code, emitted, market, image, publisher, prompts = self.worker("2026-11-26", slot)
            self.assertEqual(code, 0)
            market.fetch_snapshot.assert_not_called()
            prompts.load_template.assert_not_called()
            publisher.claim_paid_slot.assert_not_called()
            self.assertEqual(image.calls, [])
            self.assertEqual(publisher.events, [])
            records.extend(emitted)
        code, emitted, _ = self.watchdog("2026-11-26", records)
        self.assertEqual(code, 0)
        results = [r for r in emitted if r["message"] == "publication watchdog result"]
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["status"] == "expected_calendar_skip" and r["alarm"] == 0 for r in results))
        self.assertEqual(emitted[-1]["message"], "publication watchdog completed")

    def test_early_close_worker_outputs_satisfy_watchdog(self):
        records = []
        for slot in SCHEDULES:
            code, emitted, market, image, publisher, _ = self.worker("2026-11-27", slot)
            self.assertEqual(code, 0)
            if slot == "midday":
                market.fetch_snapshot.assert_not_called()
                publisher.claim_paid_slot.assert_not_called()
                self.assertEqual(image.calls, [])
            else:
                publisher.claim_paid_slot.assert_called_once()
                self.assertEqual(len(image.calls), 1)
            records.extend(emitted)
        code, emitted, _ = self.watchdog("2026-11-27", records)
        self.assertEqual(code, 0)
        results = {r["slot"]: (r["status"], r["alarm"]) for r in emitted if "alarm" in r}
        self.assertEqual(results, {"open": ("published", 0), "midday": ("expected_calendar_skip", 0), "close": ("published", 0)})

    def test_weekends_through_entrypoints_never_generate_or_query_logs(self):
        for day in ("2026-11-28", "2026-11-29"):
            records = []
            for slot in SCHEDULES:
                code, emitted, market, image, publisher, _ = self.worker(day, slot)
                self.assertEqual(code, 0)
                market.fetch_snapshot.assert_not_called()
                publisher.claim_paid_slot.assert_not_called()
                self.assertEqual(image.calls, [])
                records.extend(emitted)
            code, emitted, logs = self.watchdog(day, records)
            self.assertEqual(code, 0)
            logs.get_paginator.assert_not_called()
            self.assertTrue(all(r["alarm"] == 0 for r in emitted if "alarm" in r))

    def test_missing_execution_failed_provider_claim_and_stale_close_alarm(self):
        for failure, duplicate, stale in ((True, False, False), (False, True, False), (False, False, True)):
            with self.subTest(failure=failure, duplicate=duplicate, stale=stale):
                worker_code, records, _, image, publisher, _ = self.worker(
                    "2026-11-30", "close", failure=failure, duplicate=duplicate, stale=stale,
                )
                self.assertEqual(worker_code, 0 if duplicate else 1)
                if failure:
                    image.generate_image.assert_called_once()
                else:
                    self.assertEqual(image.calls, [])
                if stale:
                    publisher.claim_paid_slot.assert_not_called()
                code, emitted, _ = self.watchdog("2026-11-30", records)
                self.assertEqual(code, 0)
                outcomes = {r["slot"]: r for r in emitted if "alarm" in r}
                self.assertEqual(outcomes["open"]["status"], "missed_execution")
                self.assertEqual(outcomes["close"]["status"], "failed_publication")
                self.assertTrue(all(r["alarm"] == 1 for r in outcomes.values()))

    def test_watchdog_query_failure_exits_nonzero_without_heartbeat(self):
        code, records, _ = self.watchdog("2026-11-30", [], query_error=True)
        self.assertEqual(code, 1)
        self.assertEqual(records[-1]["message"], "publication watchdog failed")
        self.assertFalse(any(r["message"] == "publication watchdog completed" for r in records))

    def test_late_watchdog_does_not_emit_current_day_heartbeat(self):
        code, records, _ = self.watchdog("2026-11-30", [], late=True)
        self.assertEqual(code, 0)
        self.assertEqual(records[-1]["message"], "publication watchdog completed late")
        self.assertFalse(any(r["message"] == "publication watchdog completed" for r in records))
