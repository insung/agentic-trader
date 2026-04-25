#!/usr/bin/env python3
"""
Agentic Trader Interactive CLI
종목, 전략, 실행 모드를 선택하여 트레이딩 파이프라인을 트리거하는 대화형 CLI 도구입니다.

사용법:
  python cli.py              # 기본 (서버: localhost:8000)
  python cli.py --port 8001  # 커스텀 포트
"""
import argparse
import json
import sys
import urllib.request
import urllib.error


def print_banner():
    print()
    print("=" * 52)
    print("   🤖 Agentic Trader — Interactive CLI")
    print("   Zero-Human Hedge Fund Control Panel")
    print("=" * 52)
    print()


def api_get(base_url: str, path: str) -> dict:
    """GET 요청을 보내고 JSON 응답을 반환합니다."""
    url = f"{base_url}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"  ❌ 서버 연결 실패: {e}")
        print(f"  ➡️  서버가 실행 중인지 확인하세요: make run-wine")
        return None
    except Exception as e:
        print(f"  ❌ API 오류: {e}")
        return None


def api_post(base_url: str, path: str, data: dict) -> dict:
    """POST 요청을 보내고 JSON 응답을 반환합니다."""
    url = f"{base_url}{path}"
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        print(f"  ❌ 서버 연결 실패: {e}")
        return None
    except Exception as e:
        print(f"  ❌ API 오류: {e}")
        return None


def check_server_health(base_url: str) -> bool:
    """서버 상태를 확인합니다."""
    print("📡 서버 상태 확인 중...")
    health = api_get(base_url, "/api/v1/health")
    if health is None:
        return False
    
    mt5_status = "✅ 연결됨" if health.get("mt5_available") else "❌ 미연결 (Mock 모드)"
    print(f"  서버: {health.get('status', 'unknown').upper()}")
    print(f"  Python: {health.get('python_version', 'N/A')}")
    print(f"  MT5: {mt5_status}")
    print()
    return True


