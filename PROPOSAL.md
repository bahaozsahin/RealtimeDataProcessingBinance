# Binance Real-Time Data Pipeline — Rebuild Proposal

## Executive Summary

Dual-layer analytics pipeline for Binance market data: a **real-time path** for sub-second dashboards and a **batch analytics path** for dbt-modeled reporting — all orchestrated by Dagster and secured with Docker Secrets.

| Layer | Path | Latency |
|-------|------|---------|
| Real-time | Producer → Redpanda → ClickHouse (Kafka Engine + MVs) → Grafana | < 2 s |
| Batch | Consumer → PostgreSQL → dbt (Bronze→Silver→Gold) → Grafana | 1 hour |

**8 containers**, ~2 GB total RAM, single `docker compose up`.

---

## Architecture

```
  ┌────────────┐    ┌────────────┐    ┌───────────────┐
  │  Binance   │───►│  Producer  │───►│   Redpanda    │
  │  WebSocket │    │  (Python)  │    │   (Broker)    │
  └────────────┘    └────────────┘    └───────┬───────┘
                                          ┌───┴────┐
                             Kafka Engine │        │ aiokafka
                            (auto-ingest) │        │
                                    ┌─────▼─────┐ ┌▼───────────┐
                                    │ ClickHouse │ │  Consumer  │
                                    │ (Real-time │ │  (Python)  │
                                    │   OLAP)    │ └─────┬──────┘
                                    └─────┬──────┘       │
                                          │        ┌─────▼──────┐
                                          │        │ PostgreSQL │
                                          │        │   (DWH)    │
                                          │        └─────┬──────┘
                                          │              │
                                          │  ┌───────────┼──────────────────┐
                                          │  │  Dagster   ▼    (Orchestrator)│
                                          │  │  ┌──────────────┐           │
                                          │  │  │     dbt      │           │
                                          │  │  │  Bronze→Gold │           │
                                          │  │  └──────┬───────┘           │
                                          │  └─────────┼───────────────────┘
                                          │            │
                                    ┌─────▼────────────▼─────┐
                                    │        Grafana          │
                                    │  ClickHouse (real-time) │
                                    │  PostgreSQL (Gold)      │
                                    └────────────────────────-┘
```

### Data Flow

**Real-time path (< 2s latency):**
1. Producer connects to Binance WebSocket, streams ticker data
2. Publishes JSON messages to Redpanda topic `binance-tickers`
3. ClickHouse Kafka Engine reads from Redpanda automatically
4. Materialized views transform and store in ReplacingMergeTree tables (30-day TTL, deduped by `trade_id`)
5. Grafana queries ClickHouse for live dashboards (5s refresh, `FINAL` for deduped reads)

**Batch analytics path (1-hour schedule):**
1. Consumer reads from Redpanda topic `binance-tickers` via aiokafka
2. Bulk-inserts to PostgreSQL with `ON CONFLICT (symbol, trade_id) DO NOTHING` (duplicates rejected at write)
3. Dagster triggers dbt run on 1-hour schedule
4. dbt transforms Bronze → Silver → Gold layers (all data is clean from source)
5. Grafana queries PostgreSQL Gold tables for analytical dashboards

---

## Dedup Strategy

