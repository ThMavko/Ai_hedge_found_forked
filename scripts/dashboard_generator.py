import os
import sys
import json
import math
import base64
import io
from datetime import datetime, timezone
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.dirname(__file__))

from metrics import history_metrics  # noqa: E402

DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "index.html")

STRATEGY_COLORS = {
    "equal_weight": "#22c55e",
    "momentum": "#3b82f6",
    "fundamental": "#f59e0b",
    "sentiment": "#a855f7",
}

STRATEGY_LABELS = {
    "equal_weight": "Equal Weight",
    "momentum": "Momentum",
    "fundamental": "Fundamental",
    "sentiment": "Sentiment",
}


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _calc_daily_returns(values: list) -> list:
    if len(values) < 2:
        return []
    return [
        (values[i] - values[i - 1]) / values[i - 1] * 100 for i in range(1, len(values))
    ]


def _calc_max_drawdown(values: list) -> float:
    if not values:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _compute_metrics(history: list) -> dict:
    return history_metrics(history)


# Colori dei grafici: allineati ai token CSS della pagina (stesso pannello, nessun "riquadro nel riquadro")
CHART_BG = "#131c31"
CHART_TEXT = "#8a99b3"
CHART_TITLE = "#e6ebf4"
CHART_GRID = "#26324a"


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=CHART_BG)
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return f"data:image/png;base64,{data}"


def _dark_ax(ax):
    """Apply dark theme to a matplotlib axes."""
    ax.set_facecolor(CHART_BG)
    ax.tick_params(colors=CHART_TEXT, labelsize=8, length=3, width=0.8)
    for side in ("bottom", "left"):
        ax.spines[side].set_color(CHART_GRID)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.5, color=CHART_GRID, linewidth=0.6, linestyle=(0, (3, 4)))
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"{v:,.0f}")


def _style_title(ax, text):
    ax.set_title(text, color=CHART_TITLE, fontsize=11, fontweight="bold",
                 loc="left", pad=12)


def _style_legend(ax, ncol=1):
    legend = ax.legend(loc="upper left", fontsize=8, frameon=False,
                       labelcolor="#cbd5e1", ncol=ncol, handlelength=1.6,
                       borderaxespad=0.2)
    return legend


# ---------------------------------------------------------------------------
# Chart generators
# ---------------------------------------------------------------------------

