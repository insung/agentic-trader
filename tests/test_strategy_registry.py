import pytest
from backend.workflows.strategy_registry import resolve_strategy_profile

def test_resolve_strategy_profile_priority():
    strategy_contract = {
        "profiles": [
            {
                "name": "short_profile",
                "primary_timeframe": "M15",
                "confirmation_timeframes": []
            },
            {
                "name": "long_profile",
                "primary_timeframe": "M15",
                "confirmation_timeframes": ["H1", "H4"]
            },
            {
                "name": "medium_profile",
                "primary_timeframe": "M15",
                "confirmation_timeframes": ["H1"]
            }
        ]
    }
    
    # When requesting M15, H1, H4, it should match long_profile (length 3)
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15", "H1", "H4", "D1"])
    assert ptf == "M15"
    assert ctf == ["H1", "H4"]
    
    # When requesting M15, H1, it should match medium_profile (length 2)
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15", "H1"])
    assert ptf == "M15"
    assert ctf == ["H1"]
    
    # When requesting just M15, it should match short_profile (length 1)
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15"])
    assert ptf == "M15"
    assert ctf == []

def test_resolve_strategy_profile_symbol_gate():
    strategy_contract = {
        "profiles": [
            {
                "name": "btc_profile",
                "allowed_symbols": ["BTCUSD"],
                "primary_timeframe": "M15",
                "confirmation_timeframes": ["M30"]
            },
            {
                "name": "nas_profile",
                "allowed_symbols": ["NAS100ft.r"],
                "primary_timeframe": "M15",
                "confirmation_timeframes": ["M30"]
            }
        ]
    }
    
    # Should match btc_profile for BTCUSD
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15", "M30"], "BTCUSD")
    assert ptf == "M15"
    assert ctf == ["M30"]
    
    # Should match nas_profile for NAS100ft.r
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15", "M30"], "NAS100ft.r")
    assert ptf == "M15"
    assert ctf == ["M30"]
    
    # Should not match any for ETHUSD
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15", "M30"], "ETHUSD")
    assert ptf is None
    assert ctf == []

def test_resolve_strategy_profile_fallback():
    strategy_contract = {
        "required_timeframes": ["M15", "H1"]
    }
    
    # No profiles defined, should fallback to required_timeframes
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15", "H1", "H4"])
    assert ptf == "M15"
    assert ctf == ["H1"]
    
    # Missing required timeframes, should return None
    ptf, ctf = resolve_strategy_profile(strategy_contract, ["M15"])
    assert ptf is None
    assert ctf == []