def select_symbol(base_url: str) -> str:
    """종목 선택 메뉴를 표시하고 선택된 종목을 반환합니다."""
    print("─" * 40)
    print("📊 Step 1: 종목 선택")
    print("─" * 40)
    
    symbols = api_get(base_url, "/api/v1/symbols")
    if symbols is None:
        # 서버 연결 실패 시 기본 종목 사용
        symbols = [
            {"symbol": "EURUSD", "description": "Euro / US Dollar"},
            {"symbol": "XAUUSD", "description": "Gold / US Dollar"},
            {"symbol": "BTCUSD", "description": "Bitcoin / US Dollar"},
        ]
    
    for i, s in enumerate(symbols, 1):
        print(f"  [{i}] {s['symbol']:10s} — {s['description']}")
    
    print()
    while True:
        choice = input("  선택 (번호 입력): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(symbols):
                selected = symbols[idx]["symbol"]
                print(f"  ✅ 선택됨: {selected}")
                print()
                return selected
        except ValueError:
            # 종목 코드 직접 입력도 허용
            upper = choice.upper()
            if any(s["symbol"] == upper for s in symbols):
                print(f"  ✅ 선택됨: {upper}")
                print()
                return upper
        print("  ⚠️ 잘못된 입력입니다. 다시 선택하세요.")


def select_strategy(base_url: str) -> str:
    """전략 선택 메뉴를 표시합니다. 'auto'면 시장 상태 기반 자동 선택."""
    print("─" * 40)
    print("📈 Step 2: 전략 선택")
    print("─" * 40)
    
    strategies = api_get(base_url, "/api/v1/strategies")
    
    print(f"  [0] 자동 선택 (Market Regime 기반) ← 추천")
    if strategies:
        for i, s in enumerate(strategies, 1):
            regimes = ", ".join(s.get("allowed_regimes", []))
            print(f"  [{i}] {s['name']:30s} ({regimes})")
    
    print()
    while True:
        choice = input("  선택 (번호 입력, 기본=0): ").strip()
        if choice == "" or choice == "0":
            print("  ✅ 자동 선택 (시장 상태 기반)")
            print()
            return None  # None = auto
        try:
            idx = int(choice) - 1
            if strategies and 0 <= idx < len(strategies):
                selected = strategies[idx]["name"]
                print(f"  ✅ 선택됨: {selected}")
                print()
                return selected
        except ValueError:
            pass
        print("  ⚠️ 잘못된 입력입니다. 다시 선택하세요.")


def select_mode() -> str:
    """실행 모드 선택."""
    print("─" * 40)
    print("🔒 Step 3: 실행 모드")
    print("─" * 40)
    print("  [1] 📄 Paper Trading (모의 매매) ← 추천")
    print("  [2] 💰 Live Trading (실전 - Demo Account)")
    print()
    
    while True:
        choice = input("  선택 (번호 입력, 기본=1): ").strip()
        if choice == "" or choice == "1":
            print("  ✅ Paper Trading 모드")
            print()
            return "paper"
        elif choice == "2":
            print()
            confirm = input("  ⚠️ 실전 매매는 실제 주문이 전송됩니다. 확실합니까? (yes/no): ").strip().lower()
            if confirm == "yes":
                print("  ✅ Live Trading 모드")
                print()
                return "live"
            else:
                print("  ↩️ Paper Trading으로 변경합니다.")
                print()
                return "paper"
        print("  ⚠️ 잘못된 입력입니다. 1 또는 2를 입력하세요.")


def confirm_and_execute(base_url: str, symbol: str, strategy: str, mode: str):
    """최종 확인 후 트리거합니다."""
    strategy_display = strategy if strategy else "Auto (Market Regime)"
    mode_display = "📄 Paper" if mode == "paper" else "💰 Live"
    
    print("=" * 40)
    print("   📋 실행 요약")
    print("=" * 40)
    print(f"  종목:   {symbol}")
    print(f"  전략:   {strategy_display}")
    print(f"  모드:   {mode_display}")
    print("=" * 40)
    print()
    
    confirm = input("  실행하시겠습니까? (y/n): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("  ❌ 취소되었습니다.")
        return
    
    print()
    print("🚀 Trading workflow 트리거 중...")
    
    payload = {
        "symbol": symbol,
        "mode": mode,
    }
    if strategy:
        payload["strategy_override"] = strategy
    
    result = api_post(base_url, "/api/v1/trade/trigger", payload)
    if result:
        print(f"  ✅ {result.get('message', 'Triggered')}")
        print(f"  📌 종목: {result.get('symbol')}, 모드: {result.get('mode')}")
        print()
        print("  💡 서버 로그에서 파이프라인 실행 상태를 확인하세요.")
        print("     (서버 터미널에서 실시간 로그가 출력됩니다)")
    else:
        print("  ❌ 트리거 실패. 서버 상태를 확인하세요.")


def main():
    parser = argparse.ArgumentParser(description="Agentic Trader Interactive CLI")
    parser.add_argument("--host", default="127.0.0.1", help="서버 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="서버 포트 (기본: 8001)")
    args = parser.parse_args()
    
    base_url = f"http://{args.host}:{args.port}"
    
    print_banner()
    
    # 1. 서버 상태 확인
    if not check_server_health(base_url):
        print("  서버에 연결할 수 없습니다.")
        print(f"  서버를 먼저 시작하세요: make run-wine")
        print(f"  또는 포트를 확인하세요: python cli.py --port <PORT>")
        sys.exit(1)
    
    # 2. 종목 선택
    symbol = select_symbol(base_url)
    
    # 3. 전략 선택
    strategy = select_strategy(base_url)
    
    # 4. 모드 선택
    mode = select_mode()
    
    # 5. 확인 및 실행
    confirm_and_execute(base_url, symbol, strategy, mode)


if __name__ == "__main__":
    main()
