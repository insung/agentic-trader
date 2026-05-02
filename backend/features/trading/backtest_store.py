"""Backward-compatible imports for the trading backtest store."""

from backend.features.trading.persistence import backtest_store as _impl
from backend.features.trading.persistence.backtest_store import *  # noqa: F401,F403


def __getattr__(name: str):
    return getattr(_impl, name)
