"""Metriche di performance pure (nessun I/O), usate da backtest e test.

Convenzioni: i rendimenti sono frazioni (0.01 = 1%), 252 giorni di borsa/anno.
"""
import math

TRADING_DAYS = 252


def daily_returns(values: list[float]) -> list[float]:
    """Rendimenti semplici tra valori consecutivi di una equity curve."""
    return [
        values[i] / values[i - 1] - 1.0
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]


def total_return(values: list[float]) -> float:
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    return values[-1] / values[0] - 1.0


def cagr(values: list[float], periods_per_year: int = TRADING_DAYS) -> float:
    """Rendimento annualizzato composto. 0.0 se la serie e' troppo corta."""
    n = len(values) - 1
    if n < 1 or values[0] <= 0 or values[-1] <= 0:
        return 0.0
    return (values[-1] / values[0]) ** (periods_per_year / n) - 1.0


def annualized_vol(rets: list[float], periods_per_year: int = TRADING_DAYS) -> float:
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(periods_per_year)


def sharpe(
    rets: list[float], risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    """Sharpe annualizzato: media dei rendimenti in eccesso / dev. standard."""
    if len(rets) < 2:
        return 0.0
    rf = risk_free / periods_per_year
    excess = [r - rf for r in rets]
    vol = annualized_vol(excess, periods_per_year)
    if vol < 1e-12:  # serie costante: evita rapporti dominati dal rumore float
        return 0.0
    return (sum(excess) / len(excess)) * periods_per_year / vol


def sortino(
    rets: list[float], risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    """Come lo Sharpe ma penalizza solo la volatilita' al ribasso."""
    if len(rets) < 2:
        return 0.0
    rf = risk_free / periods_per_year
    excess = [r - rf for r in rets]
    downside = [min(0.0, r) for r in excess]
    dd = math.sqrt(sum(d * d for d in downside) / len(downside)) * math.sqrt(
        periods_per_year
    )
    if dd < 1e-12:
        return 0.0
    return (sum(excess) / len(excess)) * periods_per_year / dd


def max_drawdown(values: list[float]) -> float:
    """Massimo drawdown come frazione positiva (0.2 = -20% dal picco)."""
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst


def calmar(values: list[float], periods_per_year: int = TRADING_DAYS) -> float:
    mdd = max_drawdown(values)
    return cagr(values, periods_per_year) / mdd if mdd > 0 else 0.0


def summarize(values: list[float], risk_free: float = 0.0) -> dict[str, float]:
    """Tutte le metriche in un dict, pronto per tabelle e JSON."""
    rets = daily_returns(values)
    return {
        "total_return": total_return(values),
        "cagr": cagr(values),
        "volatility": annualized_vol(rets),
        "sharpe": sharpe(rets, risk_free),
        "sortino": sortino(rets, risk_free),
        "max_drawdown": max_drawdown(values),
        "calmar": calmar(values),
    }


def collapse_to_daily(history: list[dict]) -> list[float]:
    """Una valutazione per giorno (l'ultima): il live registra ~3 iterazioni al
    giorno, e trattarle come "giorni" falserebbe annualizzazione e Sharpe."""
    by_day: dict[str, float] = {}
    for i, entry in enumerate(history):
        # senza timestamp ogni voce vale come un giorno a se'
        day = str(entry.get("timestamp", i))[:10]
        by_day[day] = entry["total_value_eur"]
    return list(by_day.values())


def history_metrics(history: list[dict]) -> dict:
    """Metriche per le dashboard a partire da `iterations_log`.

    Percentuali espresse in punti percentuali (12.5 = 12.5%), come si aspettano
    i template HTML. Le metriche di rischio usano un valore per giorno; `values`
    resta la serie completa per i grafici.
    """
    if not history:
        return {}
    values = [e["total_value_eur"] for e in history]
    daily = collapse_to_daily(history)
    rets = daily_returns(daily)
    gains = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    mdd = max_drawdown(daily)
    ann = cagr(daily)
    return {
        "total_return": total_return(values) * 100,
        "ann_return": ann * 100,
        "ann_vol": annualized_vol(rets) * 100,
        "sharpe": sharpe(rets),
        "sortino": sortino(rets),
        "max_drawdown": mdd * 100,
        "calmar": ann / mdd if mdd > 0 else 0.0,
        "win_rate": len(gains) / len(rets) * 100 if rets else 0.0,
        "profit_factor": abs(sum(gains) / sum(losses)) if losses else float("inf"),
        "n_entries": len(values),
        "n_days": len(daily),
        "initial": values[0],
        "final": values[-1],
        "daily_rets": [r * 100 for r in rets],
        "values": values,
    }
