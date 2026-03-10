"""
Binance Consumer — Redpanda → PostgreSQL.

Reads JSON messages from a Redpanda topic, accumulates them into batches,
and bulk-inserts into PostgreSQL with ON CONFLICT DO NOTHING for dedup.

Features:
    - Batch accumulation (configurable size / flush interval)
    - Bulk INSERT via asyncpg COPY or executemany
    - Manual Kafka offset commit after successful DB write
    - Graceful shutdown on SIGINT/SIGTERM
    - Structured JSON logging
    - All config from Docker Secrets (no .env)
"""

from __future__ import annotations

import asyncio
import signal
import time
from datetime import datetime, timezone
from typing import Any

import asyncpg
import orjson
from aiokafka import AIOKafkaConsumer

from shared.logging_config import setup_logging
from shared.secrets_util import read_secret, read_secret_raw

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_LEVEL = read_secret_raw("log_level", default="INFO")
logger = setup_logging("consumer", LOG_LEVEL)

# ── Configuration ────────────────────────────────────────────────────────────

BROKER = read_secret("redpanda_broker", default="redpanda:29092")
TOPIC = read_secret_raw("topic", default="binance-tickers")
PG_PASSWORD = read_secret("postgres_password", default="postgres")

# PostgreSQL connection settings
PG_HOST = "postgres"
PG_PORT = 5432
PG_USER = "binance"
PG_DATABASE = "binance_dwh"

# Batching settings
BATCH_SIZE = 1000          # flush after N messages
FLUSH_INTERVAL = 5.0       # flush after N seconds even if batch is small
CONSUMER_GROUP = "pg-consumer"

# ── SQL ──────────────────────────────────────────────────────────────────────

INSERT_SQL = """
    INSERT INTO raw.raw_tickers (
        trade_id, symbol, price, quantity,
        trade_time, event_time, buyer_maker, ingested_at
    )
    SELECT
        x.trade_id, x.symbol, x.price, x.quantity,
        x.trade_time, x.event_time, x.buyer_maker, x.ingested_at
    FROM UNNEST($1::bigint[], $2::text[], $3::double precision[],
                $4::double precision[], $5::timestamptz[],
                $6::timestamptz[], $7::boolean[], $8::timestamptz[])
        AS x(trade_id, symbol, price, quantity,
             trade_time, event_time, buyer_maker, ingested_at)
    ON CONFLICT (symbol, trade_id) DO NOTHING
"""

# ── Helpers ──────────────────────────────────────────────────────────────────


def parse_message(raw_bytes: bytes) -> dict[str, Any] | None:
    """Parse a JSON message from Redpanda into a dict.

    Returns None if the message cannot be parsed.
    """
    try:
        msg = orjson.loads(raw_bytes)
        # Validate required fields exist
        if not all(k in msg for k in ("trade_id", "symbol", "price", "quantity",
                                       "timestamp", "event_time")):
            return None
        return msg
    except (orjson.JSONDecodeError, TypeError):
        return None


def msg_to_row(msg: dict[str, Any]) -> tuple:
    """Convert a parsed message dict to a tuple for bulk insert."""
    return (
        int(msg["trade_id"]),
        str(msg["symbol"]),
        float(msg["price"]),
        float(msg["quantity"]),
        datetime.fromtimestamp(msg["timestamp"] / 1000, tz=timezone.utc),
        datetime.fromtimestamp(msg["event_time"] / 1000, tz=timezone.utc),
        bool(msg.get("buyer_maker", False)),
        datetime.fromisoformat(msg["ingested_at"]) if isinstance(msg.get("ingested_at"), str)
        else datetime.now(timezone.utc),
    )


# ── Consumer ─────────────────────────────────────────────────────────────────


