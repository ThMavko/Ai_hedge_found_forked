"""Storico prezzi ricostruito dai log delle iterazioni + segnali derivati.

Perche' esiste: su GitHub Actions Yahoo Finance blocca le richieste, quindi i
segnali calcolati con yfinance (momentum, fondamentali) restano vuoti. I prezzi
reali pero' ci sono: ogni sessione li scrive in `iterations_log[*].prices_used`.
Da li' si ricostruisce una serie giornaliera, senza chiamate di rete, senza
nuove chiavi API e senza nuovi file da versionare.

I prezzi sono in valuta locale: i rendimenti ignorano quindi la componente FX.
"""
import glob
import json
import math
import os

PORTFOLIOS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "portfolios")

TRADING_DAYS = 252
MOMENTUM_3M = 63
MOMENTUM_1M = 21
VOL_WINDOW = 60
TREND_WINDOW = 200
MIN_OBS = 10  # sotto questa soglia nessun segnale: meglio nessun dato che dati finti

# Valori usati dalla pipeline come prezzo "nominale" quando il fetch fallisce
_PLACEHOLDERS = {100.0, 150.0}


def _is_placeholder_day(prices: dict) -> bool:
    vals = [v for v in prices.values() if v and v > 0]
    if not vals:
        return True
    return sum(1 for v in vals if v in _PLACEHOLDERS) / len(vals) >= 0.5


def load_history(portfolios_dir: str = PORTFOLIOS_DIR) -> dict[str, list[tuple[str, float]]]:
    """{ticker: [(YYYY-MM-DD, prezzo), ...]} ordinato, un valore per giorno
    (l'ultimo registrato). Scarta i giorni con prezzi nominali di fallback."""
    per_day: dict[str, dict[str, tuple[str, float]]] = {}
    for path in sorted(glob.glob(os.path.join(portfolios_dir, "*.json"))):
        try:
            with open(path) as f:
                log = json.load(f).get("iterations_log", [])
        except (OSError, json.JSONDecodeError):
            continue
        for entry in log:
            prices = entry.get("prices_used") or {}
            ts = entry.get("timestamp", "")
            if not ts or _is_placeholder_day(prices):
                continue
            day = ts[:10]
            for ticker, price in prices.items():
                if not price or price <= 0:
                    continue
                cur = per_day.setdefault(ticker, {}).get(day)
                if cur is None or ts >= cur[0]:
                    per_day[ticker][day] = (ts, float(price))
    return {
        t: sorted((d, v[1]) for d, v in days.items()) for t, days in per_day.items()
    }


def latest_prices(history: dict[str, list[tuple[str, float]]]) -> dict[str, float]:
    """Ultimo prezzo reale noto (valuta locale) per ticker."""
    return {t: series[-1][1] for t, series in history.items() if series}


def compute_price_signals(history: dict[str, list[tuple[str, float]]]) -> dict:
    """Segnali dai soli prezzi. Un ticker senza abbastanza storico viene OMESSO
    dal segnale (mai riempito con 0.0), cosi' le strategie sanno che manca."""
    momentum: dict = {}
    volatility: dict = {}
    trend: dict = {}
    for ticker, series in history.items():
        px = [p for _, p in series]
        n = len(px)
        if n < MIN_OBS:
            continue
        entry = {"n_obs": n, "source": "price_history"}
        if n > MOMENTUM_1M:
            entry["return_1m"] = round(px[-1] / px[-1 - MOMENTUM_1M] - 1.0, 4)
        if n > MOMENTUM_3M:
            entry["return_3m"] = round(px[-1] / px[-1 - MOMENTUM_3M] - 1.0, 4)
        if "return_3m" in entry:
            momentum[ticker] = entry

        rets = [px[i] / px[i - 1] - 1.0 for i in range(1, n)]
        window = rets[-VOL_WINDOW:]
        if len(window) >= 20:
            mean = sum(window) / len(window)
            var = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
            volatility[ticker] = {"vol_60d": round(math.sqrt(var * TRADING_DAYS), 4)}

        if n >= TREND_WINDOW:
            ma = sum(px[-TREND_WINDOW:]) / TREND_WINDOW
            trend[ticker] = {"above_ma200": px[-1] > ma}
    return {"momentum": momentum, "volatility": volatility, "trend": trend}