**Delivery guarantee:** At-least-once (retry until ack'd, no data loss, possible duplicates).

**Dedup key:** `(symbol, trade_id)` — Binance's unique trade identifier per symbol.

| Branch | Method | When dedup happens |
|--------|--------|--------------------|
| Real-time (ClickHouse) | `ReplacingMergeTree(event_time)` | Background merge (async) or `FINAL` keyword (query-time) |
| Batch (PostgreSQL) | `UNIQUE(symbol, trade_id)` + `ON CONFLICT DO NOTHING` | At INSERT time — duplicates silently rejected by the database |

**Why this design:**
- Both branches dedup by the same natural key: `(symbol, trade_id)`
- Every layer is trustworthy — no dirty data anywhere, no dedup logic needed in dbt
- INSERT overhead is negligible on the batch path (~2-5ms per 1000-row batch)
- Future scaling: add table partitioning when raw table exceeds ~100M rows

---

## Components

### 1. Producer (Python 3.12)

Async WebSocket client that streams Binance market data into Redpanda.

| Spec | Detail |
|------|--------|
| Runtime | Python 3.12-slim |
| Async | `asyncio` + `websockets` + `aiokafka` |
| Symbols | Configurable via `symbols` secret (comma-separated) |
| Reconnect | Exponential backoff (1s → 60s max, jitter) |
| Health | Structured JSON logging, message counter metrics |
| Secrets | `secrets_util.py` — `SecretStr` masking |

**Key dependencies:** `aiokafka`, `websockets`, `orjson`

**Message schema:**
```json
{
  "trade_id": 123456789,
  "symbol": "BTCUSDT",
  "price": "67234.50",
  "quantity": "0.00123",
  "timestamp": 1700000000000,
  "event_time": 1700000000001,
  "buyer_maker": false,
  "ingested_at": "2024-01-15T12:00:00.123Z"
}
```

> `trade_id` is Binance's unique trade identifier (`data["t"]`). Used as the natural dedup key across both ClickHouse and PostgreSQL.

---

### 2. Redpanda (Message Broker)

Kafka-compatible streaming platform. Single binary, no ZooKeeper, no JVM.

| Spec | Detail |
|------|--------|
| Image | `redpandadata/redpanda:latest` |
| RAM | ~300 MB |
| Ports | 9092 (Kafka), 8081 (Schema Registry), 8082 (REST Proxy), 9644 (Admin) |
| Topic | `binance-tickers`, 1 partition, RF=1 |
| Retention | 24 hours (enough for consumer catch-up) |
| Console | `redpandadata/console:latest` on port 8080 |

**Why Redpanda over Kafka:**
- No ZooKeeper/KRaft dependency
- 10x lower tail latency
- Built-in Schema Registry + REST Proxy
- Kafka API compatible (aiokafka works unchanged)

---

### 3. ClickHouse (Real-time OLAP)

Columnar database with native Kafka Engine that auto-ingests from Redpanda.

| Spec | Detail |
|------|--------|
| Image | `clickhouse/clickhouse-server:latest` |
| RAM | ~500 MB |
| Ports | 8123 (HTTP), 9000 (Native) |
| Storage | ReplacingMergeTree, 30-day TTL |
| Ingestion | Kafka Engine → Materialized View → ReplacingMergeTree |
| Dedup | ReplacingMergeTree collapses duplicates by `(symbol, trade_id)` on background merge |

**Init SQL creates:**

```sql
-- 1. Kafka Engine (virtual — reads from Redpanda)
CREATE TABLE binance_queue (
    trade_id     UInt64,
    symbol       String,
    price        Float64,
    quantity     Float64,
    timestamp    UInt64,
    event_time   UInt64,
    buyer_maker  UInt8,
    ingested_at  String
) ENGINE = Kafka
SETTINGS
    kafka_broker_list          = 'redpanda:9092',
    kafka_topic_list           = 'binance-tickers',
    kafka_group_name           = 'clickhouse-consumer',
    kafka_format               = 'JSONEachRow',
    kafka_num_consumers        = 1;

-- 2. ReplacingMergeTree storage (deduplicates by ORDER BY key on merge)
CREATE TABLE binance_tickers (
    trade_id     UInt64,
    symbol       LowCardinality(String),
    price        Float64,
    quantity     Float64,
    trade_time   DateTime64(3),
    event_time   DateTime64(3),
    buyer_maker  UInt8,
    ingested_at  DateTime64(3)
) ENGINE = ReplacingMergeTree(event_time)
ORDER BY (symbol, trade_id)
TTL trade_time + INTERVAL 30 DAY;

-- 3. Materialized View (auto-pipes Kafka → ReplacingMergeTree)
CREATE MATERIALIZED VIEW binance_mv TO binance_tickers AS
SELECT
    trade_id,
    symbol,
    price,
    quantity,
    toDateTime64(timestamp / 1000, 3)   AS trade_time,
    toDateTime64(event_time / 1000, 3)  AS event_time,
    buyer_maker,
    parseDateTimeBestEffort(ingested_at) AS ingested_at
FROM binance_queue;
```

> **Dedup behavior:** `ReplacingMergeTree(event_time)` keeps the row with the latest `event_time` for each `(symbol, trade_id)` key. Dedup happens during async background merges. For guaranteed dedup at query time, use `SELECT ... FROM binance_tickers FINAL`.

---

### 4. Consumer (Python 3.12)

Async Kafka consumer that reads from Redpanda and bulk-inserts into PostgreSQL.

| Spec | Detail |
|------|--------|
| Runtime | Python 3.12-slim |
| Async | `asyncio` + `aiokafka` + `asyncpg` |
| Batching | Accumulates up to 1000 rows or 5s, then bulk INSERT |
| Commit | Manual Kafka offset commit after successful DB write |
| At-least-once | Messages are re-delivered on crash (deduped via UNIQUE constraint + `ON CONFLICT DO NOTHING`) |

**Key dependencies:** `aiokafka`, `asyncpg`, `orjson`

**Consumer logic:**
```python
async def consume_loop():
    consumer = AIOKafkaConsumer("binance-tickers", ...)
    batch = []

    async for msg in consumer:
        batch.append(parse(msg))
        if len(batch) >= 1000 or time_since_last_flush > 5:
            await bulk_insert(pool, batch)
            await consumer.commit()
            batch.clear()
```

**PostgreSQL target table:**
```sql
CREATE TABLE raw_tickers (
    id          BIGSERIAL PRIMARY KEY,
    trade_id    BIGINT NOT NULL,
    symbol      TEXT NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    quantity    DOUBLE PRECISION NOT NULL,
    trade_time  TIMESTAMPTZ NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    buyer_maker BOOLEAN NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_raw_tickers_symbol_time ON raw_tickers (symbol, trade_time);
CREATE UNIQUE INDEX idx_raw_tickers_dedup ON raw_tickers (symbol, trade_id);
```

> **Two indexes by design:**
> - `(symbol, trade_time)` — for dbt incremental scans and Grafana time-range queries
> - `(symbol, trade_id)` UNIQUE — for dedup via `ON CONFLICT DO NOTHING`
>
> They serve different purposes and cannot be merged. Write overhead of maintaining both is negligible on the batch path (~4-10ms per 1000-row batch).
> When the table exceeds ~100M rows, add table partitioning by `trade_time` to keep indexes in RAM.

---

### 5. PostgreSQL (Analytical DWH)

Serves as the batch analytics warehouse for dbt transformations.

| Spec | Detail |
|------|--------|
| Image | `postgres:16-alpine` |
| RAM | ~200 MB |
| Port | 5432 |
| Database | `binance_dwh` |
| Schemas | `raw`, `staging`, `intermediate`, `gold` |

**Init script creates:**
- Database `binance_dwh`
- Schemas for each dbt layer
- `raw_tickers` table (consumer target)
- Indexes for time-range queries

---

### 6. dbt (Medallion Architecture on PostgreSQL)

Transforms raw data through Bronze → Silver → Gold layers on a 1-hour schedule.

| Spec | Detail |
|------|--------|
| Adapter | `dbt-postgres` |
| Schedule | Every 1 hour (triggered by Dagster) |
| Incremental | All models use `incremental` materialization |

**Bronze (staging) — `stg_tickers`:**
```sql
-- models/staging/stg_tickers.sql
{{ config(materialized='incremental', unique_key='trade_id') }}

SELECT
    trade_id,
    symbol,
    price,
    quantity,
    trade_time,
    event_time,
    buyer_maker,
    ingested_at,
    loaded_at
FROM {{ source('raw', 'raw_tickers') }}
{% if is_incremental() %}
WHERE loaded_at > (SELECT MAX(loaded_at) FROM {{ this }})
{% endif %}
```

> `stg_tickers` reads directly from the raw source — no dedup layer needed since `raw_tickers` is already clean (UNIQUE constraint rejects duplicates at write time).

**Silver (intermediate) — `int_ticker_enriched`:**
```sql
-- models/intermediate/int_ticker_enriched.sql
{{ config(materialized='incremental', unique_key='trade_id') }}

SELECT
    trade_id,
    symbol,
    price,
    quantity,
    price * quantity                                                AS trade_value_usd,
    LAG(price) OVER (PARTITION BY symbol ORDER BY trade_time)       AS prev_price,
    price - LAG(price) OVER (PARTITION BY symbol ORDER BY trade_time) AS price_change,
    trade_time,
    event_time,
    buyer_maker,
    ingested_at
FROM {{ ref('stg_tickers') }}
{% if is_incremental() %}
WHERE ingested_at > (SELECT MAX(ingested_at) FROM {{ this }})
{% endif %}
```

**Gold — `ohlcv_1h`:**
```sql
-- models/gold/ohlcv_1h.sql
{{ config(materialized='incremental', unique_key=['symbol', 'bucket']) }}

SELECT
    symbol,
    DATE_TRUNC('hour', trade_time)                         AS bucket,
    (ARRAY_AGG(price ORDER BY trade_time ASC))[1]          AS open,
    MAX(price)                                              AS high,
    MIN(price)                                              AS low,
    (ARRAY_AGG(price ORDER BY trade_time DESC))[1]         AS close,
    SUM(quantity)                                           AS volume,
    SUM(price * quantity)                                   AS turnover,
    COUNT(*)                                                AS trade_count
FROM {{ ref('int_ticker_enriched') }}
{% if is_incremental() %}
WHERE trade_time > (SELECT MAX(bucket) - INTERVAL '2 hours' FROM {{ this }})
{% endif %}
GROUP BY symbol, DATE_TRUNC('hour', trade_time)
```

**Gold — `daily_summary`:**
```sql
-- models/gold/daily_summary.sql
{{ config(materialized='incremental', unique_key=['symbol', 'trade_date']) }}

SELECT
    symbol,
    DATE(trade_time)     AS trade_date,
    MIN(price)           AS day_low,
    MAX(price)           AS day_high,
    AVG(price)           AS day_avg,
    SUM(quantity)        AS day_volume,
    SUM(price * quantity) AS day_turnover,
    COUNT(*)             AS day_trade_count
FROM {{ ref('int_ticker_enriched') }}
{% if is_incremental() %}
WHERE trade_time > (SELECT MAX(trade_date) - INTERVAL '1 day' FROM {{ this }})
{% endif %}
GROUP BY symbol, DATE(trade_time)
```

**Gold — `symbol_performance`:**
```sql
-- models/gold/symbol_performance.sql
{{ config(materialized='table') }}

SELECT
    symbol,
    MIN(price)           AS all_time_low,
    MAX(price)           AS all_time_high,
    COUNT(*)             AS total_trades,
    SUM(quantity)        AS total_volume,
    SUM(price * quantity) AS total_turnover,
    MIN(trade_time)      AS first_seen,
    MAX(trade_time)      AS last_seen
FROM {{ ref('int_ticker_enriched') }}
GROUP BY symbol
```

---

### 7. Dagster (Orchestrator)

Runs as webserver + daemon. Orchestrates dbt, monitors the real-time pipeline, and provides full asset lineage.

| Spec | Detail |
|------|--------|
| Image | Custom (Python 3.12 + `dagster` + `dagster-dbt` + `dagster-postgres`) |
| Ports | 3000 (Dagster UI) |
| Backend | PostgreSQL (shared instance, `dagster` schema) |
| Schedule | dbt run every 1 hour |
| Sensors | Pipeline health (consumer lag, ClickHouse row count) |

**Integration with dbt:**
```python
# orchestration/definitions.py
from dagster import Definitions, ScheduleDefinition
from dagster_dbt import DbtCliResource, dbt_assets, DbtProject

dbt_project = DbtProject(project_dir="/opt/dbt")

@dbt_assets(manifest=dbt_project.manifest_path)
def dbt_binance_assets(context, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()

dbt_schedule = ScheduleDefinition(
    job=dbt_binance_assets.to_job(),
    cron_schedule="0 * * * *",  # every hour
)

defs = Definitions(
    assets=[dbt_binance_assets],
    schedules=[dbt_schedule],
    resources={"dbt": DbtCliResource(project_dir="/opt/dbt")},
)
```

**Sensors (optional, for monitoring):**
- Consumer lag sensor — alerts if Redpanda consumer group lag > threshold
- ClickHouse freshness sensor — alerts if latest row is older than 30s
- dbt run status sensor — tracks dbt run success/failure

---

### 8. Grafana (Visualization)

Dual-datasource dashboards: ClickHouse for real-time, PostgreSQL Gold for analytics.

| Spec | Detail |
|------|--------|
| Image | `grafana/grafana:latest` |
| Port | 3001 |
| Plugins | `grafana-clickhouse-datasource` (pre-installed) |
| Provisioning | Datasources + dashboards auto-configured |

**Datasources:**

| Name | Type | Database | Use Case |
|------|------|----------|----------|
| ClickHouse | `grafana-clickhouse-datasource` | `default` | Real-time tickers, live price, 5s refresh |
| PostgreSQL | `postgres` (built-in) | `binance_dwh` | Gold tables: OHLCV, daily summaries, performance |

**Dashboard examples:**

| Dashboard | Source | Refresh |
|-----------|--------|---------|
| Live Ticker Prices | ClickHouse | 5s |
| Trade Volume Heatmap | ClickHouse | 10s |
| Hourly OHLCV Candles | PostgreSQL (Gold) | 1h |
| Daily Performance | PostgreSQL (Gold) | 1h |
| Symbol Comparison | PostgreSQL (Gold) | 1h |

---

## Project Structure

```
RealtimeDataProcessingBinance/
├── docker-compose.yml
├── .gitignore
├── README.md
├── PROPOSAL.md
│
├── producer/
│   ├── Dockerfile
│   ├── producer.py
│   ├── secrets_util.py        # ✅ Done — SecretStr + read_secret()
│   └── requirements.txt
│
├── consumer/
│   ├── Dockerfile
│   ├── consumer.py
│   ├── secrets_util.py        # Shared copy (or symlink)
│   └── requirements.txt
│
├── clickhouse/
│   └── init.sql               # Kafka Engine + MV + MergeTree
│
├── postgres/
│   └── init.sql               # Database, schemas, raw_tickers table
│
├── dbt_project/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── models/
│   │   ├── staging/
│   │   │   ├── _staging.yml
│   │   │   └── stg_tickers.sql
│   │   ├── intermediate/
│   │   │   ├── _intermediate.yml
│   │   │   └── int_ticker_enriched.sql
│   │   └── gold/
│   │       ├── _gold.yml
│   │       ├── ohlcv_1h.sql
│   │       ├── daily_summary.sql
│   │       └── symbol_performance.sql
│   └── sources/
│       └── _sources.yml
│
├── orchestration/
│   ├── Dockerfile
│   ├── definitions.py
│   └── requirements.txt
│
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── datasources.yml
│   │   └── dashboards/
│   │       ├── dashboards.yml
│   │       └── *.json
│   └── grafana.ini             # (optional overrides)
│
├── secrets/                    # gitignored — real values
│   ├── .gitkeep
│   ├── symbols.txt
│   ├── stream_type.txt
│   ├── redpanda_broker.txt
│   ├── topic.txt
│   ├── log_level.txt
│   ├── clickhouse_password.txt
│   ├── postgres_password.txt
│   ├── grafana_admin_user.txt
│   └── grafana_admin_password.txt
│
├── secrets.example/            # committed — safe defaults/templates
│   ├── symbols.txt
│   ├── stream_type.txt
│   ├── redpanda_broker.txt
│   ├── topic.txt
│   ├── log_level.txt
│   ├── clickhouse_password.txt
│   ├── postgres_password.txt
│   ├── grafana_admin_user.txt
│   └── grafana_admin_password.txt
│
└── scripts/
    ├── start.bat
    ├── start.sh
    ├── stop.bat
    ├── status.bat
    └── health_check.sh
```

---

## Docker Compose

```yaml
services:
  # ── Message Broker ──────────────────────────────────
  redpanda:
    image: redpandadata/redpanda:latest
    command:
      - redpanda start
      - --overprovisioned
      - --smp 1
      - --memory 256M
      - --reserve-memory 0M
      - --node-id 0
      - --kafka-addr PLAINTEXT://0.0.0.0:29092,OUTSIDE://0.0.0.0:9092
      - --advertise-kafka-addr PLAINTEXT://redpanda:29092,OUTSIDE://localhost:9092
      - --pandaproxy-addr 0.0.0.0:8082
      - --advertise-pandaproxy-addr localhost:8082
    ports:
      - "9092:9092"
      - "8082:8082"
      - "9644:9644"
    volumes:
      - redpanda_data:/var/lib/redpanda/data
    healthcheck:
      test: ["CMD", "rpk", "cluster", "health"]
      interval: 10s
      retries: 5

  redpanda-console:
    image: redpandadata/console:latest
    ports:
      - "8080:8080"
    environment:
      KAFKA_BROKERS: redpanda:29092
    depends_on:
      redpanda:
        condition: service_healthy

  # ── Producer ────────────────────────────────────────
  producer:
    build: ./producer
    secrets:
      - symbols
      - stream_type
      - redpanda_broker
      - topic
      - log_level
    depends_on:
      redpanda:
        condition: service_healthy
    restart: unless-stopped

  # ── Real-time OLAP ─────────────────────────────────
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"
      - "9000:9000"
    environment:
      CLICKHOUSE_PASSWORD_FILE: /run/secrets/clickhouse_password
    secrets:
      - clickhouse_password
    volumes:
      - clickhouse_data:/var/lib/clickhouse
      - ./clickhouse/init.sql:/docker-entrypoint-initdb.d/init.sql
    depends_on:
      redpanda:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "clickhouse-client", "--query", "SELECT 1"]
      interval: 10s
      retries: 5

  # ── Analytical DWH ─────────────────────────────────
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: binance_dwh
      POSTGRES_USER: binance
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U binance -d binance_dwh"]
      interval: 10s
      retries: 5

  # ── Batch Consumer ─────────────────────────────────
  consumer:
    build: ./consumer
    secrets:
      - redpanda_broker
      - topic
      - postgres_password
      - log_level
    depends_on:
      redpanda:
        condition: service_healthy
      postgres:
        condition: service_healthy
    restart: unless-stopped

  # ── Orchestrator ───────────────────────────────────
  dagster:
    build: ./orchestration
    ports:
      - "3000:3000"
    environment:
      DAGSTER_HOME: /opt/dagster/home
    secrets:
      - postgres_password
    volumes:
      - ./dbt_project:/opt/dbt
      - dagster_home:/opt/dagster/home
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  # ── Visualization ──────────────────────────────────
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      GF_INSTALL_PLUGINS: grafana-clickhouse-datasource
      GF_SECURITY_ADMIN_USER__FILE: /run/secrets/grafana_admin_user
      GF_SECURITY_ADMIN_PASSWORD__FILE: /run/secrets/grafana_admin_password
    secrets:
      - grafana_admin_user
      - grafana_admin_password
      - clickhouse_password
      - postgres_password
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    depends_on:
      clickhouse:
        condition: service_healthy
      postgres:
        condition: service_healthy
    restart: unless-stopped

# ── Secrets ─────────────────────────────────────────
secrets:
  symbols:
    file: ./secrets/symbols.txt
  stream_type:
    file: ./secrets/stream_type.txt
  redpanda_broker:
    file: ./secrets/redpanda_broker.txt
  topic:
    file: ./secrets/topic.txt
  log_level:
    file: ./secrets/log_level.txt
  clickhouse_password:
    file: ./secrets/clickhouse_password.txt
  postgres_password:
    file: ./secrets/postgres_password.txt
  grafana_admin_user:
    file: ./secrets/grafana_admin_user.txt
  grafana_admin_password:
    file: ./secrets/grafana_admin_password.txt

# ── Volumes ─────────────────────────────────────────
volumes:
  redpanda_data:
  clickhouse_data:
  postgres_data:
  grafana_data:
  dagster_home:
```

---

## Secrets Management

**No `.env` file.** All configuration flows through Docker Secrets mounted at `/run/secrets/`.

### Lookup Order (in Python services)

```
1. /run/secrets/<name>     →  Docker secret (production)
2. <NAME> env var          →  local dev override
3. default value           →  hardcoded fallback
```

### Secret Files

| Secret | Services | Example Value |
|--------|----------|---------------|
| `symbols` | producer | `btcusdt,ethusdt,solusdt` |
| `stream_type` | producer | `trade` |
| `redpanda_broker` | producer, consumer | `redpanda:29092` |
| `topic` | producer, consumer | `binance-tickers` |
| `log_level` | producer, consumer | `INFO` |
| `clickhouse_password` | clickhouse, grafana | (random 24-char) |
| `postgres_password` | postgres, consumer, dagster, grafana | (random 24-char) |
| `grafana_admin_user` | grafana | `admin` |
| `grafana_admin_password` | grafana | (random 24-char) |

### Setup

```bash
# Copy templates and fill in real values
cp -r secrets.example/ secrets/

# Or generate random passwords
python -c "import secrets; print(secrets.token_urlsafe(24))" > secrets/clickhouse_password.txt
python -c "import secrets; print(secrets.token_urlsafe(24))" > secrets/postgres_password.txt
python -c "import secrets; print(secrets.token_urlsafe(24))" > secrets/grafana_admin_password.txt
```

### SecretStr (Python)

All secrets are wrapped in `SecretStr` which prevents accidental logging:

```python
from secrets_util import read_secret

broker = read_secret("redpanda_broker", default="localhost:9092")
print(broker)        # → "******"
broker.get()         # → "redpanda:29092" (actual value)
f"using {broker}"    # → "using ******"
```

---

## Startup Flow

```
1. docker compose up -d

2. Redpanda starts → healthcheck passes
3. Redpanda Console starts (depends on Redpanda)
4. ClickHouse starts → runs init.sql (Kafka Engine + MV) → healthcheck passes
5. PostgreSQL starts → runs init.sql (schemas + raw_tickers) → healthcheck passes
6. Producer starts → connects to Binance WS → publishes to Redpanda
7. Consumer starts → reads from Redpanda → bulk-inserts to PostgreSQL
8. ClickHouse auto-ingests from Redpanda via Kafka Engine (no config needed)
9. Dagster starts → loads dbt project → schedules hourly runs
10. Grafana starts → provisions datasources + dashboards
```

**First dbt run:** Dagster triggers the first dbt run ~1 hour after startup (or trigger manually from Dagster UI at `localhost:3000`).

---

## Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Redpanda Console | http://localhost:8080 | none |
| Redpanda Admin API | http://localhost:9644 | none |
| ClickHouse HTTP | http://localhost:8123 | `default` / (from secret) |
| PostgreSQL | `localhost:5432` | `binance` / (from secret) |
| Dagster UI | http://localhost:3000 | none |
| Grafana | http://localhost:3001 | (from secrets) |

---

## Build Order

| Phase | Task | Dependencies |
|-------|------|--------------|
| 1 | Producer (`producer.py`, Dockerfile) | secrets_util.py ✅ |
| 2 | `docker-compose.yml` (Redpanda, ClickHouse, PostgreSQL, Grafana) | — |
| 3 | `clickhouse/init.sql` | — |
| 4 | `postgres/init.sql` | — |
| 5 | Consumer (`consumer.py`, Dockerfile) | secrets_util.py ✅ |
| 6 | dbt project (models, profiles, sources) | PostgreSQL init |
| 7 | Dagster (`definitions.py`, Dockerfile) | dbt project |
| 8 | Grafana provisioning (datasources, dashboards) | ClickHouse + PostgreSQL |
| 9 | Scripts (`start.bat`, `status.bat`, `health_check.sh`) | All above |
| 10 | `README.md` | All above |

---

## Future Enhancements

- **Schema Registry:** Enforce Avro/Protobuf schemas via Redpanda Schema Registry
- **Partitioning:** PostgreSQL table partitioning by `trade_time` for faster dbt incremental runs
- **dbt tests:** `not_null`, `unique`, `accepted_values`, freshness checks
- **Dagster sensors:** Consumer lag alerts, ClickHouse freshness, dbt failure Slack notifications
- **CI/CD:** GitHub Actions for `dbt test`, `docker compose build`, linting
- **Multi-symbol dashboards:** Grafana template variables for dynamic symbol filtering
- **Backfill:** Dagster backfill support for historical dbt runs
