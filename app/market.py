from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from app.logging_utils import get_logger


TICKERS = ["SPY", "QQQ", "^VIX"]

logger = get_logger(__name__)


class MarketDataError(RuntimeError):
    pass


def fetch_market_snapshot(tickers: list[str] | None = None) -> dict[str, Any]:
    symbols = tickers or TICKERS
    instruments: dict[str, dict[str, float | None]] = {}
    errors: dict[str, str] = {}

    for ticker in symbols:
        try:
            instruments[ticker] = _fetch_instrument(ticker)
        except Exception as exc:  # yfinance raises several provider/library errors.
            logger.warning("failed to fetch ticker", extra={"_ticker": ticker, "_error": str(exc)})
            instruments[ticker] = {"last": None, "previous_close": None, "change_pct": None}
            errors[ticker] = str(exc)

    summary = _build_summary(instruments)
    snapshot: dict[str, Any] = {
        "as_of": _utc_now(),
        "source": "yfinance",
        "instruments": instruments,
        "summary": summary,
    }
    if errors:
        snapshot["errors"] = errors
    if not is_usable_snapshot(snapshot):
        raise MarketDataError("market snapshot does not contain usable SPY or QQQ data")
    return snapshot


def is_usable_snapshot(snapshot: dict[str, Any]) -> bool:
    instruments = snapshot.get("instruments", {})
    return any(_is_number(instruments.get(ticker, {}).get("change_pct")) for ticker in ("SPY", "QQQ"))


def _fetch_instrument(ticker: str) -> dict[str, float | None]:
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

    return {
        "last": _round_or_none(last),
        "previous_close": _round_or_none(previous_close),
        "change_pct": _round_or_none(change_pct),
    }


def _build_summary(instruments: dict[str, dict[str, float | None]]) -> dict[str, float | None]:
    spy_change = instruments.get("SPY", {}).get("change_pct")
    qqq_change = instruments.get("QQQ", {}).get("change_pct")
    vix_change = instruments.get("^VIX", {}).get("change_pct")
    risk_values = [value for value in (spy_change, qqq_change) if _is_number(value)]
    avg_risk = sum(risk_values) / len(risk_values) if risk_values else None

    return {
        "spy_change_pct": spy_change,
        "qqq_change_pct": qqq_change,
        "vix_change_pct": vix_change,
        "avg_risk_change_pct": _round_or_none(avg_risk),
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(float(value))


def _round_or_none(value: float | None) -> float | None:
    if value is None or math.isnan(value):
        return None
    return round(float(value), 4)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

