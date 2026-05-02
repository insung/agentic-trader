"""Backward-compatible imports for the trading log store."""

from backend.features.trading.persistence import trading_log_store as _impl
from backend.features.trading.persistence.trading_log_store import *  # noqa: F401,F403


def __getattr__(name: str):
    return getattr(_impl, name)
