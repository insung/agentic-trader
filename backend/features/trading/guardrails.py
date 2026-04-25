"""
안전 방어 규칙 (Safety Guardrails) 인터셉터
AI의 모든 주문 요청은 MT5로 전송되기 전, 이 모듈의 함수들을 무조건 통과해야 합니다.
"""

def validate_daily_drawdown_lock(current_loss_pct: float) -> bool:
    """
    Rule 2: 일일 손실 한도 검사 (가장 중요)
    - 2% 이상 손실 시 1시간 쿨다운 (403 Forbidden)
    - 5% 이상 손실 시 당일 하드 락
    - current_loss_pct: 당일 누적 손실률 (예: 2.5 = 2.5% 손실)
    - 반환값: 통과 시 True, 차단 시 False
    """
    if current_loss_pct >= 2.0:
        return False
    return True

def validate_max_trades_per_day(today_trade_count: int) -> bool:
    """
    Rule 3: 하루 최대 매매 횟수 제한 (Over-trading 방지)
    - 당일 진입 횟수 3회 이하인지 검사 (429 Too Many Requests)
    - today_trade_count: 오늘 이미 체결된 진입 횟수
    - 반환값: 3회 미만일 경우 True (4번째 진입부터 차단)
    """
    if today_trade_count >= 3:
        return False
    return True

def validate_risk_reward_ratio(entry_price: float, sl_price: float, tp_price: float) -> bool:
    """
    Rule 4: 최소 손익비 검증 로직
    - 예상 수익 / 예상 손실 비율이 최소 2.0 이상인지 검사 (400 Bad Request)
    - 반환값: 손익비 1:2 이상 시 True, 그 외 False
    """
    if entry_price <= 0 or sl_price <= 0 or tp_price <= 0:
        return False

    # Long (매수) 포지션: TP는 진입가 위, SL은 진입가 아래
    if tp_price > entry_price and sl_price < entry_price:
        expected_profit = tp_price - entry_price
        expected_loss = entry_price - sl_price
    # Short (매도) 포지션: TP는 진입가 아래, SL은 진입가 위
    elif tp_price < entry_price and sl_price > entry_price:
        expected_profit = entry_price - tp_price
        expected_loss = sl_price - entry_price
    else:
        # SL/TP가 논리적으로 맞지 않는 경우 (예: 둘 다 진입가보다 높음)
        return False

    if expected_loss == 0:
        return False

    rr_ratio = expected_profit / expected_loss
    return rr_ratio >= 2.0

def enforce_one_percent_rule(account_balance: float, entry_price: float, sl_price: float) -> float:
    """
    Rule 1: 1% 룰 기반 최대 랏수 강제 계산기
    - SL 도달 시 총 자산의 1%만 잃도록 안전한 랏(Lot) 사이즈를 역산하여 반환.
    - AI가 요청한 Lot 수치는 무시되고 이 함수의 리턴값으로 덮어씌워짐.
    """
    if account_balance <= 0:
        return 0.0
        
    price_diff = abs(entry_price - sl_price)
    if price_diff == 0:
        return 0.0
        
    risk_amount = account_balance * 0.01
    lot_size = risk_amount / price_diff
    
    # MT5 랏 단위에 맞춰 소수점 둘째 자리까지 반올림 (예: 0.01)
    return round(lot_size, 2)

def validate_sl_tp_modification_limit(ticket_id: int, modify_count: int) -> bool:
    """
    Rule 5: 손절/익절 라인 수정 1회 제한
    - 물타기 방지를 위해 동일 포지션에 대한 SL/TP 수정 횟수 검사
    - modify_count: 이미 수정된 횟수
    - 반환값: 0회일 경우 True, 1회 이상일 경우 False
    """
    if modify_count >= 1:
        return False
    return True
