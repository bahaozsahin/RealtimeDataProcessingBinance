# Implementation Plan

## Current State

| Item | Status |
|------|--------|
| `producer/secrets_util.py` | Done |
| `secrets/` (9 real secret files) | Done |
| `secrets.example/` (9 templates) | Done |
| `.gitignore` | Done |
| `PROPOSAL.md` | Done |
| Everything else | Not started |

---

## Phases

### Phase 1 — Producer
> Goal: Connect to Binance WebSocket, publish messages to Redpanda.

| # | File | Description |
|---|------|-------------|
| 1.1 | `producer/requirements.txt` | `aiokafka`, `websockets`, `orjson` |
| 1.2 | `producer/producer.py` | Async WebSocket client → Redpanda. Multi-symbol, exponential backoff reconnect, structured logging, graceful shutdown |
| 1.3 | `producer/Dockerfile` | Python 3.12-slim, non-root user, pip install, CMD |

**Testable checkpoint:** `docker compose up redpanda producer` — messages flowing into Redpanda topic, visible in Redpanda Console.

---

### Phase 2 — Infrastructure (Docker Compose + Init SQL)
> Goal: All stateful services up and initialized with schemas.

| # | File | Description |
|---|------|-------------|
| 2.1 | `docker-compose.yml` | All 9 services (Redpanda, Console, ClickHouse, PostgreSQL, Producer, Consumer, Dagster, Grafana) + secrets + volumes |
| 2.2 | `clickhouse/init.sql` | Kafka Engine table, MergeTree storage, materialized view |
| 2.3 | `postgres/init.sql` | Create database schemas (`raw`, `staging`, `intermediate`, `gold`), `raw_tickers` table, indexes |

**Testable checkpoint:** `docker compose up redpanda clickhouse postgres` — all healthy. ClickHouse auto-ingests from Redpanda after producer sends data. `SELECT count() FROM binance_tickers` shows rows growing.

---

### Phase 3 — Consumer
> Goal: Read from Redpanda, bulk-insert into PostgreSQL.

| # | File | Description |
|---|------|-------------|
| 3.1 | `consumer/secrets_util.py` | Copy of `producer/secrets_util.py` |
| 3.2 | `consumer/requirements.txt` | `aiokafka`, `asyncpg`, `orjson` |
| 3.3 | `consumer/consumer.py` | Async consumer: batch accumulation (1000 rows / 5s), bulk INSERT via `asyncpg`, manual Kafka offset commit, graceful shutdown |
| 3.4 | `consumer/Dockerfile` | Python 3.12-slim, non-root user |

**Testable checkpoint:** `docker compose up redpanda postgres producer consumer` — rows appearing in `raw_tickers` table. `SELECT count(*) FROM raw_tickers;` growing.

---

### Phase 4 — dbt Project
> Goal: Bronze → Silver → Gold medallion models on PostgreSQL.

| # | File | Description |
|---|------|-------------|
| 4.1 | `dbt_project/dbt_project.yml` | Project config, profile reference, model paths |
| 4.2 | `dbt_project/profiles.yml` | PostgreSQL connection (reads password from env/secret) |
| 4.3 | `dbt_project/models/sources/_sources.yml` | Source definition pointing to `raw.raw_tickers` |
| 4.4 | `dbt_project/models/staging/stg_tickers.sql` | Incremental, selects from source, dedup logic |
| 4.5 | `dbt_project/models/staging/_staging.yml` | Column docs + tests |
| 4.6 | `dbt_project/models/intermediate/int_ticker_enriched.sql` | Adds `trade_value_usd`, `prev_price`, `price_change` (window functions) |
| 4.7 | `dbt_project/models/intermediate/_intermediate.yml` | Column docs + tests |
| 4.8 | `dbt_project/models/gold/ohlcv_1h.sql` | Hourly OHLCV candles per symbol |
| 4.9 | `dbt_project/models/gold/daily_summary.sql` | Daily aggregates per symbol |
| 4.10 | `dbt_project/models/gold/symbol_performance.sql` | All-time stats per symbol (full table rebuild) |
| 4.11 | `dbt_project/models/gold/_gold.yml` | Column docs + tests |

