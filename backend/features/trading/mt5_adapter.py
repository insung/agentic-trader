"""Compatibility wrapper for MT5 trading adapters.

New code should import from ``backend.features.trading.adapters.*``.
"""
from backend.features.trading.adapters.mt5_account import *  # noqa: F401,F403
from backend.features.trading.adapters.mt5_connection import *  # noqa: F401,F403
from backend.features.trading.adapters.mt5_execution import *  # noqa: F401,F403
from backend.features.trading.adapters.mt5_market_data import *  # noqa: F401,F403
from backend.features.trading.adapters.paper_execution import *  # noqa: F401,F403
