"""Test di integrazione sulla logica di trading, con I/O reindirizzato su una cartella temporanea."""

import pytest

import main_pipeline as mp
import portfolio_io

UNIVERSE = {
    "AAA": {"exchange": "NASDAQ", "currency": "USD", "sector": "Tech"},
    "BBB.MI": {"exchange": "BIT", "currency": "EUR", "sector": "Energy"},
}
FX = {"USD": 0.5, "EUR": 1.0}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio_io, "PORTFOLIOS_DIR", str(tmp_path))
    monkeypatch.setattr(mp, "UNIVERSE", UNIVERSE)
    monkeypatch.setattr(mp, "TRANSACTION_COST_BPS", 100.0)  # 1% per rendere i costi visibili


def run(prices, failed=frozenset()):
    return mp.run_strategy_pipeline("equal_weight", "mattina", prices, FX, {}, set(failed))


def test_first_run_buys_and_charges_fees():
    r = run({"AAA": 100.0, "BBB.MI": 50.0})
    assert r["has_trades"]
    fees = sum(t["fee_eur"] for t in r["transactions"])
    assert fees > 0
    p = r["portfolio"]
    assert p["metadata"]["current_cash"] >= 0
    assert p["metadata"]["fees_paid"] == pytest.approx(fees, abs=1e-3)
    # il totale e' il capitale iniziale meno i costi (prezzi invariati), a meno di arrotondamenti
    assert r["total_value_eur"] == pytest.approx(3000.0 - fees, abs=1.0)


def test_missing_price_does_not_collapse_portfolio_value():
    # Regressione: dopo i trade i titoli senza prezzo venivano valorizzati 0 EUR.
    first = run({"AAA": 100.0, "BBB.MI": 50.0})
    second = run({"AAA": 100.0}, failed={"BBB.MI"})
    assert second["total_value_eur"] == pytest.approx(first["total_value_eur"], rel=0.01)


def test_all_prices_missing_keeps_value_and_does_not_trade():
    first = run({"AAA": 100.0, "BBB.MI": 50.0})
    second = run({}, failed={"AAA", "BBB.MI"})
    assert not second["has_trades"]
    assert second["total_value_eur"] == pytest.approx(first["total_value_eur"], rel=0.01)


def test_iteration_log_records_fx_and_stale_tickers():
    r = run({"AAA": 100.0}, failed={"BBB.MI"})
    entry = r["portfolio"]["iterations_log"][-1]
    assert entry["fx_rates"]["USD"] == 0.5
    assert entry["stale_tickers"] == ["BBB.MI"]