**Testable checkpoint:** After consumer has run, manually invoke `dbt build` inside the Dagster container. Verify Gold tables populated: `SELECT * FROM gold.ohlcv_1h LIMIT 5;`

---

### Phase 5 — Dagster (Orchestrator)
> Goal: Schedule hourly dbt runs, provide UI for monitoring.

| # | File | Description |
|---|------|-------------|
| 5.1 | `orchestration/requirements.txt` | `dagster`, `dagster-webserver`, `dagster-dbt`, `dagster-postgres`, `dbt-postgres` |
| 5.2 | `orchestration/definitions.py` | `@dbt_assets`, `ScheduleDefinition` (hourly cron), Definitions export |
| 5.3 | `orchestration/Dockerfile` | Python 3.12-slim, install deps, copy dbt project, `dagster-webserver` CMD |

**Testable checkpoint:** `docker compose up dagster` — Dagster UI at `localhost:3000`, dbt assets visible, manually trigger a run, verify Gold tables update.

---

### Phase 6 — Grafana (Visualization)
> Goal: Auto-provisioned datasources and dashboards.

| # | File | Description |
|---|------|-------------|
| 6.1 | `grafana/provisioning/datasources/datasources.yml` | ClickHouse + PostgreSQL datasource definitions |
| 6.2 | `grafana/provisioning/dashboards/dashboards.yml` | Dashboard provider config (points to JSON files) |
| 6.3 | `grafana/provisioning/dashboards/realtime.json` | Live ticker prices + trade volume (ClickHouse, 5s refresh) |
| 6.4 | `grafana/provisioning/dashboards/analytics.json` | OHLCV candles + daily summary (PostgreSQL Gold, 1h refresh) |

**Testable checkpoint:** `docker compose up grafana` — Grafana at `localhost:3001`, both datasources green, dashboards showing data.

---

### Phase 7 — Scripts & Docs
> Goal: One-command startup, status checks, documentation.

| # | File | Description |
|---|------|-------------|
| 7.1 | `scripts/start.bat` | `docker compose up -d --build` |
| 7.2 | `scripts/stop.bat` | `docker compose down` |
| 7.3 | `scripts/status.bat` | `docker compose ps` + health summary |
| 7.4 | `scripts/start.sh` | Linux/Mac equivalent |
| 7.5 | `README.md` | Quick start, architecture overview, access points, secrets setup |

**Testable checkpoint:** Fresh clone → `cp -r secrets.example/ secrets/` → fill passwords → `scripts/start.bat` → everything up and dashboards live.

---

## File Count Summary

| Phase | Files | Cumulative |
|-------|-------|------------|
| Already done | 12 | 12 |
| Phase 1 — Producer | 3 | 15 |
| Phase 2 — Infrastructure | 3 | 18 |
| Phase 3 — Consumer | 4 | 22 |
| Phase 4 — dbt | 11 | 33 |
| Phase 5 — Dagster | 3 | 36 |
| Phase 6 — Grafana | 4 | 40 |
| Phase 7 — Scripts & Docs | 5 | 45 |
| **Total** | **~45 files** | |

---

## Dependency Graph

```
Phase 1 (Producer) ──┐
                     ├──► Phase 2 (docker-compose + init SQL)
                     │         │
                     │    ┌────┴─────┐
                     │    ▼          ▼
                     │  Phase 3   ClickHouse
                     │  (Consumer)  ready
                     │    │
                     │    ▼
                     │  Phase 4 (dbt)
                     │    │
                     │    ▼
                     │  Phase 5 (Dagster)
                     │    │
                     ├────┘
                     ▼
               Phase 6 (Grafana)
                     │
                     ▼
               Phase 7 (Scripts & Docs)
```

Phases 1 and 2 can be worked on together. Phases 3 onward are sequential.
