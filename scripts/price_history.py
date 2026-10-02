"""
Storico dei prezzi di chiusura giornalieri (prezzo locale, nella valuta del titolo).

Salvato in data/price_history.json come {ticker: {"YYYY-MM-DD": close}}.
Serve a due cose:
  1. ricostruire in modo non distruttivo i valori di portafoglio storici quando
     alcuni prezzi mancavano (vedi metrics.build_equity_series);
  2. confrontare le strategie con i benchmark.

Il file e' additivo: i valori gia' presenti non vengono mai cancellati.
"""

import json
import os
from datetime import date

PRICE_HISTORY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "price_history.json"
)


def load_price_history(path: str = PRICE_HISTORY_PATH) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_price_history(history: dict, path: str = PRICE_HISTORY_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ordered = {t: dict(sorted(days.items())) for t, days in sorted(history.items())}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, indent=1, ensure_ascii=False)
        f.write("\n")


def record_prices(prices: dict, day: str | None = None, path: str = PRICE_HISTORY_PATH) -> None:
    """Registra i prezzi reali di oggi (l'ultimo valore del giorno vince)."""
    if not prices:
        return
    day = day or str(date.today())
    history = load_price_history(path)
    for ticker, price in prices.items():
        history.setdefault(ticker, {})[day] = round(float(price), 6)
    save_price_history(history, path)


def fetch_yfinance_history(tickers: list[str], start: str) -> dict:
    """Scarica le chiusure giornaliere da Yahoo Finance. Best-effort: {} se fallisce."""
    try:
        import yfinance as yf

        raw = yf.download(
            tickers, start=start, auto_adjust=True, progress=False, threads=False
        )
    except Exception as e:  # rete, rate-limit, import
        print(f"[WARN] price history download failed: {e}")
        return {}
    if raw is None or raw.empty:
        return {}
    close = raw["Close"] if "Close" in raw.columns else raw
    out: dict[str, dict[str, float]] = {}
    if len(tickers) == 1 and not hasattr(close, "columns"):
        close = close.to_frame(tickers[0])
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        series = close[ticker].dropna()
        out[ticker] = {d.strftime("%Y-%m-%d"): round(float(v), 6) for d, v in series.items()}
    return out


def merge_into_history(fetched: dict, path: str = PRICE_HISTORY_PATH) -> int:
    """Unisce {ticker: {data: prezzo}} allo storico senza sovrascrivere. Ritorna i punti nuovi."""
    history = load_price_history(path)
    added = 0
    for ticker, days in fetched.items():
        known = history.setdefault(ticker, {})
        for d, v in days.items():
            if d not in known:
                known[d] = v
                added += 1
    if added:
        save_price_history(history, path)
    return added


def update_price_history(tickers: list[str], start: str, path: str = PRICE_HISTORY_PATH) -> int:
    """Aggiunge allo storico i prezzi scaricati, senza sovrascrivere quelli esistenti."""
    return merge_into_history(fetch_yfinance_history(tickers, start), path)


def update_fx_history(fx_tickers: dict, start: str, path: str = PRICE_HISTORY_PATH) -> int:
    """fx_tickers = {"USD": "USDEUR=X", ...} -> salva con chiave "FX:USD" (tasso verso EUR)."""
    fetched = fetch_yfinance_history(list(fx_tickers.values()), start)
    renamed = {f"FX:{ccy}": fetched[sym] for ccy, sym in fx_tickers.items() if sym in fetched}
    return merge_into_history(renamed, path)


def record_fx(fx_rates: dict, day: str | None = None, path: str = PRICE_HISTORY_PATH) -> None:
    """Registra gli FX di oggi (solo valute non-EUR, GBp escluso: derivato da GBP)."""
    day = day or str(date.today())
    record_prices(
        {f"FX:{c}": r for c, r in fx_rates.items() if c not in ("EUR", "GBp") and r},
        day,
        path,
    )


# ---------------------------------------------------------------------------
# Benchmark: Yahoo -> Tiingo (ticker USA) / Alpha Vantage (ticker europei)
# ---------------------------------------------------------------------------


def _fetch_tiingo_history(ticker: str, start: str) -> dict:
    key = os.getenv("TIINGO_API_KEY", "")
    if not key:
        return {}
    try:
        import requests

        resp = requests.get(
            f"https://api.tiingo.com/tiingo/daily/{ticker}/prices",
            params={"startDate": start, "token": key},
            timeout=20,
        )
        if resp.status_code != 200:
            return {}
        return {
            row["date"][:10]: round(float(row.get("adjClose") or row["close"]), 6)
            for row in resp.json()
        }
    except Exception as e:
        print(f"[WARN] Tiingo history failed for {ticker}: {e}")
        return {}


def _fetch_alpha_vantage_history(ticker: str) -> dict:
    key = os.getenv("ALPHA_VANTAGE_KEY", "")
    if not key:
        return {}
    symbol = ticker.replace(".MI", ".MIL").replace(".L", ".LON")
    try:
        import requests

        resp = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": "compact",
                "apikey": key,
            },
            timeout=20,
        )
        series = resp.json().get("Time Series (Daily)", {})
        return {d: round(float(v["4. close"]), 6) for d, v in series.items()}
    except Exception as e:
        print(f"[WARN] Alpha Vantage history failed for {ticker}: {e}")
        return {}


def refresh_benchmarks(
    benchmarks: list[str], default_start: str, path: str = PRICE_HISTORY_PATH
) -> int:
    """Aggiorna lo storico dei benchmark. Non solleva mai eccezioni. Ritorna i punti aggiunti."""
    today = str(date.today())
    history = load_price_history(path)
    stale = [t for t in benchmarks if max(history.get(t, {"": 0}), default="") < today]
    if not stale:
        return 0

    starts = {t: max(history.get(t, {default_start: 0}), default=default_start) for t in stale}
    fetched = fetch_yfinance_history(stale, min(starts.values()))
    for ticker in stale:
        if fetched.get(ticker):
            continue
        if "." not in ticker:
            fetched[ticker] = _fetch_tiingo_history(ticker, starts[ticker])
        if not fetched.get(ticker):
            fetched[ticker] = _fetch_alpha_vantage_history(ticker)

    added = 0
    for ticker, days in fetched.items():
        known = history.setdefault(ticker, {})
        for d, v in days.items():
            if d not in known:
                known[d] = v
                added += 1
    if added:
        save_price_history(history, path)
    return added
