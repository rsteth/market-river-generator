from __future__ import annotations

import unittest

from app.manifest import update_latest_manifest, update_recent_manifest_items


def item(
    run_id: str,
    slot: str,
    weather: str,
    created_at: str = "2026-01-02T10:00:00Z",
    date: str = "2026-01-02",
) -> dict[str, object]:
    return {
        "id": f"{date}-{slot}-{run_id}",
        "run_id": run_id,
        "slot": slot,
        "weather": weather,
        "date": date,
        "created_at": created_at,
    }


class ManifestTests(unittest.TestCase):
    def test_replaces_same_date_slot_weather(self) -> None:
        existing = {"items": [item("old", "open", "sunny")]}
        updated = update_latest_manifest(existing, item("new", "open", "sunny"), updated_at="now")

        self.assertEqual([entry["run_id"] for entry in updated["items"]], ["new"])

    def test_replaces_older_date_for_same_slot_weather(self) -> None:
        existing = {"items": [item("old", "open", "sunny", date="2026-01-01")]}
        updated = update_latest_manifest(existing, item("new", "open", "sunny"), updated_at="now")

        self.assertEqual([entry["run_id"] for entry in updated["items"]], ["new"])

    def test_keeps_weather_variants_and_sorts_by_slot_then_weather(self) -> None:
        existing = {
            "items": [
                item("rain", "midday", "rainy"),
                item("close", "close", "sunny"),
                item("cloud", "open", "cloudy"),
            ]
        }
        updated = update_latest_manifest(existing, item("sun", "open", "sunny"), updated_at="now")

        self.assertEqual(
            [(entry["slot"], entry["weather"], entry["run_id"]) for entry in updated["items"]],
            [
                ("open", "sunny", "sun"),
                ("open", "cloudy", "cloud"),
                ("midday", "rainy", "rain"),
                ("close", "sunny", "close"),
            ],
        )

    def test_recent_manifest_replaces_same_date_slot_weather_only(self) -> None:
        existing = {
            "items": [
                item("older", "open", "sunny", date="2026-01-01"),
                item("same-date", "open", "sunny", date="2026-01-02"),
            ]
        }

        updated = update_recent_manifest_items(
            existing,
            [item("new", "open", "sunny", date="2026-01-02")],
            updated_at="now",
        )

        self.assertEqual([entry["run_id"] for entry in updated["items"]], ["new", "older"])

    def test_recent_manifest_caps_by_snapshot_group_and_keeps_weather_variants(self) -> None:
        existing = {
            "items": [
                item("old-open", "open", "sunny", date="2026-01-01"),
                item("mid-sun", "midday", "sunny", date="2026-01-02"),
                item("mid-rain", "midday", "rainy", date="2026-01-02"),
                item("close", "close", "cloudy", date="2026-01-02"),
            ]
        }

        updated = update_recent_manifest_items(
            existing,
            [item("new", "open", "sunny", date="2026-01-03")],
            updated_at="now",
            max_snapshot_groups=3,
        )

        self.assertEqual(
            [(entry["date"], entry["slot"], entry["weather"], entry["run_id"]) for entry in updated["items"]],
            [
                ("2026-01-03", "open", "sunny", "new"),
                ("2026-01-02", "close", "cloudy", "close"),
                ("2026-01-02", "midday", "sunny", "mid-sun"),
                ("2026-01-02", "midday", "rainy", "mid-rain"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
