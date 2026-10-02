"""
Costruisce il payload JSON che alimenta la dashboard (docs/index.html + docs/data.json).

Tutta la logica numerica sta qui (e in metrics.py); l'HTML si limita a disegnare.
"""

from datetime import date, datetime, timezone

from config import (
    BENCHMARKS,
    FX_FALLBACK,
    RISK_FREE_RATE,
    STRATEGIES,
    STRATEGY_LABELS,
    UNIVERSE,
)
from metrics import (
    build_equity_series,
    compute_metrics,
    daily_series,
    drawdown_series,
    fx_rate,
)
from valuation import last_known_prices

# Colori distinti dai semantici positivo/negativo (verde/rosso) e dall'accento del brand.
STRATEGY_COLORS = {
    "equal_weight": "#0ea5e9",
    "momentum": "#8b5cf6",
    "fundamental": "#f59e0b",
    "sentiment": "#ec4899",
}


def extract_completed_trades(portfolios: dict) -> list:
    """Accoppia BUY/SELL (FIFO) per strategia+ticker e ritorna i round-trip chiusi."""
    completed = []
    for sname, portfolio in portfolios.items():
        buy_queues: dict[str, list] = {}
        for entry in portfolio.get("iterations_log", []):
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
            except (ValueError, KeyError):
                continue
            for txn in entry.get("transactions", []):
                ticker = txn.get("ticker")
                shares = txn.get("shares", 0)
                price_eur = txn.get("price_eur", 0)
                if txn.get("action") == "BUY":
                    buy_queues.setdefault(ticker, []).append(
                        {"timestamp": ts, "shares": shares, "price_eur": price_eur}
                    )
                elif txn.get("action") == "SELL":
                    remaining = shares
                    queue = buy_queues.get(ticker, [])
                    while remaining > 0 and queue:
                        lot = queue[0]
                        matched = min(remaining, lot["shares"])
                        completed.append(
                            {
                                "strategy": sname,
                                "ticker": ticker,
                                "shares": matched,
                                "date_in": lot["timestamp"].isoformat(),
                                "date_out": ts.isoformat(),
                                "entry_eur": round(lot["price_eur"], 4),
                                "exit_eur": round(price_eur, 4),
                                "pnl_eur": round(matched * (price_eur - lot["price_eur"]), 2),
                                "pnl_pct": round(
                                    (price_eur / lot["price_eur"] - 1) * 100
                                    if lot["price_eur"] > 0
                                    else 0.0,
                                    2,
                                ),
                            }
                        )
                        lot["shares"] -= matched
                        remaining -= matched
                        if lot["shares"] <= 0:
                            queue.pop(0)
    completed.sort(key=lambda t: t["date_out"], reverse=True)
    return completed


def _screener_rows(signals: dict) -> list:
    sentiment = signals.get("sentiment", {})
    fundamentals = signals.get("fundamentals", {})
    momentum = signals.get("momentum", {})
    rows = []
    for ticker, info in UNIVERSE.items():
        sent = sentiment.get(ticker, {})
        sent_score = sent.get("score", 0.0)
        f_score = fundamentals.get(ticker, {}).get("f_score", 0.5)
        ret_3m = momentum.get(ticker, {}).get("return_3m", 0.0)
        mom_norm = max(0.0, min(1.0, (ret_3m + 0.3) / 0.6))
        composite = 0.35 * (sent_score + 1.0) / 2.0 + 0.35 * f_score + 0.30 * mom_norm
        rows.append(
            {
                "ticker": ticker,
                "exchange": info.get("exchange", ""),
                "sector": info.get("sector", ""),
                "ret_3m": ret_3m,
                "f_score": f_score,
                "sent_score": sent_score,
                "sent_label": sent.get("label", "Neutral"),
                "composite": round(composite, 4),
            }
        )
    rows.sort(key=lambda r: r["composite"], reverse=True)
    return rows


