# Real-time Data Processing with Binance API

Technical guide for the real-time pipeline that ingests Binance WebSocket data, buffers and transforms it in Kafka, persists it in Apache Pinot, and visualizes it in Apache Superset.

## Architecture

```
Binance WebSocket → Kafka Producer → Kafka Transformer → Pinot (schema + table) → Superset
```

**Topics and table**
- Raw topic: `binance-topic`
- Transformed topic: `transformed-topic`
- Pinot REALTIME table: `binance_realtime`

## Project Layout

- `kafka_producer/` – WebSocket client that enriches Binance ticks and pushes to Kafka.
- `kafka_transformer/` – Consumer that flattens data, adds indicators, and publishes to the transformed topic.
- `pinot/` – Pinot schema/table configs and helper scripts.
- `data_viz/superset/` – Superset config, init helper, and sample SQL queries.
- `scripts/` – Helper entrypoints (`start.*`, `cleanup.bat`, `debug.bat`, `status.bat`).
- `docker-compose.yml` – Orchestrates Zookeeper, Kafka, Pinot, Superset, and setup tasks.

## Prerequisites

- Docker + Docker Compose
- ≥4GB RAM available to containers
- Internet access for the Binance WebSocket

## Quick Start

1) **Clone and configure**
```bash
git clone <repository-url>
cd RealtimeDataProcessingBinance
cp .env.example .env
# Edit .env with your values (file is gitignored)
```

2) **Start the stack**
```bash
# Linux/Mac
scripts/start.sh

# Windows
scripts/start.bat
```

3) **Create the Pinot table**  
`pinot-setup` (in Compose) only creates the schema. Create the REALTIME table yourself after services are healthy:
```bash
curl -X POST "http://localhost:9000/tables" \
  -H "Content-Type: application/json" \
  -d @pinot/binance_table.json
```
Then verify in the Pinot UI (http://localhost:9000) that `binance_realtime` exists.

4) **Access services**
- Superset: http://localhost:8088 (admin/admin123 by default)
- Pinot Controller: http://localhost:9000
- Pinot Broker: http://localhost:8099

## Services

**Kafka Producer**
- Connects to Binance WebSocket (symbol/stream configurable via env).
- Publishes enriched JSON messages to `binance-topic`.

**Kafka Transformer**
- Consumes `binance-topic`, adds indicators (SMA5/20, volatility, min/max, price deltas), time metadata, and latency.
- Publishes flattened records to `transformed-topic`.

**Apache Pinot**
- Schema: `pinot/binance_schema.json`
- Table: `pinot/binance_table.json` (REALTIME `binance_realtime`, ingestion from `transformed-topic`, inverted/bloom indexes on `symbol`/`stream_type`).

**Apache Superset**
- Preconfigured container with Postgres/Redis backing.
- `data_viz/superset/init_superset.py` can create the Pinot database connection, dataset, and starter charts (dashboard creation skipped by default; add charts manually).

## Configuration

Key environment variables (see `.env.example`):
- Source: `BINANCE_WS_BASE_URL`, `BINANCE_SYMBOL`, `BINANCE_STREAM_TYPE`
- Kafka: `KAFKA_BROKER_URL`, `KAFKA_TOPIC_BINANCE`, `KAFKA_TOPIC_TRANSFORMED`, `KAFKA_CONSUMER_GROUP_ID`
- Pinot: `PINOT_CONTROLLER_URL`, `PINOT_BROKER_URL`, `PINOT_TABLE_NAME`
- Superset: `SUPERSET_PORT`, `SUPERSET_ADMIN_*`, `SUPERSET_SECRET_KEY`
- General: `LOG_LEVEL`, `PYTHONUNBUFFERED`

Secrets belong only in `.env` (gitignored). Rotate any real keys you place there.

## Operations

- Start: `scripts/start.sh` or `scripts/start.bat`
- Check status: `scripts/status.bat` (Windows) or `docker-compose ps`
- Logs: `docker-compose logs -f <service>`
- Debug helpers: `scripts/debug.bat`
- Cleanup/reset (removes volumes): `scripts/cleanup.bat`

## Troubleshooting

- Kafka connectivity: `docker-compose logs kafka`, ensure ports 9092/29092 reachable inside network.
- Pinot schema/table: `docker-compose logs pinot-setup` for schema, and ensure you POST `pinot/binance_table.json` after startup.
- WebSocket issues: check `kafka-producer` logs for connection errors; confirm outbound network access.

Reset the stack:
```bash
docker-compose down -v
docker-compose up -d
```

## Development

- Transformations: edit `kafka_transformer/transformer.py`, update Pinot schema/table if fields change, then `docker-compose build kafka-transformer`.
- Visualizations: use Superset SQL Lab against `binance_realtime`; sample queries in `data_viz/superset/sample_queries.md`.

## Current ToDos: 
- Kafka transformations are not getting through to Pinot,
- Symbol logic is only allowing 1 at one time,
- More Charts,
- Adding a final dashboard


## Security

- Keep `.env` local (gitignored). Use `.env.example` as the template.
- For production: add auth for Superset, use HTTPS, consider Docker secrets, and secure Kafka/Pinot endpoints.
