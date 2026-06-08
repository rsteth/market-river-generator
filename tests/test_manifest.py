from __future__ import annotations

import unittest

from app.manifest import update_latest_manifest


def item(run_id: str, slot: str, weather: str, created_at: str = "2026-01-02T10:00:00Z") -> dict[str, object]:
    return {
        "id": f"2026-01-02-{slot}-{run_id}",
        "run_id": run_id,
        "slot": slot,
        "weather": weather,
        "date": "2026-01-02",
        "created_at": created_at,
    }


class ManifestTests(unittest.TestCase):
    def test_replaces_same_date_slot_weather(self) -> None:
        existing = {"items": [item("old", "open", "sunny")]}
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


if __name__ == "__main__":
    unittest.main()
