import pytest
from backend.features.trading.usecase import is_mt5_success

def test_is_mt5_success_valid():
    result = {
        "retcode": 10009,
        "order": 12345,
        "price": 65000.0,
        "comment": "Done"
    }
    success, reason = is_mt5_success(result)
    assert success is True
    assert reason == ""

def test_is_mt5_success_valid_placed():
    result = {
        "retcode": 10008,
        "order": 12345,
        "price": 65000.0,
        "comment": "Placed"
    }
    success, reason = is_mt5_success(result)
    assert success is True
    assert reason == ""

def test_is_mt5_success_invalid_retcode():
    result = {
        "retcode": 10013,
        "order": 0,
        "price": 0.0,
        "comment": "Invalid request"
    }
    success, reason = is_mt5_success(result)
    assert success is False
    assert "MT5 error retcode: 10013" in reason

def test_is_mt5_success_zero_ticket():
    result = {
        "retcode": 10009,
        "order": 0,
        "price": 65000.0,
        "comment": "Done"
    }
    success, reason = is_mt5_success(result)
    assert success is False
    assert "Invalid ticket/deal ID: 0" in reason

def test_is_mt5_success_zero_price():
    result = {
        "retcode": 10009,
        "order": 12345,
        "price": 0.0,
        "comment": "Done"
    }
    success, reason = is_mt5_success(result)
    assert success is False
    assert "Invalid executed price: 0.0" in reason

def test_is_mt5_success_empty_dict():
    result = {}
    success, reason = is_mt5_success(result)
    assert success is False
    assert "Empty response" in reason

def test_is_mt5_success_none():
    success, reason = is_mt5_success(None)
    assert success is False
    assert "Empty response" in reason

def test_is_mt5_success_deal_only():
    result = {
        "retcode": 10009,
        "deal": 55555,
        "price": 65000.0,
        "comment": "Done with deal"
    }
    success, reason = is_mt5_success(result)
    assert success is True
    assert reason == ""
