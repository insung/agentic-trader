"""Compatibility wrapper for backtest reporting helpers.

New code should import from ``backend.features.trading.research.reporting``.
"""
from backend.features.trading.research.reporting import *  # noqa: F401,F403
from backend.features.trading.research.reporting import _summarize_decisions  # noqa: F401
