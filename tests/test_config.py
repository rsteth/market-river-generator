from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings, parse_task_input_json, resolve_slot, resolve_weather_conditions
from tests.helpers import make_settings


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

    def test_settings_rejects_invalid_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "IMAGE_PROVIDER"):
            make_settings(Path("runs"), image_provider="bogus")

    def test_settings_rejects_invalid_numeric_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "REPLICATE_OUTPUT_QUALITY"):
            make_settings(Path("runs"), replicate_output_quality=101)

    def test_settings_requires_provider_secret_for_fal(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "FAL_KEY"):
                make_settings(Path("runs"), image_provider="fal")

    def test_from_env_requires_replicate_token_for_replicate_provider(self) -> None:
        with patch.dict(os.environ, {"IMAGE_PROVIDER": "replicate"}, clear=True):
            with self.assertRaisesRegex(ValueError, "REPLICATE_API_TOKEN"):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
