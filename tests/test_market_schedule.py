from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

import httpx
import replicate
import requests
from botocore.exceptions import ClientError

from app.config import resolve_run_request
from app.contracts import RunRequest
from app.image_model import FalImageProvider, ReplicateImageProvider
from app.main import main
from app.pipeline import PipelineDependencies, deterministic_run_id, run_pipeline
from app.prompts import PromptResult
from app.publish import Publisher
from app.session import assess_slot, parse_timestamp
from tests.helpers import make_settings
from tests.test_pipeline import FakeImageProvider, FakeMarketData, FakePromptTemplates, FakePublisher


class ScheduledPipelineTests(TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.publisher = FakePublisher()
        self.held_claims: set[tuple[str, str]] = set()

        def claim(*, session_date: str, slot: str, run_id: str) -> bool:
            key = (session_date, slot)
            if key in self.held_claims:
                return False
            self.held_claims.add(key)
            return True

        self.publisher.claim_paid_slot = Mock(side_effect=claim)
        self.data = Mock()
        self.image = FakeImageProvider(self.root)
        self.image.name = "replicate"
        self.prompts = Mock(wraps=FakePromptTemplates())
        self.now = parse_timestamp("2026-11-25T14:45:00Z")
        self.deps = PipelineDependencies(
            settings=make_settings(self.root),
            market_data=self.data,
            prompt_templates=self.prompts,
            image_provider=self.image,
            publisher=self.publisher,
            now=lambda: self.now.isoformat(),
            sleep=self.advance,
            new_run_id=deterministic_run_id,
        )

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def snapshot(self, date: str, *, qqq_date: str | None = None):
        snapshot = FakeMarketData().fetch_snapshot()
        return replace(snapshot, instruments={
            ticker: replace(bar, as_of=(qqq_date or date if ticker == "QQQ" else date) + "T05:00:00Z")
            for ticker, bar in snapshot.instruments.items()
        })

    def execute(self, slot: str, intended: str, actual: str | None = None, weather: tuple[str, ...] = ("sunny",)):
        self.now = parse_timestamp(actual or intended)
        return run_pipeline(RunRequest(slot=slot, weather_conditions=weather, scheduled_at=intended), self.deps)

    def test_holiday_with_usable_previous_session_data_does_not_touch_any_boundary(self) -> None:
        self.data.fetch_snapshot.return_value = self.snapshot("2026-11-25")
        for slot, time in (("open", "14:45"), ("midday", "18:15"), ("close", "21:20")):
            with self.subTest(slot=slot):
                result = self.execute(slot, f"2026-11-26T{time}:00Z")
                self.assertEqual(result.skip_reason, "market_closed")
        self.data.fetch_snapshot.assert_not_called()
        self.prompts.load_template.assert_not_called()
        self.publisher.claim_paid_slot.assert_not_called()
        self.assertEqual(self.publisher.events, [])
        self.assertEqual(self.image.calls, [])

    def test_scheduler_entrypoint_holiday_with_resolved_ecs_environment(self) -> None:
        from app.config import Settings

        environment = {
            "SCHEDULE_NAME": "market-river-close",
            "SCHEDULED_AT": "2026-11-26T21:20:00Z",
            "TASK_INPUT_JSON": '{"slot":"close"}',
        }
        self.now = parse_timestamp("2026-11-26T21:20:02Z")
        with (
            patch.dict("os.environ", environment, clear=True),
            patch("app.main.load_dotenv"),
            patch.object(Settings, "from_env", return_value=self.deps.settings),
            patch("app.main.default_dependencies", return_value=self.deps),
            self.assertLogs("app.pipeline", level="INFO") as logs,
        ):
            self.assertEqual(main([]), 0)
        self.assertTrue(any("market slot skipped by calendar" in record.message for record in logs.records))
        self.data.fetch_snapshot.assert_not_called()
        self.publisher.claim_paid_slot.assert_not_called()
        self.assertEqual(self.publisher.events, [])
        self.assertEqual(self.image.calls, [])

    def test_regular_day_keeps_all_slots_and_half_day_drops_midday(self) -> None:
        for day, allowed_slots in (("25", ("open", "midday", "close")), ("27", ("open", "close"))):
            self.data.fetch_snapshot.return_value = self.snapshot(f"2026-11-{day}")
            for slot, time in (("open", "14:45"), ("midday", "18:15"), ("close", "21:20")):
                result = self.execute(slot, f"2026-11-{day}T{time}:00Z")
                self.assertTrue(result.succeeded)
                self.assertEqual(result.skip_reason, None if slot in allowed_slots else "outside_session")
        self.assertEqual([item["slot"] for item in self.image.calls], ["open", "midday", "close", "open", "close"])
        self.assertEqual(self.data.fetch_snapshot.call_count, 5)

    def test_close_catches_up_with_only_market_reads_and_then_claims_once(self) -> None:
        yesterday = self.snapshot("2026-11-25")
        mixed = self.snapshot("2026-11-27", qqq_date="2026-11-25")
        current = self.snapshot("2026-11-27")
        self.data.fetch_snapshot.side_effect = [yesterday, mixed, current]
        held_counts = []
        original_sleep = self.deps.sleep

        def sleep_without_claim(seconds):
            held_counts.append(len(self.held_claims))
            original_sleep(seconds)

        self.deps = replace(self.deps, sleep=sleep_without_claim)
        result = self.execute("close", "2026-11-27T21:20:00Z")
        self.assertTrue(result.succeeded)
        self.assertEqual(result.skip_reason, None)
        self.assertEqual(held_counts, [0, 0])
        self.assertEqual(len(self.image.calls), 1)

    def test_stale_close_exhausts_data_only_attempts_and_leaves_no_claim(self) -> None:
        self.data.fetch_snapshot.return_value = self.snapshot("2026-11-27", qqq_date="2026-11-25")
        result = self.execute("close", "2026-11-27T21:20:00Z")
        self.assertEqual(result.skip_reason, "close_data_unavailable")
        self.assertFalse(result.succeeded)
        self.assertEqual(self.data.fetch_snapshot.call_count, 3)
        self.publisher.claim_paid_slot.assert_not_called()
        self.prompts.load_template.assert_not_called()
        self.assertEqual(self.image.calls, [])
        self.assertEqual(self.publisher.events, [])

    def test_late_start_uses_intended_session_and_never_fetches_another_day(self) -> None:
        result = self.execute("close", "2026-11-25T21:20:00Z", "2026-11-27T14:45:00Z")
        self.assertEqual(result.skip_reason, "expired_schedule")
        self.data.fetch_snapshot.assert_not_called()
        self.publisher.claim_paid_slot.assert_not_called()

    def test_catchup_near_deadline_does_not_poll_or_claim(self) -> None:
        self.data.fetch_snapshot.return_value = self.snapshot("2026-11-25")
        result = self.execute("close", "2026-11-27T21:20:00Z", "2026-11-27T21:39:55Z")
        self.assertEqual(result.skip_reason, "close_data_unavailable")
        self.data.fetch_snapshot.assert_called_once()
        self.publisher.claim_paid_slot.assert_not_called()

    def test_manual_close_uses_ny_session_for_claim_and_metadata_after_utc_midnight(self) -> None:
        self.data.fetch_snapshot.return_value = self.snapshot("2026-11-27")
        self.now = parse_timestamp("2026-11-28T00:10:00Z")
        request = RunRequest(slot="close", weather_conditions=("sunny",))
        result = run_pipeline(request, self.deps)
        self.assertTrue(result.succeeded)
        self.assertEqual(self.publisher.successes[0].session_date, "2026-11-27")
        self.assertTrue(self.publisher.successes[0].created_at.startswith("2026-11-28T"))
        self.assertIn(("2026-11-27", "close"), self.held_claims)
        earlier_run = deterministic_run_id(request, "2026-11-27T21:20:00Z")
        self.assertEqual(earlier_run, result.run_id)

    def test_uncertain_paid_outcome_cannot_spend_twice_even_with_changed_weather(self) -> None:
        self.data.fetch_snapshot.return_value = self.snapshot("2026-11-27")
        self.image.generate_image = Mock(side_effect=TimeoutError("provider outcome unknown"))
        with self.assertLogs("app.pipeline", level="ERROR"):
            first = self.execute("close", "2026-11-27T21:20:00Z")
        self.assertFalse(first.succeeded)
        after = list(self.publisher.events)
        next_attempt = self.execute("close", "2026-11-27T21:20:00Z", "2026-11-27T21:25:00Z", ("cloudy",))
        self.assertEqual(next_attempt.skip_reason, "paid_slot_already_claimed")
        self.image.generate_image.assert_called_once()
        self.assertEqual(self.publisher.events, after)


class ScheduleBoundaryTests(TestCase):
    def test_dst_and_close_boundary(self) -> None:
        for value in ("2026-03-06T14:45:00Z", "2026-03-09T13:45:00Z"):
            now = parse_timestamp(value)
            self.assertIsNone(assess_slot("open", now, now).skip_reason)
        exact_close = parse_timestamp("2026-11-27T18:00:00Z")
        self.assertEqual(assess_slot("midday", exact_close, exact_close).skip_reason, "outside_session")
        self.assertEqual(assess_slot("close", exact_close, exact_close).skip_reason, "before_close_data_buffer")

    def test_actual_scheduler_env_override_is_required_not_wall_clock_fallback(self) -> None:
        with patch.dict("os.environ", {"SCHEDULE_NAME": "market-river-close", "TASK_INPUT_JSON": '{"slot":"close"}'}, clear=True):
            with self.assertRaisesRegex(ValueError, "SCHEDULED_AT"):
                resolve_run_request(None, None)
            with patch.dict("os.environ", {"SCHEDULED_AT": "2026-11-27T21:20:00Z"}):
                self.assertEqual(resolve_run_request(None, None).scheduled_at, "2026-11-27T21:20:00Z")
        with self.assertRaises(ValueError):
            parse_timestamp("<aws.scheduler.scheduled-time>")

    def test_s3_claim_is_create_only_and_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            publisher = Publisher(make_settings(Path(tmp)))
            publisher._s3 = Mock()
            kwargs = {"session_date": "2026-11-27", "slot": "close", "run_id": "test"}
            self.assertTrue(publisher.claim_paid_slot(**kwargs))
            sent = publisher._s3.put_object.call_args.kwargs
            self.assertEqual(sent["IfNoneMatch"], "*")
            self.assertEqual(sent["Key"], "generation-claims/2026-11-27/close.json")
            for code in ("PreconditionFailed", "AccessDenied", "ConditionalRequestConflict"):
                publisher._s3.put_object.side_effect = ClientError({"Error":{"Code": code}}, "PutObject")
                if code == "PreconditionFailed":
                    self.assertFalse(publisher.claim_paid_slot(**kwargs))
                else:
                    with self.assertRaises(ClientError):
                        publisher.claim_paid_slot(**kwargs)

    def test_pinned_replicate_transport_never_replays_prediction_post(self) -> None:
        attempts = []

        def reject(request: httpx.Request) -> httpx.Response:
            attempts.append(request.method)
            return httpx.Response(503, json={"detail": "ambiguous"})

        client = replicate.Client(api_token="not-real", transport=httpx.MockTransport(reject))
        with self.assertRaises(replicate.exceptions.ReplicateError):
            client.run("black-forest-labs/flux-2-pro", input={"prompt": "river"})
        self.assertEqual(attempts, ["POST"])

    def test_ambiguous_provider_errors_are_not_retried(self) -> None:
        prompt = Mock(spec=PromptResult)
        prompt.provider = "test"
        prompt.positive_prompt = "river"
        prompt.negative_prompt = ""
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            args = dict(prompt_result=prompt, run_id="x", output_dir=path, slot="close", market_mood="test", volatility_mood="test")
            with patch("replicate.run", side_effect=TimeoutError("uncertain")) as replicate:
                with self.assertRaises(TimeoutError):
                    ReplicateImageProvider(make_settings(path)).generate_image(**args)
                replicate.assert_called_once()
            with patch.dict("os.environ", {"FAL_KEY":"not-a-real-key"}, clear=True):
                with patch("requests.post", side_effect=requests.Timeout("uncertain")) as fal:
                    with self.assertRaises(requests.Timeout):
                        FalImageProvider(make_settings(path)).generate_image(**args)
                    fal.assert_called_once()
                    self.assertFalse(fal.call_args.kwargs["allow_redirects"])
