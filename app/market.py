from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from app.contracts import InstrumentSnapshot, MarketSnapshot, MarketSummary
from app.logging_utils import get_logger


TICKERS = ["SPY", "QQQ", "^VIX"]

logger = get_logger(__name__)


class MarketDataError(RuntimeError):
    pass


def fetch_market_snapshot(tickers: list[str] | None = None, *, max_age_hours: int = 120) -> MarketSnapshot:
    symbols = tickers or TICKERS
    instruments: dict[str, InstrumentSnapshot] = {}
    errors: dict[str, str] = {}

    for ticker in symbols:
        try:
            instruments[ticker] = _fetch_instrument(ticker)
        except Exception as exc:  # yfinance raises several provider/library errors.
            logger.warning("failed to fetch ticker", extra={"_ticker": ticker, "_error": str(exc)})
            instruments[ticker] = InstrumentSnapshot(last=None, previous_close=None, change_pct=None)
            errors[ticker] = str(exc)

    summary = _build_summary(instruments)
    snapshot = MarketSnapshot(
        as_of=_utc_now(),
        source="yfinance",
        instruments=instruments,
        summary=summary,
        errors=errors,
    )
    if not is_usable_snapshot(snapshot):
        raise MarketDataError("market snapshot does not contain usable SPY or QQQ data")
    if not is_fresh_snapshot(snapshot, max_age_hours=max_age_hours):
        raise MarketDataError(f"market snapshot is older than {max_age_hours} hours")
    return snapshot


def is_usable_snapshot(snapshot: MarketSnapshot) -> bool:
    empty = InstrumentSnapshot(last=None, previous_close=None, change_pct=None)
    return any(_is_number(snapshot.instruments.get(ticker, empty).change_pct) for ticker in ("SPY", "QQQ"))


def is_fresh_snapshot(
    snapshot: MarketSnapshot,
    *,
    max_age_hours: int,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(timezone.utc)
    for ticker in ("SPY", "QQQ"):
        instrument = snapshot.instruments.get(ticker)
        if instrument is None or not instrument.as_of:
            continue
        as_of = datetime.fromisoformat(instrument.as_of.replace("Z", "+00:00"))
        age_hours = (current - as_of).total_seconds() / 3600
        if age_hours <= max_age_hours:
            return True
    return False


def _fetch_instrument(ticker: str) -> InstrumentSnapshot:
    history = yf.Ticker(ticker).history(period="7d", interval="1d", auto_adjust=False)
    if history is None or history.empty:
        raise MarketDataError(f"no history returned for {ticker}")

    close_series = history["Close"].dropna()
    if len(close_series) < 2:
        raise MarketDataError(f"not enough close data returned for {ticker}")

    last = float(close_series.iloc[-1])
    previous_close = float(close_series.iloc[-2])
    if previous_close == 0:
        change_pct = None
    else:
        change_pct = ((last - previous_close) / previous_close) * 100.0

    return InstrumentSnapshot(
        last=_round_or_none(last),
        previous_close=_round_or_none(previous_close),
        change_pct=_round_or_none(change_pct),
        as_of=_timestamp_to_utc_iso(close_series.index[-1]),
    )


def _build_summary(instruments: dict[str, InstrumentSnapshot]) -> MarketSummary:
    spy_change = instruments.get("SPY", InstrumentSnapshot(None, None, None)).change_pct
    qqq_change = instruments.get("QQQ", InstrumentSnapshot(None, None, None)).change_pct
    vix_change = instruments.get("^VIX", InstrumentSnapshot(None, None, None)).change_pct
    risk_values = [value for value in (spy_change, qqq_change) if _is_number(value)]
    avg_risk = sum(risk_values) / len(risk_values) if risk_values else None

    return MarketSummary(
        spy_change_pct=spy_change,
        qqq_change_pct=qqq_change,
        vix_change_pct=vix_change,
        avg_risk_change_pct=_round_or_none(avg_risk),
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(float(value))


def _round_or_none(value: float | None) -> float | None:
    if value is None or math.isnan(value):
        return None
    return round(float(value), 4)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_to_utc_iso(value: Any) -> str:
    to_pydatetime = getattr(value, "to_pydatetime", None)
    parsed = to_pydatetime() if callable(to_pydatetime) else value
    if not isinstance(parsed, datetime):
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
