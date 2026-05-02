"""Compatibility wrapper for trading operations position tracking."""
import sys

from backend.features.trading.operations import position_tracker as _position_tracker

sys.modules[__name__] = _position_tracker
