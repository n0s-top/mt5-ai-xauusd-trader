from io import StringIO

from rich.console import Console

from src.strategies.terminal_view import render_plan


def sample():
    return {
        "symbol": "XAUUSDc",
        "status": "WAIT",
        "reason": "No valid setup",
        "preferred_side": "SELL",
        "bid": 2000,
        "ask": 2000.2,
        "currency": "USD",
        "reference_scenarios": [
            {
                "side": "SELL",
                "status": "REFERENCE_ONLY",
                "entry": 1999,
                "stop_loss": 2002,
                "take_profit": 1993,
                "reward_risk": 2,
                "volume": None,
                "sizing_note": "Equity is zero",
            }
        ],
        "expires_at_utc": "2026-10-29T09:00:00+00:00",
    }


def test_plain_view_explains_wait_lot_and_local_expiry():
    output = StringIO()
    render_plan(sample(), Console(file=output, width=100, no_color=True))
    text = output.getvalue()
    assert "WAIT" in text and "SELL" in text
    assert "N/A" in text and "Equity is zero" in text
    assert "16:00:00" in text and "UTC+7" in text
    assert "khong phai Kelly" in text
    assert "\x1b[" not in text


def test_color_view_emits_ansi_and_keeps_external_text_literal():
    output = StringIO()
    plan = sample()
    plan["reason"] = "[bold red]literal[/bold red]"
    render_plan(
        plan,
        Console(
            file=output, width=100, force_terminal=True, no_color=False, color_system="standard"
        ),
    )
    text = output.getvalue()
    assert "\x1b[" in text
    assert "[bold red]literal[/bold red]" in text


def test_blocked_view_handles_missing_market_data():
    output = StringIO()
    render_plan(
        {"symbol": "XAUUSDc", "status": "BLOCKED", "reason": "Disconnected"},
        Console(file=output, width=45, no_color=True),
    )
    assert "Disconnected" in output.getvalue()
