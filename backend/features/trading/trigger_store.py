"""Backward-compatible imports for the trigger store."""

from backend.features.trading.persistence import trigger_store as _impl
from backend.features.trading.persistence.trigger_store import *  # noqa: F401,F403


def __getattr__(name: str):
    return getattr(_impl, name)
