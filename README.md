# AI Hedge Fund — Paper Trading Quant Platform

Piattaforma di paper trading multi-strategia con capitale iniziale di **3.000 €** per strategia,
su 20 titoli di **NASDAQ**, **NYSE**, **FTSE** e **Borsa Italiana**. Gira su GitHub Actions
(nessun server) e notifica su Telegram. Nessun denaro reale è coinvolto.

## Strategie

Tutte implementano `BaseStrategy.compute_weights(universe, prices, signals) -> {ticker: peso}`.

| Strategia | Idea | Segnali usati | Live |
|---|---|---|:-:|
| `equal_weight` | 1/N su tutto l'universo | – | ✅ |
| `momentum` | top 10 per rendimento a 3 mesi | `momentum.return_3m` | ✅ |
| `fundamental` | pesi proporzionali all'F-score (P/E, ROE, FCF, D/E) | `fundamentals.f_score` | ✅ |
| `sentiment` | pesi da sentiment news (Alpha Vantage + FinBERT) | `sentiment.score` | ✅ |
| `trend_momentum` | momentum, ma solo sopra la media mobile a 200gg; altrimenti cassa | `momentum`, `trend` | solo backtest |
| `inverse_volatility` | peso ∝ 1/volatilità (risk-parity semplificato) | `volatility.vol_60d` | solo backtest |

Le ultime due sono disponibili nel codice e nel backtest, ma non sono ancora registrate in
`STRATEGIES` (`scripts/config.py`): farlo crea un nuovo portafoglio live e va deciso consapevolmente.
Aggiungere una strategia = una classe in `scripts/strategies/` + export in `__init__.py`.

## Architettura

| File | Ruolo |
|---|---|
| `scripts/main_pipeline.py` | Orchestratore: prezzi, FX, ordini per strategia, report |
| `scripts/fetch_prices.py` | Prezzi: Tiingo (US) → Alpha Vantage (EU) → yfinance, con cache giornaliera |
| `scripts/fetch_fundamentals.py`, `fetch_sentiment.py` | Calcolo segnali → `data/signals.json` |
| `scripts/portfolio_io.py` | Lettura/scrittura dei portafogli JSON in `data/portfolios/` |
| `scripts/market_note.py` | Nota di mercato nel report Telegram (vedi sotto) |
| `scripts/metrics.py` | Metriche di performance (Sharpe, Sortino, drawdown, CAGR, Calmar) |
| `scripts/backtest.py` | Backtest storico con benchmark |
| `scripts/dashboard_generator.py`, `web/` | Dashboard HTML statica (`docs/`) e app Streamlit/Flask |

### Workflow

- `paper_trading.yml` — 3 sessioni al giorno nei giorni feriali; committa i JSON aggiornati.
- `market_analysis.yml` — ogni mattina aggiorna `data/signals.json` (fondamentali, momentum, sentiment).
- `backtest.yml` — manuale o mensile: rigenera `docs/backtest.{md,json,png}`.
- `ci.yml` — su ogni push/PR: `ruff` + `pytest`.

### Regole di esecuzione ordini

1. Peso target dalla strategia → valore target in EUR.
2. **Filtro anti-costi**: nessun ordine se lo scostamento dal target è < 5% del portafoglio.
3. **Lotti interi**: acquisti/vendite arrotondati per difetto a un numero intero di azioni.
4. I prezzi USD/GBP/GBp sono convertiti in EUR con il cambio live.
5. Se il prezzo di un titolo non è disponibile (fallback), per quel titolo il trading è sospeso.

## Backtest

```bash
pip install -r requirements-dev.txt
python scripts/backtest.py --years 5          # scrive docs/backtest.{md,json,png}
```

Confronta le strategie con **SPY** e **FTSE MIB** (buy & hold), in EUR, con ribilanciamento
mensile e costi di transazione (default 10 bps sul turnover).

Limiti dichiarati:

- Sono testate solo le strategie con segnali ricostruibili dai prezzi *point-in-time*
  (`equal_weight`, `momentum`, `trend_momentum`, `inverse_volatility`). `fundamental` e `sentiment`
  non hanno uno storico gratuito affidabile: includerle darebbe look-ahead bias.
- Azioni frazionarie (il live usa lotti interi), cassa a rendimento zero, nessuna imposta.
- Il paniere è quello attuale (survivorship bias).

I risultati dell'ultima esecuzione sono in [`docs/backtest.md`](docs/backtest.md), se già generati.

## Nota di mercato su Telegram

Il report include una breve nota con migliore/peggiore strategia, operazioni del giorno,
sentiment e momentum più forti. **Di default è un template deterministico: nessuna AI, nessuna API
key, nessun costo.**

Opzionale: farla riscrivere da un LLM con un endpoint compatibile OpenAI (anche locale, es. Ollama).
Si attiva solo se sono impostate `LLM_BASE_URL` e `LLM_MODEL` (`LLM_API_KEY` solo se serve).
Se l'LLM non risponde, si torna al template.

## Setup

### Secret GitHub

| Secret | Uso | Obbligatorio |
|---|---|:-:|
| `TIINGO_API_KEY` | prezzi US (free tier) | consigliato |
| `ALPHA_VANTAGE_KEY` | prezzi EU, FX, news sentiment (free tier) | consigliato |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | notifiche | no |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | nota riscritta da LLM | no |

### Esecuzione locale

```bash
pip install -r requirements.txt        # include torch/transformers per FinBERT
export TIINGO_API_KEY=... ALPHA_VANTAGE_KEY=... TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=...
python scripts/main_pipeline.py --hour 7     # 7 = mattina, 15 = pomeriggio, 21 = sera
```

### Sviluppo

```bash
pip install -r requirements-dev.txt    # leggero: niente torch
ruff check scripts tests
pytest
```

I test coprono pesi delle strategie, metriche, motore di backtest (incluso l'assenza di look-ahead
nei segnali), regole di esecuzione ordini e nota di mercato.

### Dashboard

`docs/index.html` è generata a ogni sessione. Per pubblicarla: Settings → Pages → sorgente `docs/`.

## Universo

NASDAQ: AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA · NYSE: JPM, JNJ, V, KO ·
FTSE: ULVR.L, HSBA.L, BP.L, GSK.L, RIO.L · BIT: ENI.MI, ISP.MI, ENEL.MI, LDO.MI, MONC.MI

Si modifica in `scripts/config.py` (`UNIVERSE`).

## Manutenzione

- **Reset di una strategia**: elimina `data/portfolios/<strategia>.json` (riparte da 3.000 €).
- **Orari**: cron in `.github/workflows/paper_trading.yml` (UTC, non seguono l'ora legale).
