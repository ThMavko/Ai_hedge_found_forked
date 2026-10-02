import pytest

from valuation import last_known_prices, mark_to_market

UNIVERSE = {
    "AAA": {"currency": "USD"},
    "BBB.MI": {"currency": "EUR"},
    "CCC.L": {"currency": "GBp"},
}
FX = {"USD": 0.9, "EUR": 1.0}


def _portfolio():
    return {
        "metadata": {"current_cash": 50.0},
        "current_positions": {
            "AAA": {"shares": 2, "avg_price": 8.0},
            "BBB.MI": {"shares": 10, "avg_price": 4.0},
        },
        "iterations_log": [{"prices_used": {"BBB.MI": 5.0, "AAA": 11.0}}],
    }


def test_last_known_prices_takes_latest_positive():
    p = _portfolio()
    p["iterations_log"].append({"prices_used": {"AAA": 12.0, "BBB.MI": 0}})
    assert last_known_prices(p) == {"AAA": 12.0, "BBB.MI": 5.0}


def test_mark_to_market_live_prices():
    total, values = mark_to_market(_portfolio(), {"AAA": 10.0, "BBB.MI": 6.0}, FX, UNIVERSE)
    assert values == {"AAA": pytest.approx(18.0), "BBB.MI": pytest.approx(60.0)}
    assert total == pytest.approx(128.0)


def test_missing_price_falls_back_to_last_known_not_zero():
    total, values = mark_to_market(_portfolio(), {"AAA": 10.0}, FX, UNIVERSE)
    assert values["BBB.MI"] == pytest.approx(50.0)  # 10 x ultimo prezzo noto (5.0)
    assert total == pytest.approx(50 + 18 + 50)


def test_no_history_falls_back_to_cost_basis():
    p = _portfolio()
    p["iterations_log"] = []
    _, values = mark_to_market(p, {}, FX, UNIVERSE)
    assert values["BBB.MI"] == pytest.approx(40.0)
    assert values["AAA"] == pytest.approx(16.0)


def test_stale_ticker_ignores_live_price():
    _, values = mark_to_market(
        _portfolio(), {"AAA": 10.0, "BBB.MI": 999.0}, FX, UNIVERSE, stale={"BBB.MI"}
    )
    assert values["BBB.MI"] == pytest.approx(50.0)
