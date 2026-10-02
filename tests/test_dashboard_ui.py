"""Protegge la struttura della dashboard: il polish grafico non deve cambiare
sezioni, ordine, tab e funzionalita' (vedi README: "stessa dashboard, rifinita")."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import dashboard_generator as dg  # noqa: E402

SECTIONS = [
    "Strategy Overview",
    "Performance Comparison",
    "Stock Screener",
    "Portfolio Details",
    "Completed Trades",
]
STRATEGIES = ["equal_weight", "momentum", "fundamental", "sentiment"]


def _portfolio(name):
    log = [
        {
            "timestamp": f"2026-07-0{d}T10:00:00+00:00",
            "total_value_eur": 3000.0 + d * 10,
            "current_cash": 100.0,
            "prices_used": {"AAPL": 200.0},
            "transactions": (
                [{"action": "BUY", "ticker": "AAPL", "shares": 1, "price_eur": 100.0}]
                if d == 1
                else [{"action": "SELL", "ticker": "AAPL", "shares": 1, "price_eur": 110.0}]
                if d == 2
                else []
            ),
        }
        for d in range(1, 5)
    ]
    return {
        "strategy": name,
        "metadata": {"initial_capital": 3000.0, "current_cash": 100.0},
        "current_positions": {"AAPL": {"shares": 2, "avg_price": 150.0}},
        "iterations_log": log,
    }


def _html():
    return dg.build_html({n: _portfolio(n) for n in STRATEGIES}, {"sentiment": {}})


def test_sections_present_in_original_order():
    titles = re.findall(r'<div class="section-title">(.*?)</div>', _html())
    assert titles == SECTIONS


def test_four_strategy_cards_and_tabs_with_working_js_hook():
    html = _html()
    assert html.count('class="strategy-card"') == 4
    for s in STRATEGIES:
        assert f'id="btn-{s}"' in html and f'id="panel-{s}"' in html
        assert f"showTab('{s}')" in html
    assert "function showTab(name)" in html
    assert html.count('class="tab-btn active"') == 1
    assert html.count('class="tab-panel active"') == 1


def test_tables_keep_their_columns():
    html = _html()
    for col in ["Ticker", "Exchange", "Sector", "Mom 3m", "F-Score", "Sentiment", "Composite"]:
        assert f">{col}</th>" in html or f'">{col}</th>' in html
    for col in ["Shares", "Avg", "Cur", "Equity", "PnL", "PnL%"]:
        assert f'">{col}</th>' in html
    for col in ["Strategia", "Data Entrata", "Data Uscita", "Prezzo In (€)", "Prezzo Out (€)"]:
        assert f">{col}</th>" in html or f'">{col}</th>' in html


def test_responsive_and_self_contained():
    html = _html()
    assert 'name="viewport"' in html
    assert "@media(max-width:768px)" in html
    # nessuna risorsa esterna: la pagina resta un singolo file per GitHub Pages
    assert not re.search(r'(src|href)="https?://(?!github\.com)', html)
    assert "@import" not in html