class BinanceConsumer:
    """Reads from Redpanda and bulk-inserts into PostgreSQL."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._consumer: AIOKafkaConsumer | None = None
        self._pool: asyncpg.Pool | None = None
        self._msg_count: int = 0
        self._insert_count: int = 0
        self._error_count: int = 0
        self._start_time: float = time.monotonic()

    # ── Kafka ────────────────────────────────────────────────────────────

    async def _start_kafka(self) -> AIOKafkaConsumer:
        """Create and start the aiokafka consumer."""
        consumer = AIOKafkaConsumer(
            TOPIC,
            bootstrap_servers=BROKER.get(),
            group_id=CONSUMER_GROUP,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: v,  # keep raw bytes
        )
        await consumer.start()
        logger.info("Kafka consumer connected to broker, group=%s", CONSUMER_GROUP)
        return consumer

    async def _stop_kafka(self) -> None:
        """Stop the Kafka consumer."""
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")

    # ── PostgreSQL ───────────────────────────────────────────────────────

    async def _start_pg(self) -> asyncpg.Pool:
        """Create the asyncpg connection pool."""
        pool = await asyncpg.create_pool(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD.get(),
            database=PG_DATABASE,
            min_size=2,
            max_size=5,
        )
        logger.info("PostgreSQL connection pool created (host=%s, db=%s)", PG_HOST, PG_DATABASE)
        return pool

    async def _stop_pg(self) -> None:
        """Close the PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def _bulk_insert(self, rows: list[tuple]) -> int:
        """Bulk-insert rows into raw.raw_tickers.

        Uses UNNEST for efficient batch insert with ON CONFLICT DO NOTHING.
        Returns the number of rows actually inserted (excludes duplicates).
        """
        if not rows:
            return 0

        # Transpose rows into column arrays for UNNEST
        trade_ids = [r[0] for r in rows]
        symbols = [r[1] for r in rows]
        prices = [r[2] for r in rows]
        quantities = [r[3] for r in rows]
        trade_times = [r[4] for r in rows]
        event_times = [r[5] for r in rows]
        buyer_makers = [r[6] for r in rows]
        ingested_ats = [r[7] for r in rows]

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                INSERT_SQL,
                trade_ids, symbols, prices, quantities,
                trade_times, event_times, buyer_makers, ingested_ats,
            )

        # result is like "INSERT 0 42" — parse inserted count
        try:
            inserted = int(result.split()[-1])
        except (ValueError, IndexError):
            inserted = len(rows)

        return inserted

    # ── Consume Loop ─────────────────────────────────────────────────────

    async def _consume_loop(self) -> None:
        """Main consume loop with batch accumulation and periodic flush."""
        batch: list[tuple] = []
        last_flush = time.monotonic()

        logger.info(
            "Starting consume loop: topic=%s, batch_size=%d, flush_interval=%.1fs",
            TOPIC, BATCH_SIZE, FLUSH_INTERVAL,
        )

        try:
            while not self._shutdown_event.is_set():
                # Poll with a short timeout so we can check shutdown and time-based flush
                result = await asyncio.wait_for(
                    self._poll_batch(batch),
                    timeout=1.0,
                )

                now = time.monotonic()
                should_flush = (
                    len(batch) >= BATCH_SIZE
                    or (batch and now - last_flush >= FLUSH_INTERVAL)
                )

                if should_flush:
                    await self._flush(batch)
                    last_flush = time.monotonic()

        except asyncio.CancelledError:
            logger.info("Consume loop cancelled")

        # Final flush on shutdown
        if batch:
            logger.info("Final flush: %d remaining messages", len(batch))
            await self._flush(batch)

    async def _poll_batch(self, batch: list[tuple]) -> None:
        """Poll messages from Kafka and append parsed rows to batch."""
        try:
            msg = await asyncio.wait_for(
                self._consumer.__anext__(),
                timeout=1.0,
            )
        except (asyncio.TimeoutError, StopAsyncIteration):
            return

        parsed = parse_message(msg.value)
        if parsed is None:
            self._error_count += 1
            return

        try:
            row = msg_to_row(parsed)
            batch.append(row)
            self._msg_count += 1
        except (KeyError, ValueError, TypeError):
            self._error_count += 1
            logger.exception("Failed to convert message to row")

    async def _flush(self, batch: list[tuple]) -> None:
        """Flush the current batch to PostgreSQL and commit offsets."""
        if not batch:
            return

        try:
            inserted = await self._bulk_insert(batch)
            self._insert_count += inserted

            # Commit Kafka offset after successful DB write
            await self._consumer.commit()

            elapsed = time.monotonic() - self._start_time
            rate = self._msg_count / elapsed if elapsed > 0 else 0

            logger.info(
                "Flushed %d rows (%d inserted, %d dupes skipped) | "
                "Total: %d consumed, %d inserted, %.1f msg/s, %d errors",
                len(batch),
                inserted,
                len(batch) - inserted,
                self._msg_count,
                self._insert_count,
                rate,
                self._error_count,
            )
        except Exception:
            self._error_count += 1
            logger.exception("Failed to flush batch of %d rows", len(batch))
            # Don't commit offset — messages will be re-delivered (at-least-once)
            return
        finally:
            batch.clear()

    # ── Lifecycle ────────────────────────────────────────────────────────

    def _handle_signal(self) -> None:
        """Signal handler for graceful shutdown."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def run(self) -> None:
        """Main entry point: connect to Kafka + PG, consume, then cleanup."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._handle_signal())

        try:
            self._pool = await self._start_pg()
            self._consumer = await self._start_kafka()
            await self._consume_loop()
        finally:
            await self._stop_kafka()
            await self._stop_pg()
            elapsed = time.monotonic() - self._start_time
            logger.info(
                "Consumer finished: %d consumed, %d inserted, %d errors, ran for %.0fs",
                self._msg_count,
                self._insert_count,
                self._error_count,
                elapsed,
            )


# ── Entrypoint ───────────────────────────────────────────────────────────────


def main() -> None:
    """Run the Binance consumer."""
    logger.info("Binance Consumer starting")
    consumer = BinanceConsumer()
    asyncio.run(consumer.run())


if __name__ == "__main__":
    main()
