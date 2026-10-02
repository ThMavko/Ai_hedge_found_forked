import pytest

from config import UNIVERSE
from strategies import (
    EqualWeightStrategy,
    FundamentalStrategy,
    InverseVolatilityStrategy,
    MomentumStrategy,
    SentimentStrategy,
    TrendMomentumStrategy,
)

ALL = [
    EqualWeightStrategy,
    MomentumStrategy,
    FundamentalStrategy,
    SentimentStrategy,
    InverseVolatilityStrategy,
    TrendMomentumStrategy,
]


def _signals(universe):
    tickers = list(universe)
    return {
        "momentum": {t: {"return_3m": i / 100} for i, t in enumerate(tickers)},
        "fundamentals": {t: {"f_score": 0.4 + i / 100} for i, t in enumerate(tickers)},
        "sentiment": {
            t: {"score": 0.1 + i / 100, "num_articles": 10}
            for i, t in enumerate(tickers)
        },
        "volatility": {t: {"vol_60d": 0.1 + i / 50} for i, t in enumerate(tickers)},
        "trend": {t: {"above_ma200": True} for t in tickers},
    }


@pytest.mark.parametrize("cls", ALL)
def test_weights_sum_to_one_with_signals(cls):
    w = cls().compute_weights(UNIVERSE, {}, _signals(UNIVERSE))
    assert w
    assert sum(w.values()) == pytest.approx(1.0)
    assert all(0.0 <= x <= 1.0 for x in w.values())
    assert set(w) <= set(UNIVERSE)


@pytest.mark.parametrize("cls", ALL)
def test_weights_sum_to_one_without_signals(cls):
    w = cls().compute_weights(UNIVERSE, {}, {})
    assert sum(w.values()) == pytest.approx(1.0)


def test_equal_weight_empty_universe():
    assert EqualWeightStrategy().compute_weights({}, {}, {}) == {}


def test_momentum_picks_top_n_by_return():
    sig = _signals(UNIVERSE)
    w = MomentumStrategy().compute_weights(UNIVERSE, {}, sig)
    assert len(w) == MomentumStrategy.top_n
    best = sorted(sig["momentum"], key=lambda t: sig["momentum"][t]["return_3m"])[-10:]
    assert set(w) == set(best)


def test_inverse_volatility_prefers_low_vol():
    u = {"A": {}, "B": {}}
    sig = {"volatility": {"A": {"vol_60d": 0.1}, "B": {"vol_60d": 0.4}}}
    w = InverseVolatilityStrategy().compute_weights(u, {}, sig)
    assert w["A"] == pytest.approx(0.8)
    assert w["B"] == pytest.approx(0.2)


def test_trend_filter_excludes_tickers_below_ma200():
    u = {"A": {}, "B": {}, "C": {}}
    sig = {
        "momentum": {t: {"return_3m": r} for t, r in zip("ABC", (0.3, 0.2, 0.1))},
        "trend": {
            "A": {"above_ma200": False},
            "B": {"above_ma200": True},
            "C": {"above_ma200": True},
        },
    }
    w = TrendMomentumStrategy().compute_weights(u, {}, sig)
    assert set(w) == {"B", "C"}


def test_trend_momentum_goes_to_cash_when_all_below_ma200():
    u = {"A": {}, "B": {}}
    sig = {"trend": {"A": {"above_ma200": False}, "B": {"above_ma200": False}}}
    assert TrendMomentumStrategy().compute_weights(u, {}, sig) == {}


def test_fundamental_uses_fallback_without_real_scores():
    w = FundamentalStrategy().compute_weights(UNIVERSE, {}, {})
    assert len(w) == 10  # lista fallback, non equal-weight su tutto l'universo
