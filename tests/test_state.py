from __future__ import annotations

import unittest

from app.state import caption_for_state, derive_visual_state


class StateTests(unittest.TestCase):
    def test_market_mood_thresholds(self) -> None:
        cases = [
            (1.01, "strong_risk_on"),
            (0.26, "risk_on"),
            (0.25, "flat"),
            (-0.25, "flat"),
            (-0.26, "risk_off"),
            (-1.01, "strong_risk_off"),
        ]
        for avg_risk, expected in cases:
            with self.subTest(avg_risk=avg_risk):
                state = derive_visual_state(_snapshot(avg_risk, 0), weather_condition="sunny", slot="open")
                self.assertEqual(state["market_mood"], expected)

    def test_volatility_mood_thresholds(self) -> None:
        cases = [(5.01, "rising"), (5.0, "stable"), (-5.0, "stable"), (-5.01, "falling")]
        for vix_change, expected in cases:
            with self.subTest(vix_change=vix_change):
                state = derive_visual_state(_snapshot(0, vix_change), weather_condition="sunny", slot="open")
                self.assertEqual(state["volatility_mood"], expected)

    def test_caption_uses_weather_and_slot(self) -> None:
        state = derive_visual_state(_snapshot(0, 0), weather_condition="rainy", slot="close")

        self.assertTrue(caption_for_state(state).startswith("a rainy evening"))


def _snapshot(avg_risk: float, vix_change: float) -> dict[str, object]:
    return {"summary": {"avg_risk_change_pct": avg_risk, "vix_change_pct": vix_change}}


if __name__ == "__main__":
    unittest.main()
