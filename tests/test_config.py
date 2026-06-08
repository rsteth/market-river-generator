from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import parse_task_input_json, resolve_slot, resolve_weather_conditions


class ConfigParsingTests(unittest.TestCase):
    def test_resolves_slot_from_cli_before_env(self) -> None:
        with patch.dict(os.environ, {"SLOT": "close"}, clear=True):
            self.assertEqual(resolve_slot("open"), "open")

    def test_resolves_all_weather_in_stable_order(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_weather_conditions("all"), ["sunny", "cloudy", "rainy"])

    def test_rejects_non_object_task_input_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_task_input_json('["open"]')

    def test_rejects_invalid_weather(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "weather condition"):
                resolve_weather_conditions("snowy")


if __name__ == "__main__":
    unittest.main()
