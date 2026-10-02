# Paper Trading Quant Platform

Piattaforma di paper trading multi-mercato e **multi-strategia** con capitale iniziale di **3.000 € per strategia**, su **NASDAQ**, **NYSE**, **FTSE** e **Borsa Italiana (BIT)**. Gira su GitHub Actions (3 sessioni al giorno), notifica su Telegram e pubblica una dashboard interattiva su GitHub Pages.

> Simulazione a scopo didattico. Non è consulenza finanziaria.

---

## Strategie

Ogni strategia ha un portafoglio indipendente in `data/portfolios/<strategia>.json`.

| Strategia | Logica |
|---|---|
| `equal_weight` | Pesi uguali su tutti i 20 titoli |
| `momentum` | Top 10 per rendimento a 3 mesi, pesi uguali |
| `fundamental` | Pesi proporzionali all'F-score (P/E, ROE, FCF yield, D/E) |
| `sentiment` | Pesi in base allo score di sentiment (Alpha Vantage + FinBERT) |

`momentum` viene calcolato dallo **storico prezzi locale** (`data/price_history.json`), quindi non dipende da Yahoo Finance. Se i dati fondamentali non sono disponibili, `fundamental` usa una lista fissa di fallback e la dashboard lo segnala.

---

## Architettura

| Componente | Ruolo |
|---|---|
| `scripts/main_pipeline.py` | Orchestratore: prezzi, FX, ordini, report, dashboard |
| `scripts/valuation.py` | Valorizzazione del portafoglio; un prezzo mancante usa l'ultimo noto, mai 0 € |
| `scripts/metrics.py` | Ricostruzione dell'equity e metriche (Sharpe, Sortino, drawdown, Calmar…) |
| `scripts/price_history.py` | Storico prezzi/FX/benchmark (`data/price_history.json`), additivo |
| `scripts/signals_utils.py` | Momentum da storico, stato dei segnali, merge non distruttivo |
| `scripts/dashboard_data.py` | Costruisce il payload JSON della dashboard |
| `scripts/dashboard_generator.py` | Scrive `docs/index.html` e `docs/data.json` |
| `scripts/templates/dashboard.html` | Template della dashboard (Plotly) |
| `scripts/backfill_history.py` | Backfill locale di prezzi, FX e benchmark |
| `scripts/telegram_utils.py` | Notifiche Telegram |
| `web/` | Dashboard live opzionali (Flask su Render, Streamlit) |

### Flusso di una sessione

1. GitHub Actions avvia il workflow (mattina / pomeriggio / sera, lun-ven).
2. Prezzi: **Tiingo** (USA) → **Alpha Vantage** (Europa) → **yfinance**, con cache giornaliera.
3. Cambi: **Frankfurter** (BCE, gratuito) → Alpha Vantage → fallback statico.
4. Ogni strategia calcola i pesi target e ribilancia (soglia 5%, lotti interi, costi simulati).
5. Si aggiornano lo storico prezzi e i benchmark, poi si salvano portafogli, report Telegram e dashboard.
6. Il bot committa i file aggiornati.

### Gestione del rischio e realismo

- **Soglia di ribilanciamento 5%**: nessun ordine se lo scostamento dal peso target è inferiore.
- **Lotti interi**: nessuna frazione di azione.
- **Costi di transazione**: `TRANSACTION_COST_BPS` in `scripts/config.py` (default 10 bps su ogni ordine). Sono registrati in `fee_eur` per ogni transazione e in `metadata.fees_paid`. Valgono solo per i nuovi trade.
- **Prezzi mancanti**: i titoli senza prezzo non vengono scambiati e restano valorizzati all'ultimo prezzo noto.

---

## Dashboard

`docs/index.html` è una pagina autosufficiente (dati incorporati, grafici Plotly da CDN): si apre anche da file locale. Contiene:

- **KPI** per strategia e per benchmark (MSCI World in EUR via `SWDA.MI`, S&P 500 via `SPY`);
- **Equity curve interattiva** in Base 100, in valore € o come drawdown;
- **Confronto metriche**: rendimento, annualizzato, volatilità, Sharpe, Sortino, max drawdown, Calmar, % giorni positivi, costi;
- **Portafoglio** per strategia: allocazione, esposizione per settore, posizioni con P&L;
- **Screener** (momentum, F-score, sentiment, punteggio composito);
- **Trade conclusi** con filtro per strategia;
- tema chiaro/scuro e layout mobile.

Le stesse informazioni sono in `docs/data.json`. Per GitHub Pages: Settings → Pages → sorgente `docs/`.

### Nota sui dati storici

Fino al 30/09/2026 i 5 titoli di Borsa Italiana risultavano spesso senza prezzo e venivano contati **0 €** nel totale, e quando Alpha Vantage non rispondeva il cambio USD/EUR cadeva su un fallback statico (0,92 contro ~0,89 reale). Il totale registrato nei JSON ha quindi falsi crolli e picchi. Il codice ora corregge il problema in avanti (`valuation.py`, FX affidabile) e la dashboard **ricostruisce** l'equity storica con i prezzi e i cambi reali (`metrics.build_equity_series`). I file in `data/portfolios/` non vengono mai modificati.

---

## Setup

### Prerequisiti

- Python 3.10+
- API key per [Tiingo](https://www.tiingo.com/), [Alpha Vantage](https://www.alphavantage.co/) e un bot [Telegram](https://core.telegram.org/bots#6-botfather)

### GitHub Secrets

| Secret | Descrizione |
|---|---|
| `TIINGO_API_KEY` | Prezzi azionari USA e benchmark |
| `ALPHA_VANTAGE_KEY` | Prezzi europei, sentiment, FX di riserva |
| `TELEGRAM_TOKEN` | Token del bot |
| `TELEGRAM_CHAT_ID` | Chat di destinazione |

### Esecuzione locale

```bash
pip install -r requirements.txt

# Una sessione (7 = mattina, 15 = pomeriggio, 21 = sera)
python scripts/main_pipeline.py --hour 21

# Backfill di prezzi, FX e benchmark (richiede accesso a Yahoo Finance)
python scripts/backfill_history.py --start 2026-06-01

# Dati fondamentali e momentum
python scripts/fetch_fundamentals.py
```

### Test e lint

```bash
pip install -r requirements-test.txt
ruff check scripts tests
pytest -q
```

La CI (`.github/workflows/ci.yml`) esegue gli stessi controlli su ogni pull request.

---

## Universo dei ticker

- **NASDAQ**: AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA
- **NYSE**: JPM, JNJ, V, KO
- **FTSE**: ULVR.L, HSBA.L, BP.L, GSK.L, RIO.L
- **Borsa Italiana**: ENI.MI, ISP.MI, ENEL.MI, LDO.MI, MONC.MI

## Manutenzione

- **Modificare i ticker o i parametri**: `scripts/config.py` (`UNIVERSE`, `TRANSACTION_COST_BPS`, `RISK_FREE_RATE`, `BENCHMARKS`).
- **Cambiare gli orari**: cron in `.github/workflows/paper_trading.yml`.
- **Reset di una strategia**: sostituire `data/portfolios/<strategia>.json` con un portafoglio iniziale (storico escluso dal reset: `data/price_history.json` si mantiene).
