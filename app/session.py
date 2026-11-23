from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from math import isfinite
from zoneinfo import ZoneInfo

from app.contracts import MarketSnapshot

NEW_YORK = ZoneInfo("America/New_York")
MAX_SCHEDULE_DELAY = timedelta(minutes=20)
CLOSE_DATA_BUFFER = timedelta(minutes=10)
CLOSE_POLL_SECONDS = 30
CLOSE_FETCH_ATTEMPTS = 3


@dataclass(frozen=True)
class SlotDecision:
    session_date: date
    deadline: datetime
    skip_reason: str | None = None


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("market schedule timestamps must include a UTC offset")
    return parsed


@lru_cache(maxsize=32)
def _session_hours(session_date: date) -> tuple[datetime, datetime] | None:
    import pandas_market_calendars as calendars

    schedule = calendars.get_calendar("NYSE").schedule(start_date=session_date, end_date=session_date)
    if schedule.empty:
        return None
    row = schedule.iloc[0]
    return row.market_open.to_pydatetime(), row.market_close.to_pydatetime()


def assess_slot(slot: str, scheduled_at: datetime, now: datetime) -> SlotDecision:
    session_date = scheduled_at.astimezone(NEW_YORK).date()
    deadline = scheduled_at + MAX_SCHEDULE_DELAY
    if now < scheduled_at:
        raise ValueError("scheduled market slot is in the future")
    if now > deadline or now.astimezone(NEW_YORK).date() != session_date:
        return SlotDecision(session_date, deadline, "expired_schedule")
    hours = _session_hours(session_date)
    if hours is None:
        return SlotDecision(session_date, deadline, "market_closed")
    opens, closes = hours
    if slot in {"open", "midday"}:
        if not opens <= scheduled_at < closes or not opens <= now < closes:
            return SlotDecision(session_date, deadline, "outside_session")
    elif slot == "close":
        if scheduled_at < closes + CLOSE_DATA_BUFFER:
            return SlotDecision(session_date, deadline, "before_close_data_buffer")
    else:
        raise ValueError(f"unknown market slot: {slot}")
    return SlotDecision(session_date, deadline)


def has_session_equity_bars(snapshot: MarketSnapshot, session_date: date) -> bool:
    for ticker in ("SPY", "QQQ"):
        instrument = snapshot.instruments.get(ticker)
        if instrument is None or not instrument.as_of:
            return False
        prices = (instrument.last, instrument.previous_close, instrument.change_pct)
        if any(value is None or not isfinite(value) for value in prices):
            return False
        if instrument.last <= 0 or instrument.previous_close <= 0:
            return False
        try:
            bar_date = parse_timestamp(instrument.as_of).astimezone(NEW_YORK).date()
        except ValueError:
            return False
        if bar_date != session_date:
            return False
    return True
