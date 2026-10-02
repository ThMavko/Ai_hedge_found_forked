import json
import re

from dashboard_data import build_payload, extract_completed_trades
from dashboard_generator import _render


def _portfolio():
    def entry(day, total, txns=None):
        return {
            "timestamp": f"2026-03-{day:02d}T12:00:00+00:00",
            "session": "sera",
            "total_value_eur": total,
            "current_cash": total,
            "positions": {},
            "prices_used": {},
            "transactions": txns or [],
        }

    log = [
        entry(2, 3000.0, [{"action": "BUY", "ticker": "AAPL", "shares": 2, "price_eur": 100.0}]),
        entry(3, 3010.0),
        entry(4, 3020.0, [{"action": "SELL", "ticker": "AAPL", "shares": 1, "price_eur": 110.0}]),
    ]
    return {
        "metadata": {"initial_capital": 3000.0, "current_cash": 3020.0},
        "current_positions": {"AAPL": {"shares": 1, "avg_price": 100.0}},
        "iterations_log": log,
    }


def test_completed_trades_fifo():
    trades = extract_completed_trades({"equal_weight": _portfolio()})
    assert len(trades) == 1
    assert trades[0]["pnl_eur"] == 10.0 and trades[0]["shares"] == 1


def test_payload_and_render_roundtrip():
    payload = build_payload({"equal_weight": _portfolio()}, {}, {})
    s = payload["strategies"]["equal_weight"]
    assert s["metrics"]["n_days"] == 3
    assert s["positions"][0]["ticker"] == "AAPL"

    html = _render(payload)
    assert "__DATA__" not in html
    match = re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S)
    assert json.loads(match.group(1))["generated_at"] == payload["generated_at"]


def test_render_escapes_script_terminator():
    payload = build_payload({}, {}, {})
    payload["note"] = "</script><b>x</b>"
    assert "</script><b>" not in _render(payload)
