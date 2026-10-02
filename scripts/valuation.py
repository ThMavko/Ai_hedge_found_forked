"""
Valorizzazione del portafoglio (mark-to-market) con gestione dei prezzi mancanti.

Bug storico: dopo i trade il totale veniva ricalcolato con `prices.get(t, 0)`, quindi
ogni titolo senza prezzo valeva 0 EUR e l'equity crollava di centinaia di euro.
Qui un titolo senza prezzo live viene valorizzato all'ultimo prezzo noto
(dal log delle iterazioni) o, in mancanza, al prezzo medio di carico.
"""


def last_known_prices(portfolio: dict) -> dict:
    """Ultimo prezzo locale noto per ticker, dal log delle iterazioni."""
    last: dict[str, float] = {}
    for entry in portfolio.get("iterations_log", []):
        for ticker, price in entry.get("prices_used", {}).items():
            if price and price > 0:
                last[ticker] = price
    return last


def price_eur_for(
    ticker: str,
    prices: dict,
    fx_rates: dict,
    universe: dict,
    avg_price_eur: float,
    last_known: dict,
    stale: set | None = None,
) -> float:
    """Prezzo in EUR: live se disponibile, altrimenti ultimo noto, altrimenti costo."""
    fx = fx_rates.get(universe[ticker]["currency"], 1.0)
    live = prices.get(ticker)
    if live and ticker not in (stale or ()):
        return live * fx
    last = last_known.get(ticker)
    if last:
        return last * fx
    return avg_price_eur


def mark_to_market(
    portfolio: dict,
    prices: dict,
    fx_rates: dict,
    universe: dict,
    stale: set | None = None,
) -> tuple[float, dict]:
    """Ritorna (totale_EUR_inclusa_cassa, {ticker: valore_EUR})."""
    last_known = last_known_prices(portfolio)
    values: dict[str, float] = {}
    for ticker, pos in portfolio.get("current_positions", {}).items():
        if ticker not in universe:
            continue
        px = price_eur_for(
            ticker, prices, fx_rates, universe, pos.get("avg_price", 0.0), last_known, stale
        )
        values[ticker] = px * pos.get("shares", 0)
    total = portfolio["metadata"]["current_cash"] + sum(values.values())
    return total, values