def _generate_equity_comparison_chart(portfolios: dict) -> str:
    """Multi-strategy equity curve comparison chart."""
    fig, ax = plt.subplots(figsize=(11, 3.5))
    has_data = False
    for sname, portfolio in portfolios.items():
        history = portfolio.get("iterations_log", [])
        if not history:
            continue
        timestamps = []
        values = []
        for e in history:
            try:
                timestamps.append(datetime.fromisoformat(e["timestamp"]))
                values.append(e["total_value_eur"])
            except (ValueError, KeyError):
                continue
        if timestamps:
            color = STRATEGY_COLORS.get(sname, "#94a3b8")
            label = STRATEGY_LABELS.get(sname, sname)
            ax.plot(timestamps, values, color=color, linewidth=1.6, label=label)
            has_data = True

    if not has_data:
        ax.text(0.5, 0.5, "No data yet — in attesa della prima sessione di trading",
                ha="center", va="center", transform=ax.transAxes, color=CHART_TEXT)

    _style_title(ax, "Strategy Performance Comparison")
    ax.set_ylabel("EUR", color=CHART_TEXT, fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    if has_data:
        _style_legend(ax, ncol=4)
    fig.patch.set_facecolor(CHART_BG)
    _dark_ax(ax)
    return _fig_to_b64(fig)


def _generate_single_equity_chart(portfolio: dict, strategy_name: str) -> str:
    """Single strategy equity + cash chart."""
    history = portfolio.get("iterations_log", [])
    color = STRATEGY_COLORS.get(strategy_name, "#22c55e")
    fig, ax = plt.subplots(figsize=(10, 3))
    if history:
        ts = []
        vals = []
        cash_vals = []
        for e in history:
            try:
                ts.append(datetime.fromisoformat(e["timestamp"]))
                vals.append(e["total_value_eur"])
                cash_vals.append(e.get("current_cash", 0))
            except (ValueError, KeyError):
                continue
        if ts:
            ax.plot(ts, vals, color=color, linewidth=1.6, label="Portfolio")
            ax.fill_between(ts, vals, alpha=0.1, color=color)
            ax.plot(ts, cash_vals, color="#64748b", linewidth=1, linestyle="--", label="Cash")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    _style_title(ax, f"Equity Curve — {STRATEGY_LABELS.get(strategy_name, strategy_name)}")
    ax.set_ylabel("EUR", color=CHART_TEXT, fontsize=8)
    _style_legend(ax, ncol=2)
    fig.patch.set_facecolor(CHART_BG)
    _dark_ax(ax)
    return _fig_to_b64(fig)


# ---------------------------------------------------------------------------
# HTML Section builders
# ---------------------------------------------------------------------------

def _build_strategy_cards(portfolios: dict) -> str:
    """4 strategy cards side by side."""
    cards = ""
    for sname in ["equal_weight", "momentum", "fundamental", "sentiment"]:
        portfolio = portfolios.get(sname, {})
        history = portfolio.get("iterations_log", [])
        metadata = portfolio.get("metadata", {})
        metrics = _compute_metrics(history)
        initial = metadata.get("initial_capital", 3000.0)
        total = metrics.get("final", metadata.get("current_cash", initial))
        ret_pct = metrics.get("total_return", 0.0)
        color = STRATEGY_COLORS.get(sname, "#22c55e")
        label = STRATEGY_LABELS.get(sname, sname)
        sign = "+" if ret_pct >= 0 else ""
        badge_cls = "badge-pos" if ret_pct >= 0 else "badge-neg"

        # daily change from last 2 entries
        values = metrics.get("values", [])
        daily_chg = 0.0
        if len(values) >= 2:
            daily_chg = (values[-1] - values[-2]) / values[-2] * 100 if values[-2] > 0 else 0
        daily_sign = "+" if daily_chg >= 0 else ""
        daily_cls = "pos" if daily_chg >= 0 else "neg"

        cards += f"""
        <div class="strategy-card" style="--c:{color};border-top:3px solid {color};">
          <div class="strat-name">{label}</div>
          <div class="strat-value">{total:.2f} EUR</div>
          <div class="strat-return {badge_cls}">{sign}{ret_pct:.2f}%</div>
          <div class="strat-daily {daily_cls}">1d: {daily_sign}{daily_chg:.2f}%</div>
        </div>"""
    return f'<div class="strategy-cards">{cards}</div>'


def _build_screener_table(signals: dict) -> str:
    """Stock screener table with composite scores."""
    try:
        from config import UNIVERSE
    except ImportError:
        return '<p class="empty">Screener unavailable (config not found)</p>'

    sentiment_data = signals.get("sentiment", {})
    fundamentals_data = signals.get("fundamentals", {})
    momentum_data = signals.get("momentum", {})

    rows_data = []
    for ticker, info in UNIVERSE.items():
        sent = sentiment_data.get(ticker, {})
        fund = fundamentals_data.get(ticker, {})
        mom = momentum_data.get(ticker, {})

        sent_score = sent.get("score", 0.0)      # [-1, 1]
        f_score = fund.get("f_score", 0.5)        # [0, 1]
        ret_3m = mom.get("return_3m", 0.0)        # float, e.g. 0.12 = 12%

        # Normalize momentum to [0, 1]: clamp to [-0.3, +0.3] range
        mom_norm = max(0.0, min(1.0, (ret_3m + 0.3) / 0.6))
        # Normalize sentiment from [-1,1] to [0,1]
        sent_norm = (sent_score + 1.0) / 2.0

        composite = 0.35 * sent_norm + 0.35 * f_score + 0.30 * mom_norm

        sent_label = sent.get("label", "Neutral")
        if sent_label.lower() == "bullish":
            sent_cls = "pos"
        elif sent_label.lower() == "bearish":
            sent_cls = "neg"
        else:
            sent_cls = "neutral-lbl"

        rows_data.append({
            "ticker": ticker,
            "exchange": info.get("exchange", ""),
            "sector": info.get("sector", ""),
            "ret_3m": ret_3m,
            "f_score": f_score,
            "sent_score": sent_score,
            "sent_label": sent_label,
            "sent_cls": sent_cls,
            "composite": composite,
        })

    rows_data.sort(key=lambda x: x["composite"], reverse=True)

    rows_html = ""
    for r in rows_data:
        ret_cls = "pos" if r["ret_3m"] >= 0 else "neg"
        comp_pct = int(r["composite"] * 100)
        comp_bar = f'<span class="bar bar-lg"><i class="bar-comp" style="width:{comp_pct}%"></i></span>'
        fscore_pct = int(r["f_score"] * 100)
        fscore_bar = f'<span class="bar"><i class="bar-fscore" style="width:{fscore_pct}%"></i></span>'
        ret_sign = "+" if r["ret_3m"] >= 0 else ""
        sent_sign = "+" if r["sent_score"] >= 0 else ""
        rows_html += f"""<tr>
          <td><strong>{r['ticker']}</strong></td>
          <td>{r['exchange']}</td>
          <td>{r['sector']}</td>
          <td class="{ret_cls} num">{ret_sign}{r['ret_3m']*100:.1f}%</td>
          <td>{fscore_bar} {r['f_score']:.2f}</td>
          <td class="{r['sent_cls']}">{sent_sign}{r['sent_score']:.3f} <small>{r['sent_label']}</small></td>
          <td>{comp_bar} {r['composite']:.3f}</td>
        </tr>"""

    return f"""
    <div class="table-scroll">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Exchange</th><th>Sector</th>
        <th class="num">Mom 3m</th><th>F-Score</th><th>Sentiment</th><th>Composite</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>"""


def _build_portfolio_tabs(portfolios: dict) -> str:
    """Tab-based portfolio detail for each strategy."""
    try:
        from config import UNIVERSE
    except ImportError:
        UNIVERSE = {}

    tab_buttons = ""
    tab_panels = ""

    strategy_order = ["equal_weight", "momentum", "fundamental", "sentiment"]
    for idx, sname in enumerate(strategy_order):
        portfolio = portfolios.get(sname, {})
        if not portfolio:
            continue
        label = STRATEGY_LABELS.get(sname, sname)
        active_btn = "tab-btn active" if idx == 0 else "tab-btn"
        active_panel = "tab-panel active" if idx == 0 else "tab-panel"

        history = portfolio.get("iterations_log", [])
        positions = portfolio.get("current_positions", {})
        last_prices = history[-1].get("prices_used", {}) if history else {}
        metadata = portfolio.get("metadata", {})

        # Generate equity chart
        chart_b64 = _generate_single_equity_chart(portfolio, sname)

        pos_rows = ""
        for ticker in sorted(positions.keys()):
            p = positions[ticker]
            info = UNIVERSE.get(ticker, {})
            cur_price_local = last_prices.get(ticker, p["avg_price"])
            ccy = info.get("currency", "EUR")
            fx = {"USD": 0.92, "GBP": 1.17, "GBp": 0.0117, "EUR": 1.0}.get(ccy, 1.0)
            cur_price_eur = cur_price_local * fx
            eq = p["shares"] * cur_price_eur
            cost = p["shares"] * p["avg_price"]
            pnl_e = eq - cost
            pnl_p = ((cur_price_eur / p["avg_price"]) - 1) * 100 if p["avg_price"] > 0 else 0
            pnl_cls = "pos" if pnl_e >= 0 else "neg"
            pos_rows += f"""<tr>
              <td><strong>{ticker}</strong></td>
              <td>{info.get('exchange', '')}</td>
              <td class="num">{p['shares']}</td>
              <td class="num">{p['avg_price']:.2f}</td>
              <td class="num">{cur_price_eur:.2f}</td>
              <td class="num">{eq:.2f}</td>
              <td class="{pnl_cls} num">{pnl_e:+.2f}</td>
              <td class="{pnl_cls} num">{pnl_p:+.2f}%</td>
            </tr>"""

        metrics = _compute_metrics(history)
        cash = metadata.get("current_cash", 0)
        total = metrics.get("final", cash)
        initial = metadata.get("initial_capital", 3000.0)
        ret_pct = metrics.get("total_return", 0.0)

        tab_buttons += f'<button class="{active_btn}" onclick="showTab(\'{sname}\')" id="btn-{sname}">{label}</button>'
        tab_panels += f"""
        <div class="{active_panel}" id="panel-{sname}">
          <div class="tab-summary">
            <span>Total: <strong>{total:.2f} EUR</strong></span>
            <span>Cash: <strong>{cash:.2f} EUR</strong></span>
            <span>Return: <strong class="{'pos' if ret_pct >= 0 else 'neg'}">{ret_pct:+.2f}%</strong></span>
            <span>Positions: <strong>{len(positions)}</strong></span>
          </div>
          <img class="tab-chart" src="{chart_b64}" alt="Equity {label}">
          {'<div class="table-scroll"><table><thead><tr><th>Ticker</th><th>Exc</th><th class="num">Shares</th><th class="num">Avg</th><th class="num">Cur</th><th class="num">Equity</th><th class="num">PnL</th><th class="num">PnL%</th></tr></thead><tbody>' + pos_rows + '</tbody></table></div>' if pos_rows else '<p class="empty">No positions yet.</p>'}
        </div>"""

    return f"""
    <div class="tabs">
      <div class="tab-buttons">{tab_buttons}</div>
      {tab_panels}
    </div>"""


# ---------------------------------------------------------------------------
# Trade history helpers
# ---------------------------------------------------------------------------

def _extract_completed_trades(portfolios: dict) -> list:
    """Match BUY/SELL pairs per strategy+ticker (FIFO) to build closed-trade list."""
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
                action = txn.get("action")

                if action == "BUY":
                    buy_queues.setdefault(ticker, []).append(
                        {"timestamp": ts, "shares": shares, "price_eur": price_eur}
                    )

                elif action == "SELL":
                    remaining = shares
                    queue = buy_queues.get(ticker, [])
                    while remaining > 0 and queue:
                        lot = queue[0]
                        matched = min(remaining, lot["shares"])
                        pnl_eur = matched * (price_eur - lot["price_eur"])
                        pnl_pct = (
                            (price_eur / lot["price_eur"] - 1) * 100
                            if lot["price_eur"] > 0 else 0
                        )
                        completed.append({
                            "strategy": sname,
                            "ticker": ticker,
                            "shares": matched,
                            "date_in": lot["timestamp"],
                            "date_out": ts,
                            "entry_eur": lot["price_eur"],
                            "exit_eur": price_eur,
                            "pnl_eur": pnl_eur,
                            "pnl_pct": pnl_pct,
                        })
                        lot["shares"] -= matched
                        remaining -= matched
                        if lot["shares"] <= 0:
                            queue.pop(0)

    completed.sort(key=lambda x: x["date_out"], reverse=True)
    return completed


def _build_trade_history_section(portfolios: dict) -> str:
    """HTML table of all completed roundtrip trades across all strategies."""
    trades = _extract_completed_trades(portfolios)

    if not trades:
        return '<p class="empty">Nessun trade concluso.</p>'

    total_pnl = sum(t["pnl_eur"] for t in trades)
    winning = [t for t in trades if t["pnl_eur"] > 0]
    losing = [t for t in trades if t["pnl_eur"] < 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0
    total_sign = "+" if total_pnl >= 0 else ""
    total_cls = "pos" if total_pnl >= 0 else "neg"

    _SCOL = {
        "equal_weight": "#22c55e", "momentum": "#3b82f6",
        "fundamental": "#f59e0b", "sentiment": "#a855f7",
    }
    _SLBL = {
        "equal_weight": "EqW", "momentum": "Mom",
        "fundamental": "Fun", "sentiment": "Sen",
    }

    rows = ""
    for t in trades:
        pnl_cls = "pos" if t["pnl_eur"] >= 0 else "neg"
        sign = "+" if t["pnl_eur"] >= 0 else ""
        sc = _SCOL.get(t["strategy"], "#94a3b8")
        sl = _SLBL.get(t["strategy"], t["strategy"])
        date_in = t["date_in"].strftime("%m/%d %H:%M")
        date_out = t["date_out"].strftime("%m/%d %H:%M")
        rows += f"""<tr>
          <td><span class="strat-tag" style="background:{sc}22;color:{sc}">{sl}</span></td>
          <td><strong>{t['ticker']}</strong></td>
          <td class="date">{date_in}</td>
          <td class="date">{date_out}</td>
          <td class="num">{t['shares']}</td>
          <td class="num">{t['entry_eur']:.2f}</td>
          <td class="num">{t['exit_eur']:.2f}</td>
          <td class="{pnl_cls} num strong">{sign}{t['pnl_eur']:.2f}</td>
          <td class="{pnl_cls} num">{sign}{t['pnl_pct']:.2f}%</td>
        </tr>"""

    return f"""
    <div class="trade-summary">
      <span>Trades: <strong>{len(trades)}</strong></span>
      <span>Win rate: <strong class="pos">{win_rate:.0f}%</strong></span>
      <span>Vincenti: <strong class="pos">{len(winning)}</strong></span>
      <span>Perdenti: <strong class="neg">{len(losing)}</strong></span>
      <span>P&amp;L totale: <strong class="{total_cls}">{total_sign}{total_pnl:.2f} €</strong></span>
    </div>
    <div class="table-scroll">
    <table>
      <thead><tr>
        <th>Strategia</th><th>Ticker</th><th>Data Entrata</th><th>Data Uscita</th>
        <th class="num">Q.tà</th>
        <th class="num">Prezzo In (€)</th>
        <th class="num">Prezzo Out (€)</th>
        <th class="num">P&amp;L €</th>
        <th class="num">P&amp;L %</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>"""


# ---------------------------------------------------------------------------
# Main HTML builder
# ---------------------------------------------------------------------------

def build_html(portfolios: dict, signals: dict = None) -> str:
    """
    Build the multi-portfolio HTML dashboard.
    portfolios: {strategy_name: portfolio_dict}
    signals: signals.json content (optional)
    """
    if signals is None:
        signals = {}

    try:
        from config import UNIVERSE
    except ImportError:
        UNIVERSE = {}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    signals_updated = signals.get("fundamentals_updated", "N/A")
    sentiment_updated = signals.get("sentiment_updated", "N/A")
    if signals_updated != "N/A":
        signals_updated = signals_updated[:16].replace("T", " ")
    if sentiment_updated != "N/A":
        sentiment_updated = sentiment_updated[:16].replace("T", " ")

    strategy_cards_html = _build_strategy_cards(portfolios)
    comparison_chart = _generate_equity_comparison_chart(portfolios)
    screener_html = _build_screener_table(signals)
    portfolio_tabs_html = _build_portfolio_tabs(portfolios)
    trade_history_html = _build_trade_history_section(portfolios)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Hedge Fund — Multi-Strategy Dashboard</title>
<style>
:root {{
  color-scheme: dark;
  --bg:#0a101e; --bg-2:#0f172a;
  --panel:#131c31; --panel-2:#17223a;
  --line:#26324a; --line-soft:#1c2740;
  --text:#e2e8f0; --text-strong:#f8fafc; --muted:#8a99b3; --faint:#64748b;
  --accent:#38bdf8; --pos:#22c55e; --neg:#ef4444;
  --radius:10px;
  --shadow:0 1px 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{
  font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  font-size:14px; line-height:1.5; color:var(--text);
  background:radial-gradient(900px 320px at 50% -120px,rgba(56,189,248,0.07),transparent 70%),var(--bg-2);
  background-color:var(--bg-2);
  -webkit-font-smoothing:antialiased; font-variant-numeric:tabular-nums;
}}
a {{ color:var(--accent); text-decoration:none; transition:color .15s; }}
a:hover {{ color:#7dd3fc; text-decoration:underline; }}
::selection {{ background:rgba(56,189,248,0.3); }}
* {{ scrollbar-width:thin; scrollbar-color:var(--line) transparent; }}
::-webkit-scrollbar {{ height:8px; width:8px; }}
::-webkit-scrollbar-thumb {{ background:var(--line); border-radius:8px; }}

.header {{ position:relative; background:linear-gradient(180deg,#18233b,var(--bg-2)); padding:26px 32px 22px; border-bottom:1px solid var(--line); }}
.header::before {{ content:""; position:absolute; inset:0 0 auto 0; height:2px;
  background:linear-gradient(90deg,#22c55e 0 25%,#3b82f6 25% 50%,#f59e0b 50% 75%,#a855f7 75% 100%); opacity:.85; }}
.header h1 {{ font-size:21px; font-weight:650; letter-spacing:-0.01em; color:var(--text-strong); }}
.header .sub {{ color:var(--muted); font-size:12px; margin-top:8px; display:flex; gap:6px 22px; flex-wrap:wrap; }}
.header .sub strong {{ color:var(--text); font-weight:500; }}
.container {{ max-width:1280px; margin:0 auto; padding:8px 24px 24px; }}
.section-title {{ display:flex; align-items:center; gap:12px; font-size:12px; font-weight:650; margin:34px 0 14px; color:var(--text-strong);
  text-transform:uppercase; letter-spacing:0.12em; }}
.section-title::before {{ content:""; width:3px; height:15px; border-radius:2px; background:linear-gradient(180deg,var(--accent),#3b82f6); }}
.section-title::after {{ content:""; flex:1; height:1px; background:linear-gradient(90deg,var(--line),transparent); }}

/* Panels */
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); margin-bottom:28px; }}
.panel-flush {{ overflow:hidden; }}
.panel-pad {{ overflow:hidden; padding:20px; }}

/* Strategy cards */
.strategy-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; margin-bottom:28px; }}
.strategy-card {{ position:relative; background:linear-gradient(180deg,var(--panel-2),var(--panel)); border:1px solid var(--line); border-radius:var(--radius);
  padding:18px 18px 16px; box-shadow:var(--shadow); transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease; }}
.strategy-card:hover {{ transform:translateY(-2px); border-color:var(--c,var(--line)); box-shadow:0 12px 28px -14px var(--c,#000); }}
.strat-name {{ font-size:10.5px; font-weight:600; text-transform:uppercase; letter-spacing:0.14em; color:var(--muted); margin-bottom:10px; }}
.strat-value {{ font-size:25px; font-weight:650; letter-spacing:-0.02em; color:var(--text-strong); white-space:nowrap; line-height:1.15; }}
.strat-return {{ font-size:13px; font-weight:600; margin-top:10px; display:inline-block; padding:3px 9px; border-radius:6px; }}
.badge-pos {{ background:rgba(34,197,94,0.14); color:var(--pos); box-shadow:inset 0 0 0 1px rgba(34,197,94,0.25); }}
.badge-neg {{ background:rgba(239,68,68,0.14); color:var(--neg); box-shadow:inset 0 0 0 1px rgba(239,68,68,0.25); }}
.strat-daily {{ font-size:12px; margin-top:8px; color:var(--faint); }}

/* Comparison chart */
.chart-wrap {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); padding:16px 18px; margin-bottom:28px; overflow-x:auto; }}
.chart-wrap img {{ display:block; width:100%; height:auto; }}
.tab-chart {{ display:block; width:100%; height:auto; margin:14px 0; }}

/* Tables */
.table-scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ position:sticky; top:0; background:var(--panel-2); color:var(--muted); text-align:left; padding:10px 14px; font-weight:600; text-transform:uppercase;
  font-size:10px; letter-spacing:0.1em; border-bottom:1px solid var(--line); white-space:nowrap; }}
td {{ padding:9px 14px; border-bottom:1px solid var(--line-soft); white-space:nowrap; transition:background .12s; }}
tbody tr:last-child td {{ border-bottom:none; }}
td strong {{ font-weight:600; color:var(--text-strong); letter-spacing:0.01em; }}
tr:hover td {{ background:rgba(56,189,248,0.045); }}
th.num, td.num {{ text-align:right; }}
td.date {{ color:var(--muted); font-size:11.5px; }}
td.strong {{ font-weight:600; }}
td small {{ color:var(--muted); font-size:10.5px; margin-left:3px; }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .neutral-lbl {{ color:var(--muted); }}
.strat-tag {{ display:inline-block; padding:2px 8px; border-radius:5px; font-size:10px; font-weight:700; letter-spacing:0.06em; }}
.empty {{ color:var(--faint); padding:14px 0; font-size:13px; }}

/* Score bars */
.bar {{ display:inline-block; vertical-align:middle; width:60px; height:6px; margin-right:8px; background:#26324a; border-radius:6px; overflow:hidden; }}
.bar-lg {{ width:80px; }}
.bar i {{ display:block; height:100%; border-radius:6px; }}
.bar-fscore {{ background:linear-gradient(90deg,#d97706,#f59e0b); }}
.bar-comp {{ background:linear-gradient(90deg,#16a34a,#22c55e); }}

/* Tabs */
.tabs {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); box-shadow:var(--shadow); overflow:hidden; }}
.tab-buttons {{ display:flex; gap:0; background:var(--bg-2); border-bottom:1px solid var(--line); flex-wrap:wrap; padding:0 6px; }}
.tab-btn {{ background:transparent; border:none; color:var(--faint); padding:13px 18px; cursor:pointer; font:inherit; font-size:13px; font-weight:500; letter-spacing:0.01em;
  transition:color .15s,background .15s,border-color .15s; border-bottom:2px solid transparent; margin-bottom:-1px; }}
.tab-btn:hover {{ color:var(--text); background:rgba(148,163,184,0.06); }}
.tab-btn:focus-visible {{ outline:2px solid var(--accent); outline-offset:-2px; }}
.tab-btn.active {{ color:var(--text-strong); font-weight:600; border-bottom-color:var(--accent); }}
.tab-panel {{ display:none; padding:20px; }}
.tab-panel.active {{ display:block; }}
.tab-summary {{ display:flex; gap:8px 28px; flex-wrap:wrap; margin-bottom:6px; font-size:12px; color:var(--muted); }}
.tab-summary strong {{ color:var(--text-strong); font-weight:600; font-size:13px; margin-left:2px; }}
.tab-summary strong.pos {{ color:var(--pos); }} .tab-summary strong.neg {{ color:var(--neg); }}
.trade-summary {{ display:flex; gap:8px 28px; flex-wrap:wrap; font-size:12px; color:var(--muted); margin-bottom:16px; padding-bottom:14px; border-bottom:1px solid var(--line-soft); }}
.trade-summary strong {{ color:var(--text-strong); font-weight:600; font-size:13px; margin-left:2px; }}
.trade-summary strong.pos {{ color:var(--pos); }} .trade-summary strong.neg {{ color:var(--neg); }}
.panel-pad .table-scroll {{ margin:0 -20px -20px; }}

/* Footer */
.footer {{ text-align:center; padding:24px; color:var(--faint); font-size:11.5px; letter-spacing:0.02em; border-top:1px solid var(--line-soft); margin-top:28px; }}

@media(max-width:768px) {{
  .header {{ padding:20px 16px 16px; }}
  .header h1 {{ font-size:18px; }}
  .container {{ padding:4px 14px 20px; }}
  .strategy-cards {{ grid-template-columns:repeat(2,1fr); gap:10px; }}
  .strategy-card {{ padding:14px 12px 12px; }}
  .strat-value {{ font-size:18px; }}
  .strat-name {{ letter-spacing:0.1em; }}
  th, td {{ padding:8px 10px; }}
  .tab-btn {{ padding:12px 12px; }}
  .tab-panel {{ padding:14px; }}
  .chart-wrap {{ padding:10px; }}
  .chart-wrap img, .tab-chart {{ min-width:640px; }}
  .tab-panel .tab-chart {{ margin-right:0; }}
  .panel-pad {{ padding:14px; }}
  .panel-pad .table-scroll {{ margin:0 -14px -14px; }}
}}
@media(prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} .strategy-card:hover {{ transform:none; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>AI Hedge Fund &mdash; Multi-Strategy Paper Trading</h1>
  <div class="sub">
    <span>Updated: <strong>{now}</strong></span>
    <span>Signals: <strong>{signals_updated}</strong></span>
    <span>Sentiment: <strong>{sentiment_updated}</strong></span>
    <span>Exchanges: NASDAQ &middot; NYSE &middot; FTSE &middot; BIT</span>
  </div>
</div>

<div class="container">

  <div class="section-title">Strategy Overview</div>
  {strategy_cards_html}

  <div class="section-title">Performance Comparison</div>
  <div class="chart-wrap">
    <img src="{comparison_chart}" alt="Strategy Comparison">
  </div>

  <div class="section-title">Stock Screener</div>
  <div class="panel panel-flush">
    {screener_html}
  </div>

  <div class="section-title">Portfolio Details</div>
  {portfolio_tabs_html}

  <div class="section-title">Completed Trades</div>
  <div class="panel panel-pad">
    {trade_history_html}
  </div>

</div>

<div class="footer">
  <a href="https://github.com">GitHub</a> &middot;
  AI Hedge Fund Paper Trading &middot; {now}
</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  var panel = document.getElementById('panel-' + name);
  var btn = document.getElementById('btn-' + name);
  if (panel) panel.classList.add('active');
  if (btn) btn.classList.add('active');
}}
</script>
</body>
</html>"""
