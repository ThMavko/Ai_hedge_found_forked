import pytest

from signals_utils import enrich_signals, merge_fundamentals, momentum_from_history

UNIVERSE = {"AAA": {}, "BBB": {}}


def _history(first, mid, last):
    return {
        "AAA": {"2026-01-01": first, "2026-03-02": mid, "2026-04-01": last},
        "BBB": {"2026-04-01": 10.0},  # un solo punto: non calcolabile
    }


def test_momentum_from_history_returns():
    m = momentum_from_history(_history(100.0, 110.0, 121.0), UNIVERSE)
    assert "BBB" not in m
    # storico di 3 mesi esatti: 91 giorni prima del 1/4 e' il 1/1 -> 121/100
    assert m["AAA"]["return_3m"] == pytest.approx(0.21)
    assert m["AAA"]["return_1m"] == pytest.approx(121 / 110 - 1, abs=1e-3)


def test_momentum_requires_minimum_span():
    short = {"AAA": {"2026-03-20": 100.0, "2026-04-01": 110.0}}
    assert momentum_from_history(short, UNIVERSE) == {}


def test_enrich_replaces_placeholders_but_keeps_real_values():
    signals = {
        "momentum": {
            "AAA": {"return_3m": 0.0, "return_1m": 0.0},
            "BBB": {"return_3m": 0.5, "return_1m": 0.1},
        },
        "fundamentals": {"AAA": {"f_score": 0.5}},
        "sentiment": {"AAA": {"num_articles": 3}},
    }
    out = enrich_signals(signals, _history(100.0, 110.0, 121.0), UNIVERSE)
    assert out["momentum"]["AAA"]["return_3m"] == pytest.approx(0.21)
    assert out["momentum"]["BBB"]["return_3m"] == 0.5
    assert out["status"]["fundamentals_real"] is False
    assert out["status"]["sentiment_real"] is True
    assert signals["momentum"]["AAA"]["return_3m"] == 0.0  # input non mutato


def test_merge_fundamentals_does_not_clobber_real_data():
    old = {"AAA": {"f_score": 0.8, "roe": 0.2}, "BBB": {"f_score": 0.5}}
    new = {"AAA": {"f_score": 0.5}, "BBB": {"f_score": 0.6, "roe": 0.1}}
    merged = merge_fundamentals(new, old)
    assert merged["AAA"] == old["AAA"]
    assert merged["BBB"] == new["BBB"]
