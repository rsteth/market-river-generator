from __future__ import annotations

import unittest

from app.prompts import PromptTemplate, compose_prompt, sha256_text


class PromptTests(unittest.TestCase):
    def test_compose_prompt_fills_required_placeholders(self) -> None:
        template_text = "Weather: {weather}\nTime: {time_of_day}\nMarket: {market_condition}"
        template = PromptTemplate(
            prompt_id="river_city",
            version="test",
            text=template_text,
            source="test",
            sha256=sha256_text(template_text),
        )
        state = {
            "market_mood": "risk_on",
            "weather": {"condition": "sunny"},
            "time_of_day": {"slot": "open"},
        }

        result = compose_prompt(state, template=template)

        self.assertIn("Clear dry weather", result.positive_prompt)
        self.assertIn("Early morning atmosphere", result.positive_prompt)
        self.assertIn("constructive and open", result.positive_prompt)

    def test_compose_prompt_rejects_unknown_placeholder(self) -> None:
        template = PromptTemplate(
            prompt_id="river_city",
            version="test",
            text="Unknown: {missing}",
            source="test",
            sha256=sha256_text("Unknown: {missing}"),
        )
        state = {
            "market_mood": "flat",
            "weather": {"condition": "sunny"},
            "time_of_day": {"slot": "open"},
        }

        with self.assertRaises(KeyError):
            compose_prompt(state, template=template)


if __name__ == "__main__":
    unittest.main()
