from unittest.mock import patch

from tools.trade_cli import confirm_and_execute, select_timeframe


def test_confirm_and_execute_posts_timeframes_list():
    with patch("builtins.input", return_value="y"), patch("tools.trade_cli.api_post") as mock_post:
        mock_post.return_value = {
            "message": "ok",
            "symbol": "EURUSD",
            "mode": "paper",
        }

        confirm_and_execute(
            "http://127.0.0.1:8001",
            "EURUSD",
            "paper",
            "M15,M30",
        )

    mock_post.assert_called_once_with(
        "http://127.0.0.1:8001",
        "/api/v1/trade/trigger",
        {
            "symbol": "EURUSD",
            "timeframes": ["M15", "M30"],
            "mode": "paper",
        },
    )


def test_select_timeframe_supports_direct_input_option():
    with patch("builtins.input", side_effect=["4", "M15,M30"]):
        assert select_timeframe() == "M15,M30"
