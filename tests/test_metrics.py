import pytest

from metrics import (
    build_equity_series,
    compute_metrics,
    daily_returns,
    daily_series,
    drawdown_series,
    max_drawdown,
    rebase,
)

UNIVERSE = {
    "AAA": {"currency": "USD"},
    "BBB.MI": {"currency": "EUR"},
}


def test_daily_returns():
    assert daily_returns([100, 110, 99]) == pytest.approx([0.10, -0.10])


def test_max_drawdown_and_dates():
    daily = [("2026-01-01", 100), ("2026-01-02", 120), ("2026-01-03", 90), ("2026-01-04", 130)]
    mdd, peak, trough = max_drawdown(daily)
    assert mdd == pytest.approx(0.25)
    assert (peak, trough) == ("2026-01-02", "2026-01-03")
    assert drawdown_series(daily)[-1][1] == 0.0


def test_daily_series_keeps_last_value_of_each_day():
    # 3 rilevazioni al giorno non devono creare 3 rendimenti al giorno
    series = [
        {"date": "2026-01-01", "value": 100.0},
        {"date": "2026-01-01", "value": 100.0},
        {"date": "2026-01-01", "value": 101.0},
        {"date": "2026-01-02", "value": 102.0},
        {"date": "2026-01-02", "value": 102.0},
        {"date": "2026-01-02", "value": 103.02},
    ]
    daily = daily_series(series)
    assert daily == [("2026-01-01", 101.0), ("2026-01-02", 103.02)]
    m = compute_metrics(daily)
    assert m["total_return"] == pytest.approx(0.02)
    assert m["n_days"] == 2


def test_compute_metrics_handles_short_and_flat_series():
    assert compute_metrics([])["total_return"] == 0.0
    flat = [("2026-01-01", 100.0), ("2026-01-02", 100.0), ("2026-01-03", 100.0)]
    m = compute_metrics(flat, risk_free=0.02)
    assert m["sharpe"] == 0.0 and m["max_drawdown"] == 0.0


def test_risk_free_lowers_sharpe():
    values = [100, 101, 100.5, 102, 103]
    daily = [(f"2026-01-{d:02d}", v) for d, v in enumerate(values, start=1)]
    assert compute_metrics(daily, risk_free=0.05)["sharpe"] < compute_metrics(daily)["sharpe"]


def test_annualization_is_compound_over_calendar_days():
    daily = [("2026-01-01", 100.0), ("2026-01-02", 100.0), ("2026-04-02", 110.0)]
    m = compute_metrics(daily)
    assert m["ann_return"] == pytest.approx(1.10 ** (365 / 91) - 1)


def test_rebase():
    assert rebase([("a", 50.0), ("b", 75.0)]) == [("a", 100.0), ("b", 150.0)]


def _entry(day, cash, positions, prices, total, fx=None):
    e = {
        "timestamp": f"{day}T12:00:00+00:00",
        "current_cash": cash,
        "positions": positions,
        "prices_used": prices,
        "total_value_eur": total,
    }
    if fx:
        e["fx_rates"] = fx
    return e


def test_equity_series_values_missing_prices_instead_of_zero():
    # Regressione: titolo senza prezzo contato 0 EUR -> falso crollo dell'equity.
    positions = {"AAA": {"shares": 1, "avg_price": 9}, "BBB.MI": {"shares": 10, "avg_price": 5}}
    history = [
        _entry("2026-03-02", 100, positions, {"AAA": 10.0, "BBB.MI": 5.0}, 159.0, {"USD": 0.9}),
        # BBB.MI senza prezzo: il totale registrato perde 50 EUR
        _entry("2026-03-03", 100, positions, {"AAA": 10.0}, 109.0, {"USD": 0.9}),
    ]
    price_history = {"BBB.MI": {"2026-03-02": 5.0, "2026-03-03": 6.0}}
    series = build_equity_series(history, price_history, UNIVERSE, {"USD": 0.5, "EUR": 1.0})
    assert series[0]["value"] == pytest.approx(159.0)
    assert series[1]["value"] == pytest.approx(100 + 9 + 60)
    assert series[1]["repaired"] is True and series[0]["repaired"] is False


def test_equity_series_uses_historical_fx_not_static_fallback():
    positions = {"AAA": {"shares": 2, "avg_price": 9}}
    # totale registrato col fallback 0.92, ma il cambio storico del giorno e' 0.80
    history = [_entry("2026-03-02", 0, positions, {"AAA": 100.0}, 2 * 100 * 0.92)]
    ph = {"FX:USD": {"2026-03-02": 0.80}}
    series = build_equity_series(history, ph, UNIVERSE, {"USD": 0.92, "EUR": 1.0})
    assert series[0]["value"] == pytest.approx(160.0)
