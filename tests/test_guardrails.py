import unittest
import sys
import os

# Add the project root to sys.path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.guardrails import (
    validate_daily_drawdown_lock,
    validate_max_trades_per_day,
    validate_risk_reward_ratio,
    enforce_one_percent_rule,
    validate_sl_tp_modification_limit
)

class TestGuardrails(unittest.TestCase):

    def test_validate_daily_drawdown_lock(self):
        # Rule 2: 2% 이상 손실 시 차단 (False 반환)
        self.assertTrue(validate_daily_drawdown_lock(1.5))
        self.assertTrue(validate_daily_drawdown_lock(1.99))
        
        # 2% 손실 (차단)
        self.assertFalse(validate_daily_drawdown_lock(2.0))
        # 5% 손실 (당일 하드 락)
        self.assertFalse(validate_daily_drawdown_lock(5.0))

    def test_validate_max_trades_per_day(self):
        # Rule 3: 하루 최대 3회 이하. 당일 4번째 진입 기각
        self.assertTrue(validate_max_trades_per_day(0))
        self.assertTrue(validate_max_trades_per_day(2))
        
        # 3회 이미 체결되었으면 4번째 진입 시도이므로 차단
        self.assertFalse(validate_max_trades_per_day(3))
        self.assertFalse(validate_max_trades_per_day(4))

    def test_validate_risk_reward_ratio(self):
        # Rule 4: 손익비 2.0 이상
        # Long position: 진입 100, 익절 120 (수익 20), 손절 90 (손실 10) => 손익비 2.0 (True)
        self.assertTrue(validate_risk_reward_ratio(100.0, 90.0, 120.0))
        
        # Long position: 진입 100, 익절 115 (수익 15), 손절 90 (손실 10) => 손익비 1.5 (False)
        self.assertFalse(validate_risk_reward_ratio(100.0, 90.0, 115.0))
        
        # Short position: 진입 100, 익절 80 (수익 20), 손절 110 (손실 10) => 손익비 2.0 (True)
        self.assertTrue(validate_risk_reward_ratio(100.0, 110.0, 80.0))
        
        # Short position: 진입 100, 익절 85 (수익 15), 손절 110 (손실 10) => 손익비 1.5 (False)
        self.assertFalse(validate_risk_reward_ratio(100.0, 110.0, 85.0))
        
        # 잘못된 주문 (SL, TP가 모두 진입가 위)
        self.assertFalse(validate_risk_reward_ratio(100.0, 110.0, 120.0))
        
        # 잘못된 값 (0 이하)
        self.assertFalse(validate_risk_reward_ratio(0.0, 10.0, 20.0))

    def test_enforce_one_percent_rule(self):
        # Rule 1: 1% 룰 기반 랏수 계산
        # 자산 10,000, 1%는 100. 
        # 진입 1.1000, 손절 1.0900 (차이 0.0100)
        # lot_size = 100 / 0.0100 = 10000.0
        self.assertAlmostEqual(enforce_one_percent_rule(10000.0, 1.1000, 1.0900), 10000.0)
        
        # 잔고가 0이거나 음수일 때
        self.assertEqual(enforce_one_percent_rule(0.0, 1.1000, 1.0900), 0.0)
        
        # 손절가와 진입가가 같을 때 (가격 차이 0)
        self.assertEqual(enforce_one_percent_rule(10000.0, 1.1000, 1.1000), 0.0)
        
        # Short position도 동일하게 계산되는지 확인
        # 진입 1.1000, 손절 1.1100 (차이 0.0100)
        self.assertAlmostEqual(enforce_one_percent_rule(10000.0, 1.1000, 1.1100), 10000.0)

    def test_validate_sl_tp_modification_limit(self):
        # Rule 5: 1회 수정 제한
        # 아직 수정되지 않은 경우 (0회) -> 수정 가능 (True)
        self.assertTrue(validate_sl_tp_modification_limit(12345, 0))
        
        # 이미 1회 수정된 경우 -> 수정 불가 (False)
        self.assertFalse(validate_sl_tp_modification_limit(12345, 1))
        
        # 이미 여러 번 수정된 경우 (발생하면 안 되지만 테스트) -> 수정 불가 (False)
        self.assertFalse(validate_sl_tp_modification_limit(12345, 2))

if __name__ == '__main__':
    unittest.main()
