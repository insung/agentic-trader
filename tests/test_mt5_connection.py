import MetaTrader5 as mt5

def test_connection():
    # MT5 터미널 연결 시도
    if not mt5.initialize():
        print(f"❌ MT5 초기화 실패! initialize() failed. Error: {mt5.last_error()}")
        print("➡️ 가능한 원인:")
        print("   1. MT5 데스크탑 클라이언트 켜져있지 않음")
        print("   2. 리눅스 네이티브 Python에서 이 스크립트를 실행했음 (Wine 파이썬 환경 필수)")
        mt5.shutdown()
        return

    print("✅ MT5 초기화 성공!")

    # 터미널 및 계정 정보 확인
    terminal_info = mt5.terminal_info()
    if terminal_info is not None:
        print(f"👉 터미널 정보: {terminal_info.name} (Build: {terminal_info.build})")
        print(f"👉 연결된 브로커: {terminal_info.company}")
    else:
        print("⚠️ 터미널 정보를 가져올 수 없습니다.")

    # 타겟 종목(BTCUSD) 잔고 및 호가 확인 시도
    symbol = "BTCUSD"
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"⚠️ {symbol} 심볼 정보를 찾을 수 없습니다. (MT5 종합시세에서 해당 통화쌍이 활성화되었는지 확인하세요)")
    else:
        print(f"📈 {symbol} 통화쌍 확인됨! 현재 매수호가(Ask): {symbol_info.ask}, 현재 매도호가(Bid): {symbol_info.bid}")

    mt5.shutdown()

if __name__ == "__main__":
    print("================================")
    print("MT5 (Wine) Connection Test")
    print("================================")
    test_connection()
