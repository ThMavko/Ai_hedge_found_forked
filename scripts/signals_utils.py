"""
Utilita' sui segnali (data/signals.json).

Problema storico: fetch_fundamentals.py scriveva valori neutri (f_score 0.5, momentum 0.0)
ogni volta che Yahoo Finance falliva, quindi le strategie Momentum e Fundamental giravano
su dati finti senza che nessuno se ne accorgesse. Qui:
  * il momentum viene calcolato dallo storico prezzi locale (nessuna dipendenza da Yahoo);
  * si espone lo stato dei segnali (reale vs placeholder) per mostrarlo in dashboard.
"""

from datetime import datetime, timedelta

_NEUTRAL_F_SCORE = 0.5


def _on_or_before(days: dict, target: str):
    earlier = [d for d in days if d <= target]
    return days[max(earlier)] if earlier else None


def momentum_from_history(price_history: dict, universe: dict, min_span_days: int = 45) -> dict:
    """{ticker: {return_3m, return_1m}} dallo storico prezzi (stessa valuta, quindi niente FX).

    Se lo storico copre meno di 3 mesi si usa il primo prezzo disponibile, purche' lo storico
    copra almeno `min_span_days`; altrimenti il ticker viene omesso.
    """
    out = {}
    for ticker in universe:
        days = price_history.get(ticker) or {}
        if len(days) < 2:
            continue
        ordered = sorted(days)
        last_day, first_day = ordered[-1], ordered[0]
        last_dt = datetime.strptime(last_day, "%Y-%m-%d")
        span = (last_dt - datetime.strptime(first_day, "%Y-%m-%d")).days
        if span < min_span_days:
            continue
        now = days[last_day]
        p3 = _on_or_before(days, (last_dt - timedelta(days=91)).strftime("%Y-%m-%d")) or days[first_day]
        p1 = _on_or_before(days, (last_dt - timedelta(days=30)).strftime("%Y-%m-%d")) or days[first_day]
        if p3 > 0 and p1 > 0:
            out[ticker] = {
                "return_3m": round(now / p3 - 1.0, 4),
                "return_1m": round(now / p1 - 1.0, 4),
            }
    return out


def _is_placeholder_momentum(entry: dict | None) -> bool:
    return not entry or (not entry.get("return_3m") and not entry.get("return_1m"))


def enrich_signals(signals: dict, price_history: dict, universe: dict) -> dict:
    """Copia dei segnali con il momentum reale al posto dei placeholder, piu' `status`."""
    enriched = dict(signals)
    momentum = dict(signals.get("momentum", {}))
    computed = momentum_from_history(price_history, universe)
    filled = 0
    for ticker, values in computed.items():
        if _is_placeholder_momentum(momentum.get(ticker)):
            momentum[ticker] = values
            filled += 1
    enriched["momentum"] = momentum

    fundamentals = signals.get("fundamentals", {})
    fundamentals_real = any(
        v.get("f_score") not in (None, _NEUTRAL_F_SCORE) for v in fundamentals.values()
    )
    sentiment_real = any(v.get("num_articles", 0) > 0 for v in signals.get("sentiment", {}).values())
    momentum_real = any(not _is_placeholder_momentum(v) for v in momentum.values())
    enriched["status"] = {
        "fundamentals_real": fundamentals_real,
        "sentiment_real": sentiment_real,
        "momentum_real": momentum_real,
        "momentum_from_history": filled,
    }
    return enriched


def merge_fundamentals(new: dict, old: dict) -> dict:
    """Non sovrascrive dati reali precedenti con placeholder (fetch fallito)."""
    merged = {}
    for ticker, entry in new.items():
        is_placeholder = set(entry) <= {"f_score"} and entry.get("f_score") == _NEUTRAL_F_SCORE
        previous = old.get(ticker)
        if is_placeholder and previous and previous.get("f_score") not in (None, _NEUTRAL_F_SCORE):
            merged[ticker] = previous
        else:
            merged[ticker] = entry
    return merged
