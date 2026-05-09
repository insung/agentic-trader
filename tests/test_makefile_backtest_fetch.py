import subprocess
from pathlib import Path


def test_backtest_fetch_accepts_timeframe_alias():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["make", "-n", "backtest-fetch", "TIMEFRAME=M5"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--timeframes M5" in result.stdout
    assert "M15,M30" not in result.stdout
