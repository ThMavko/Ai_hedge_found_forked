"""
Serie di equity e metriche di performance (modulo puro, senza I/O ne' dipendenze).

Differenze rispetto alla vecchia `_compute_metrics` di dashboard_generator:
  * i rendimenti sono calcolati su base *giornaliera* (ultimo valore del giorno),
    non tra una sessione e l'altra (3 al giorno);
  * l'annualizzazione e' geometrica sui giorni di calendario trascorsi, non
    `rendimento_totale / n_iterazioni * 252`;
  * Sharpe e Sortino sottraggono il tasso risk-free;
  * la serie viene ricostruita dove il portafoglio era sottovalutato per prezzi mancanti.
"""

import math
from datetime import datetime

TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Equity series (con riparazione dei prezzi mancanti)
# ---------------------------------------------------------------------------


def _price_on_or_before(days: dict, day: str):
    """Ultimo prezzo storico con data <= day, altrimenti il primo successivo."""
    if not days:
        return None
    earlier = [d for d in days if d <= day]
    if earlier:
        return days[max(earlier)]
    return days[min(days)]


def fx_rate(ccy: str, day: str, entry_fx: dict | None, price_history: dict, fallback: dict) -> float:
    """Cambio verso EUR: dalla voce di log, poi dallo storico FX, poi dal fallback statico."""
    if ccy == "EUR":
        return 1.0
    if ccy == "GBp":
        return fx_rate("GBP", day, entry_fx, price_history, fallback) / 100.0
    if entry_fx and entry_fx.get(ccy):
        return entry_fx[ccy]
    hist = _price_on_or_before(price_history.get(f"FX:{ccy}", {}), day)
    return hist if hist else fallback.get(ccy, 1.0)


def build_equity_series(
    history: list,
    price_history: dict | None = None,
    universe: dict | None = None,
    fx_fallback: dict | None = None,
) -> list:
    """Converte `iterations_log` in [{timestamp, date, value, repaired}].

    Ogni voce viene rivalutata da zero: cassa + sum(quantita' x prezzo x cambio).
    Questo corregge due problemi storici del totale registrato:
      * titoli senza prezzo contati 0 EUR (crolli artificiali di centinaia di euro);
      * cambio USD/GBP instabile: quando Alpha Vantage non rispondeva si usava un
        fallback statico (0.92) invece del tasso reale, gonfiando le posizioni USA.
    Prezzo: quello usato nella voce, altrimenti la chiusura storica del giorno, altrimenti
    l'ultimo noto, altrimenti il prezzo di carico. Cambio: quello registrato nella voce,
    altrimenti lo storico FX del giorno, altrimenti il fallback statico.
    `repaired` e' True se il valore ricalcolato differisce di oltre 1 EUR da quello
    registrato. I dati grezzi del portafoglio non vengono modificati.
    """
    price_history = price_history or {}
    universe = universe or {}
    fx_fallback = fx_fallback or {"EUR": 1.0}

    series = []
    last_local: dict[str, float] = {}
    for entry in history:
        ts = entry.get("timestamp", "")
        day = ts[:10]
        used = entry.get("prices_used", {}) or {}
        entry_fx = entry.get("fx_rates")
        recorded = float(entry.get("total_value_eur", 0.0))

        value = float(entry.get("current_cash", 0.0))
        for ticker, pos in (entry.get("positions") or {}).items():
            shares = pos.get("shares", 0)
            local = used.get(ticker)
            if not local:
                local = _price_on_or_before(price_history.get(ticker, {}), day)
            if not local:
                local = last_local.get(ticker)
            ccy = universe.get(ticker, {}).get("currency", "EUR")
            if local:
                value += shares * local * fx_rate(ccy, day, entry_fx, price_history, fx_fallback)
            else:
                value += shares * pos.get("avg_price", 0.0)

        for ticker, price in used.items():
            if price and price > 0:
                last_local[ticker] = price
        series.append(
            {
                "timestamp": ts,
                "date": day,
                "value": round(value, 2),
                "repaired": abs(value - recorded) > 1.0,
            }
        )
    return series