def _positions(portfolio: dict, price_history: dict, live_prices: dict | None = None) -> list:
    history = portfolio.get("iterations_log", [])
    last = history[-1] if history else {}
    live_prices = live_prices or {}
    # Con prezzi live si usa il cambio piu' recente dello storico, non quello dell'ultima voce.
    day = str(date.today()) if live_prices else last.get("timestamp", "")[:10]
    entry_fx = None if live_prices else last.get("fx_rates")
    used = last.get("prices_used", {}) or {}
    last_known = last_known_prices(portfolio)

    rows = []
    for ticker, pos in sorted(portfolio.get("current_positions", {}).items()):
        info = UNIVERSE.get(ticker, {})
        ccy = info.get("currency", "EUR")
        fx = fx_rate(ccy, day, entry_fx, price_history, FX_FALLBACK)
        live = live_prices.get(ticker) or 0.0
        local = live or used.get(ticker) or last_known.get(ticker)
        price_eur = local * fx if local else pos["avg_price"]
        value = price_eur * pos["shares"]
        cost = pos["avg_price"] * pos["shares"]
        rows.append(
            {
                "ticker": ticker,
                "exchange": info.get("exchange", ""),
                "sector": info.get("sector", ""),
                "shares": pos["shares"],
                "avg_price": round(pos["avg_price"], 4),
                "price_eur": round(price_eur, 4),
                "value": round(value, 2),
                "pnl": round(value - cost, 2),
                "pnl_pct": round((price_eur / pos["avg_price"] - 1) * 100, 2)
                if pos["avg_price"] > 0
                else 0.0,
                "stale": not live and ticker not in used,
                "live": bool(live),
            }
        )
    return rows


def _benchmarks(price_history: dict, start_day: str) -> dict:
    out = {}
    for ticker, label in BENCHMARKS.items():
        days = price_history.get(ticker, {})
        series = [[d, p] for d, p in sorted(days.items()) if d >= start_day]
        if len(series) >= 2:
            out[ticker] = {
                "label": label,
                "series": series,
                "metrics": compute_metrics([(d, p) for d, p in series], RISK_FREE_RATE),
            }
    return out


def build_payload(
    portfolios: dict,
    signals: dict | None = None,
    price_history: dict | None = None,
    live_prices: dict | None = None,
) -> dict:
    """live_prices: {ticker: prezzo in valuta locale}, opzionale (dashboard Flask)."""
    signals = signals or {}
    price_history = price_history or {}

    strategies = {}
    all_days = []
    for sname in STRATEGIES:
        portfolio = portfolios.get(sname)
        if not portfolio:
            continue
        history = portfolio.get("iterations_log", [])
        series = build_equity_series(history, price_history, UNIVERSE, FX_FALLBACK)
        daily = daily_series(series)
        if not daily:
            continue
        all_days.append(daily[0][0])
        metrics = compute_metrics(daily, RISK_FREE_RATE)
        meta = portfolio.get("metadata", {})
        meta_cash = meta.get("current_cash", 0.0)
        positions = _positions(portfolio, price_history, live_prices)
        live_total = meta_cash + sum(p["value"] for p in positions)
        for p in positions:
            p["weight"] = round(p["value"] / live_total, 4) if live_total > 0 else 0.0
        is_live = any(p["live"] for p in positions)
        strategies[sname] = {
            "label": STRATEGY_LABELS.get(sname, sname),
            "color": STRATEGY_COLORS.get(sname, "#94a3b8"),
            "equity": [[d, v] for d, v in daily],
            "drawdown": [[d, round(v * 100, 3)] for d, v in drawdown_series(daily)],
            "metrics": metrics,
            "cash": round(meta.get("current_cash", 0.0), 2),
            "initial_capital": meta.get("initial_capital", 3000.0),
            "fees_paid": round(meta.get("fees_paid", 0.0), 2),
            "positions": positions,
            "live_value": round(live_total, 2) if is_live else None,
            "repaired_points": sum(1 for p in series if p["repaired"]),
            "iterations": len(history),
            "last_update": history[-1]["timestamp"] if history else None,
        }

    start_day = min(all_days) if all_days else "1970-01-01"
    trades = extract_completed_trades(portfolios)
    wins = [t for t in trades if t["pnl_eur"] > 0]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "signals_updated": (signals.get("fundamentals_updated") or "N/A")[:16].replace("T", " "),
        "sentiment_updated": (signals.get("sentiment_updated") or "N/A")[:16].replace("T", " "),
        "risk_free": RISK_FREE_RATE,
        "strategies": strategies,
        "benchmarks": _benchmarks(price_history, start_day),
        "screener": _screener_rows(signals),
        "trades": trades,
        "trades_summary": {
            "count": len(trades),
            "wins": len(wins),
            "losses": sum(1 for t in trades if t["pnl_eur"] < 0),
            "pnl": round(sum(t["pnl_eur"] for t in trades), 2),
        },
        "data_quality": {
            "repaired_points": sum(s["repaired_points"] for s in strategies.values()),
            "signals": signals.get("status", {}),
        },
    }
