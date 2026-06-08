from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.contracts import InstrumentSnapshot, MarketSnapshot, MarketSummary
from app.market import is_fresh_snapshot


class MarketFreshnessTests(unittest.TestCase):
    def test_snapshot_is_fresh_when_risk_instrument_is_within_max_age(self) -> None:
        snapshot = _snapshot(spy_as_of="2026-01-02T09:00:00Z")

        self.assertTrue(
            is_fresh_snapshot(
                snapshot,
                max_age_hours=2,
                now=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            )
        )

    def test_snapshot_is_stale_when_risk_instruments_are_too_old(self) -> None:
        snapshot = _snapshot(spy_as_of="2026-01-01T09:00:00Z", qqq_as_of="2026-01-01T09:00:00Z")

        self.assertFalse(
            is_fresh_snapshot(
                snapshot,
                max_age_hours=2,
                now=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            )
        )


def _snapshot(spy_as_of: str | None, qqq_as_of: str | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        as_of="2026-01-02T10:00:00Z",
        source="test",
        instruments={
            "SPY": InstrumentSnapshot(last=100, previous_close=99, change_pct=1, as_of=spy_as_of),
            "QQQ": InstrumentSnapshot(last=100, previous_close=99, change_pct=1, as_of=qqq_as_of),
        },
        summary=MarketSummary(
            spy_change_pct=1,
            qqq_change_pct=1,
            vix_change_pct=0,
            avg_risk_change_pct=1,
        ),
    )


if __name__ == "__main__":
    unittest.main()