def daily_series(series: list) -> list:
    """Un punto per giorno: l'ultimo valore registrato. Ritorna [(date_str, value)]."""
    by_day: dict[str, float] = {}
    for p in series:
        by_day[p["date"]] = p["value"]
    return sorted(by_day.items())


# ---------------------------------------------------------------------------
# Metriche
# ---------------------------------------------------------------------------


def daily_returns(values: list) -> list:
    """Rendimenti semplici (frazioni, non percentuali) tra valori consecutivi."""
    return [
        values[i] / values[i - 1] - 1.0
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]


def max_drawdown(daily: list) -> tuple:
    """(max drawdown come frazione positiva, data picco, data minimo)."""
    peak_v, peak_d = None, None
    worst, w_peak, w_trough = 0.0, None, None
    for d, v in daily:
        if peak_v is None or v > peak_v:
            peak_v, peak_d = v, d
        dd = (peak_v - v) / peak_v if peak_v else 0.0
        if dd > worst:
            worst, w_peak, w_trough = dd, peak_d, d
    return worst, w_peak, w_trough


def drawdown_series(daily: list) -> list:
    """[(date, drawdown)] con drawdown <= 0, rispetto al massimo corrente."""
    out, peak = [], None
    for d, v in daily:
        peak = v if peak is None or v > peak else peak
        out.append((d, (v / peak - 1.0) if peak else 0.0))
    return out


def _std(xs: list) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def compute_metrics(daily: list, risk_free: float = 0.0) -> dict:
    """Metriche su serie giornaliera [(date, value)]. Rendimenti in frazioni."""
    if len(daily) < 2:
        v = daily[0][1] if daily else 0.0
        return {"initial": v, "final": v, "total_return": 0.0, "n_days": len(daily)}

    dates = [d for d, _ in daily]
    values = [v for _, v in daily]
    initial, final = values[0], values[-1]
    total_return = final / initial - 1.0 if initial > 0 else 0.0

    d0 = datetime.strptime(dates[0], "%Y-%m-%d").date()
    d1 = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    calendar_days = max((d1 - d0).days, 1)
    # Annualizzazione composta; con storici brevi e' solo indicativa.
    ann_return = (
        (1.0 + total_return) ** (365.0 / calendar_days) - 1.0 if total_return > -1 else -1.0
    )

    rets = daily_returns(values)
    rf_daily = risk_free / TRADING_DAYS
    excess = [r - rf_daily for r in rets]
    ann_vol = _std(rets) * math.sqrt(TRADING_DAYS)
    ex_std = _std(excess)
    sharpe = (sum(excess) / len(excess)) / ex_std * math.sqrt(TRADING_DAYS) if ex_std > 0 else 0.0

    downside = [min(0.0, r - rf_daily) for r in rets]
    dd_dev = math.sqrt(sum(x * x for x in downside) / len(downside)) if downside else 0.0
    sortino = (sum(excess) / len(excess)) / dd_dev * math.sqrt(TRADING_DAYS) if dd_dev > 0 else 0.0

    mdd, mdd_peak, mdd_trough = max_drawdown(daily)
    cur_dd = drawdown_series(daily)[-1][1]
    calmar = ann_return / mdd if mdd > 0 else 0.0

    gains = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    profit_factor = (sum(gains) / abs(sum(losses))) if losses else None

    return {
        "initial": initial,
        "final": final,
        "total_return": total_return,
        "ann_return": ann_return,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "max_drawdown_peak": mdd_peak,
        "max_drawdown_trough": mdd_trough,
        "current_drawdown": cur_dd,
        "calmar": calmar,
        "win_rate": len(gains) / len(rets) if rets else 0.0,
        "profit_factor": profit_factor,
        "best_day": max(rets) if rets else 0.0,
        "worst_day": min(rets) if rets else 0.0,
        "last_day_return": rets[-1] if rets else 0.0,
        "n_days": len(daily),
        "calendar_days": calendar_days,
    }


def rebase(daily: list, base: float = 100.0) -> list:
    """Serie normalizzata: primo valore = base."""
    if not daily or daily[0][1] <= 0:
        return list(daily)
    first = daily[0][1]
    return [(d, v / first * base) for d, v in daily]
