# NEPSE Insight AI

A personal research tool for the Nepal Stock Exchange. It takes daily price and volume
data (plus fundamentals where I have them), trains an XGBoost model on it, and gives a
BUY / SELL / HOLD / NO TRADE call for each stock along with the reasons behind it.

It does not place trades. The output is meant to support my own decisions, nothing more.

## Status

Work in progress.

- The backend (FastAPI + PostgreSQL + XGBoost) works end to end.
- There is no real NEPSE data source hooked up yet. `seed-demo` loads generated prices
  so the pipeline can be tested. Those rows are stored with `source=synthetic`. Don't
  read anything into signals produced from them.
- The Vue frontend still runs its own in-browser simulation and isn't connected to the
  API yet.

## Stack

| Part     | Tech                                             |
|----------|--------------------------------------------------|
| API      | FastAPI, SQLAlchemy 2, Pydantic 2                |
| Database | PostgreSQL 16 (Docker)                           |
| Model    | XGBoost 3, scikit-learn, pandas                  |
| Frontend | Vue 3, Vite, TypeScript, Vuetify 3, Chart.js     |

## Getting started

You need Python 3.13, Node 20+ and Docker Desktop.

### Backend

```bash
cd backend
docker compose up -d                  # starts Postgres on localhost:5432

py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                  # defaults match docker-compose.yml

python -m app.cli seed-demo           # optional: generated test data
python -m app.cli train
python -m app.cli generate

uvicorn app.main:app --reload
```

The API runs on http://127.0.0.1:8000. Swagger docs are at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:5173. If you change `vite.config.ts` or install packages,
restart the dev server.

## Loading data

Prices can come in through a CSV file or the API. The importer handles the usual
column names (`Date`, `LTP`, `Qty`, `Total Traded Amount` and so on), so most NEPSE
exports work without renaming anything.

Required columns: symbol, date, open, high, low, close, volume. Turnover is optional.
If the file is for a single stock and has no symbol column, pass `--symbol`.

```bash
python -m app.cli import-csv data/nabil.csv --symbol NABIL
```

Or upload it:

```bash
curl -F "file=@nabil.csv" -F "symbol=NABIL" http://127.0.0.1:8000/api/v1/prices/import
```

Re-importing the same dates overwrites the old rows rather than duplicating them.

## How the signals are made

1. **Features.** Each stock gets around 33 features per trading day: returns over
   1 to 60 days, distance from moving averages, MACD, RSI, stochastic, Bollinger
   bands, ATR, volatility, volume trends, OBV, distance from the 52-week high and low,
   and liquidity. Market context comes from the average of all stocks (market return,
   breadth, relative strength). Fundamentals (P/E, P/B, ROE, dividend yield, earnings
   yield) are matched to each day using the latest values known at the time.
2. **Target.** Return over the next 10 trading days, bucketed into down (< -3%),
   neutral, and up (> +3%). Both numbers are configurable.
3. **Training.** Split by date, not randomly. The last 20% of dates is held out, with
   a gap the length of the horizon between train and validation so labels can't leak.
   Classes are weighted to balance them, and early stopping runs on the validation set.
   Accuracy, macro F1, log loss, a majority-class baseline and the hit rate of the
   BUY/SELL calls are all saved with each model.
4. **Decision.**
   - **NO TRADE** when there's under 60 days of history, average turnover is below
     Rs. 5 lakh, the data is stale, or the model isn't confident enough.
   - **BUY** / **SELL** when the up/down probability is at least 45% and beats the
     opposite side by 10 points or more.
   - **HOLD** otherwise.
5. **Explanation.** Every call lists the features that pushed the model hardest
   (XGBoost SHAP contributions), plus plain-language notes like "RSI at 27.4 indicates
   oversold conditions".

All the thresholds live in `backend/app/config.py` and can be overridden in `.env`.

A sanity check worth knowing: on purely random prices the model scores a log loss of
about 1.098 (ln 3, the same as guessing) and every stock comes back NO TRADE. That's
what should happen.

## CLI

```
python -m app.cli init-db                        create tables
python -m app.cli import-csv <file> [--symbol]   import prices
python -m app.cli seed-demo [--years 3]          load synthetic test data
python -m app.cli train [--horizon] [--threshold]
python -m app.cli generate                       signals for the latest date
```

## API

Base path is `/api/v1`.

| Method | Path                                | What it does                              |
|--------|-------------------------------------|-------------------------------------------|
| GET    | `/health`                           | DB status and active model                |
| GET    | `/companies`                        | Companies with date range and last close  |
| POST   | `/companies`                        | Add or update a company                   |
| GET    | `/companies/{symbol}/prices`        | Price history (`start`, `end`, `limit`)   |
| POST   | `/companies/{symbol}/prices`        | Add price bars as JSON                    |
| POST   | `/prices/import`                    | CSV upload                                |
| GET    | `/companies/{symbol}/indicators`    | Computed features over time               |
| GET    | `/companies/{symbol}/fundamentals`  | Fundamentals history                      |
| POST   | `/companies/{symbol}/fundamentals`  | Add fundamentals                          |
| GET    | `/companies/{symbol}/insight`       | Live call for one stock, with reasons     |
| POST   | `/models/train`                     | Train a new model                         |
| GET    | `/models`                           | All trained models                        |
| GET    | `/models/active`                    | Active model with metrics                 |
| POST   | `/models/{id}/activate`             | Switch back to an older model             |
| POST   | `/signals/generate`                 | Generate and store signals for all stocks |
| GET    | `/signals`                          | Latest stored signals (`action` filter)   |

## Project layout

```
backend/
  app/
    api/            route handlers
    services/       indicators, features, ingestion, training, signals
    cli.py          management commands
    config.py       settings and signal thresholds
    models.py       database tables
    schemas.py      request/response models
  artifacts/        saved model files (git-ignored)
  docker-compose.yml
frontend/
  src/
    components/     controls, chart, stats, trade history
    services/       in-browser simulation (temporary)
```

## Next up

- A real data source for daily NEPSE prices, either scraped or through an API
- Wire the frontend to the API
- Alembic migrations (tables are created on startup for now)
- Walk-forward backtesting instead of a single train/validation split
- Tests

## Disclaimer

This is a personal research project, not financial advice. The model can and will be
wrong, and past patterns in NEPSE data don't guarantee anything about the future.
