# Member Intelligence API

> AI-powered member analytics for credit unions — ingest member data, run ETL pipelines, and generate AI-driven financial insights.

![Demo](member%20intelligence.gif)

---


## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00?style=flat&logo=sqlalchemy&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-migrations-6BA81E?style=flat)
![Pandas](https://img.shields.io/badge/Pandas-ETL-150458?style=flat&logo=pandas&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat&logo=pydantic&logoColor=white)
![Claude](https://img.shields.io/badge/Anthropic-Claude-191919?style=flat&logo=anthropic&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-database-4169E1?style=flat&logo=postgresql&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-FF4B4B?style=flat&logo=streamlit&logoColor=white)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit Dashboard                      │
│                       dashboard/app.py :8501                    │
│                                                                 │
│   ┌──────────────┐  ┌─────────────────┐  ┌──────────────────┐  │
│   │ Member Search│  │  Member Detail  │  │ Segment Summary  │  │
│   │ search/filter│  │ portfolio+ratios│  │ Plotly bar charts│  │
│   │ drill-through│  │ AI Insight panel│  │ avg dep/loan/LTD │  │
│   └──────────────┘  └─────────────────┘  └──────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │ httpx  (localhost:8000)
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Application                        │
│                        app/main.py :8000                        │
│                                                                 │
│  POST /ingest          app/routers/ingest.py                    │
│  GET  /members         app/routers/members.py                   │
│  GET  /members/{id}                                             │
│  GET  /members/{id}/portfolio                                   │
│  POST /members/{id}/analyze   app/routers/insights.py           │
│  GET  /segments/summary       app/routers/members.py            │
│  GET  /health                                                   │
└──────┬───────────────────────────────────────┬──────────────────┘
       │                                       │
┌──────▼──────────────────┐    ┌───────────────▼────────────────┐
│    Services Layer       │    │       Anthropic API            │
│                         │    │                                │
│  app/services/etl.py    │    │  app/services/ai_service.py    │
│  ┌─────────────────┐    │    │  ┌──────────────────────────┐  │
│  │ pandas pipeline │    │    │  │ claude-sonnet-4-6        │  │
│  │ clean → validate│    │    │  │ system prompt: advisor   │  │
│  │ → bulk insert   │    │    │  │ returns JSON:            │  │
│  └────────┬────────┘    │    │  │  narrative               │  │
│           │             │    │  │  risk_flags              │  │
└───────────┼─────────────┘    │  │  cross_sell_opps         │  │
            │                  │  └──────────────────────────┘  │
┌───────────▼─────────────────────────────────────────────────┐  │
│                   SQLAlchemy ORM                            │  │
│                   app/models/                               │  │
│                                                             │  │
│  members ──────┬──── accounts                              │  │
│  (500 rows)    └──── loans                                  │  │
│  member_number      (800 rows)  (350 rows)                  │  │
│  segment            balance     current_balance             │  │
│  member_since       type        loan_type                   │  │
│  ...                status      interest_rate ...           │  │
└─────────────────────────────┬───────────────────────────────┘  │
                              │                                   │
                    ┌─────────▼──────────┐                        │
                    │   SQLite           │                        │
                    │  member_intel.db   │                        │
                    └────────────────────┘                        │
                                                                  │
       ┌──────────────────────────────────────────────────────────┘
       │
┌──────▼────────────────────────────────────┐
│          Data Generation / Ingest         │
│                                           │
│  data/generate_mock_data.py               │
│    → data/raw/members.csv   (500 rows)    │
│    → data/raw/accounts.csv  (800 rows)    │
│    → data/raw/loans.csv     (350 rows)    │
│                                           │
│  POST /ingest (multipart CSV upload)      │
│    → etl.py cleans, validates, loads      │
└───────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Generate mock data

```bash
python data/generate_mock_data.py
```

### 4. Start the API server

```bash
uvicorn app.main:app --reload
```

SQLite tables are created automatically on first run.

### 5. Ingest the CSVs

```bash
curl -X POST http://localhost:8000/ingest \
  -F "members=@data/raw/members.csv" \
  -F "accounts=@data/raw/accounts.csv" \
  -F "loans=@data/raw/loans.csv"
```

### 6. Start the dashboard

```bash
streamlit run dashboard/app.py
```

Open `http://localhost:8501`. API docs at `http://localhost:8000/docs`.

---

## Deploy to Railway

### Prerequisites
- [Railway CLI](https://docs.railway.app/develop/cli) installed and logged in
- A Railway project with a **PostgreSQL** add-on provisioned

### Steps

```bash
# 1. Link repo to your Railway project
railway link

# 2. Add environment variables (DATABASE_URL is injected automatically from Postgres add-on)
railway variables set ANTHROPIC_API_KEY=sk-ant-...

# 3. Deploy
railway up
```

Railway reads `railway.toml` and runs:
```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`DATABASE_URL` is injected automatically by the Railway Postgres add-on. The app converts `postgres://` → `postgresql+psycopg2://` at startup, so no manual URL editing is needed.

After deploying, ingest your data against the live URL:
```bash
curl -X POST https://<your-app>.railway.app/ingest \
  -F "members=@data/raw/members.csv" \
  -F "accounts=@data/raw/accounts.csv" \
  -F "loans=@data/raw/loans.csv"
```

> **Note:** The Streamlit dashboard is a local dev tool — point `API_BASE` in `dashboard/app.py` at your Railway URL to use it against the deployed API.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/ingest` | Upload member/account/loan CSVs |
| `GET` | `/members` | Paginated member list (`?page=`, `?page_size=`, `?segment=`) |
| `GET` | `/members/{id}` | Member detail with summary (deposits, loans, tenure) |
| `GET` | `/members/{id}/portfolio` | Full portfolio breakdown with ratios |
| `POST` | `/members/{id}/analyze` | Generate AI insight via Claude |
| `GET` | `/segments/summary` | Aggregate stats grouped by segment |

---

## Project Structure

```
member-intel-api/
├── app/
│   ├── main.py               # FastAPI app, router registration
│   ├── config.py             # pydantic-settings (loads .env)
│   ├── database.py           # SQLAlchemy engine, SessionLocal, Base
│   ├── models/
│   │   ├── member.py         # members table
│   │   ├── account.py        # accounts table (FK → members)
│   │   └── loan.py           # loans table (FK → members)
│   ├── schemas/
│   │   ├── member.py         # Pydantic request/response schemas
│   │   └── insights.py       # AI insight schemas
│   ├── routers/
│   │   ├── members.py        # /members + /segments endpoints
│   │   ├── ingest.py         # POST /ingest
│   │   └── insights.py       # POST /members/{id}/analyze
│   └── services/
│       ├── etl.py            # pandas clean → SQLAlchemy bulk load
│       └── ai_service.py     # Anthropic SDK wrapper
├── dashboard/
│   └── app.py                # Streamlit dashboard (3 pages)
├── data/
│   ├── generate_mock_data.py # Generates realistic CSVs
│   └── raw/                  # Drop CSVs here for ingestion
├── tests/
├── .env.example
└── requirements.txt
```

---

## Key Design Decisions

**ETL processes members before accounts/loans** so foreign key lookups always resolve. Rows referencing unknown `member_number` values are skipped with a warning rather than aborting the entire import.

**`Decimal` throughout** — balances and rates use `Numeric` columns in SQLAlchemy and `Decimal` in Python. Values are cast via `Decimal(str(x))` when sourced from SQLite aggregates to avoid float precision loss.

**Loan-to-deposit ratio is `None` when deposits = 0** rather than `0` or `∞`, and is excluded from segment averages accordingly.

**AI insights are never cached on the server** — each `POST /members/{id}/analyze` call is fresh. The dashboard caches the last result in `session_state` keyed by `member_id`, cleared when the user navigates to a different member.

**Segment average LTD** is computed as the mean of per-member ratios (not `SUM(loans)/SUM(deposits)`), so members with large balances don't dominate the segment figure.
