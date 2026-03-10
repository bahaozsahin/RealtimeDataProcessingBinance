"""
Binance WebSocket Producer.

Connects to the Binance WebSocket API, receives real-time trade/ticker data,
and publishes JSON messages to a Redpanda topic via aiokafka.

Features:
    - Multi-symbol streaming (configurable via Docker secret)
    - Exponential backoff reconnect (1s → 60s, with jitter)
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

import orjson
import websockets
from aiokafka import AIOKafkaProducer

from shared.logging_config import setup_logging
from shared.secrets_util import read_secret, read_secret_raw

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_LEVEL = read_secret_raw("log_level", default="INFO")
logger = setup_logging("producer", LOG_LEVEL)

# ── Configuration ────────────────────────────────────────────────────────────

SYMBOLS = read_secret("symbols", default="btcusdt,ethusdt,solusdt,bnbusdt,xrpusdt")
STREAM_TYPE = read_secret_raw("stream_type", default="trade")
BROKER = read_secret("redpanda_broker", default="redpanda:9092")
TOPIC = read_secret_raw("topic", default="binance-tickers")

# Binance WebSocket base URL
BINANCE_WS_BASE = "wss://stream.binance.com:9443"

# Reconnect settings
RECONNECT_BASE_DELAY = 1.0  # seconds
RECONNECT_MAX_DELAY = 60.0  # seconds
RECONNECT_JITTER = 0.5  # ±50% jitter

# ── Helpers ──────────────────────────────────────────────────────────────────


def build_ws_url(symbols: list[str], stream_type: str) -> str:
    """Build the Binance combined WebSocket stream URL.

    Example: wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade
    """
    streams = "/".join(f"{s.lower()}@{stream_type}" for s in symbols)
    return f"{BINANCE_WS_BASE}/stream?streams={streams}"


def parse_trade_message(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Extract relevant fields from a Binance trade WebSocket message.

    Returns None if the message is not a valid trade event.
    """
    data = raw.get("data")
    if not data or data.get("e") != "trade":
        return None

    return {
        "trade_id": data["t"],
        "symbol": data["s"],
        "price": data["p"],
        "quantity": data["q"],
        "timestamp": data["T"],
        "event_time": data["E"],
        "buyer_maker": data["m"],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_ticker_message(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Extract relevant fields from a Binance 24hr ticker message.

    Returns None if the message is not a valid ticker event.
    Handles both @ticker (24hrTicker) and @miniTicker (24hrMiniTicker) events.
    """
    data = raw.get("data")
    if not data or data.get("e") not in ("24hrTicker", "24hrMiniTicker"):
        return None

    return {
        "trade_id": data["E"],  # no trade ID for tickers, use event time as pseudo-ID
        "symbol": data["s"],
        "price": data["c"],  # close price
        "quantity": data["v"],  # total traded base asset volume
        "timestamp": data["E"],
        "event_time": data["E"],
        "buyer_maker": False,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


PARSERS = {
    "trade": parse_trade_message,
    "ticker": parse_ticker_message,
    "miniTicker": parse_ticker_message,
}


def parse_message(raw: dict[str, Any], stream_type: str) -> dict[str, Any] | None:
    """Route to the correct parser based on stream type."""
    parser = PARSERS.get(stream_type, parse_trade_message)
    return parser(raw)


# ── Producer ─────────────────────────────────────────────────────────────────


class BinanceProducer:
    """Manages the Binance WebSocket connection and Kafka producer lifecycle."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._producer: AIOKafkaProducer | None = None
        self._msg_count: int = 0
        self._error_count: int = 0
        self._start_time: float = time.monotonic()

    # ── Kafka ────────────────────────────────────────────────────────────

    async def _start_kafka(self) -> AIOKafkaProducer:
        """Create and start the aiokafka producer."""
        producer = AIOKafkaProducer(
            bootstrap_servers=BROKER.get(),
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
            linger_ms=50,
            max_batch_size=65536,
            compression_type="lz4",
        )
        await producer.start()
        logger.info("Kafka producer connected to broker")
        return producer

    async def _stop_kafka(self) -> None:
        """Flush and stop the Kafka producer."""
        if self._producer:
            await self._producer.flush()
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    # ── WebSocket ────────────────────────────────────────────────────────

    async def _stream(self) -> None:
        """Connect to Binance WS and stream messages to Kafka.

        Reconnects automatically with exponential backoff + jitter.
        """
        symbol_list = SYMBOLS.split(",")
        url = build_ws_url(symbol_list, STREAM_TYPE)
        attempt = 0

        logger.info(
            "Starting stream: symbols=%s, stream_type=%s, topic=%s",
            symbol_list,
            STREAM_TYPE,
            TOPIC,
        )

        while not self._shutdown_event.is_set():
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=2**20,  # 1 MB
                ) as ws:
                    logger.info("WebSocket connected to Binance (attempt %d)", attempt + 1)
                    attempt = 0  # reset on successful connection

                    async for raw_msg in ws:
                        if self._shutdown_event.is_set():
                            break

                        try:
                            raw = orjson.loads(raw_msg)
                            parsed = parse_message(raw, STREAM_TYPE)

                            if parsed is None:
                                continue

                            await self._producer.send(
                                TOPIC,
                                value=parsed,
                                key=parsed["symbol"].encode(),
                            )
                            self._msg_count += 1

                            if self._msg_count % 1000 == 0:
                                elapsed = time.monotonic() - self._start_time
                                rate = self._msg_count / elapsed if elapsed > 0 else 0
                                logger.info(
                                    "Progress: %d messages sent (%.1f msg/s, %d errors)",
                                    self._msg_count,
                                    rate,
                                    self._error_count,
                                )

                        except Exception:
                            self._error_count += 1
                            logger.exception("Failed to process message")

            except asyncio.CancelledError:
                logger.info("Stream cancelled")
                break

            except Exception:
                attempt += 1
                self._error_count += 1

                delay = min(
                    RECONNECT_BASE_DELAY * (2 ** (attempt - 1)),
                    RECONNECT_MAX_DELAY,
                )
                # Add jitter: ±50%
                import random

                jitter = delay * RECONNECT_JITTER * (2 * random.random() - 1)
                delay = max(0.1, delay + jitter)

                logger.warning(
                    "WebSocket disconnected (attempt %d), reconnecting in %.1fs",
                    attempt,
                    delay,
                )

                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=delay,
                    )
                    # If we get here, shutdown was requested during backoff
                    break
                except asyncio.TimeoutError:
                    # Backoff done, retry
                    continue

    # ── Lifecycle ────────────────────────────────────────────────────────

    def _handle_signal(self) -> None:
        """Signal handler for graceful shutdown."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    async def run(self) -> None:
        """Main entry point: start Kafka, stream, then cleanup."""
        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_signal)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda *_: self._handle_signal())

        try:
            self._producer = await self._start_kafka()
            await self._stream()
        finally:
            await self._stop_kafka()
            elapsed = time.monotonic() - self._start_time
            logger.info(
                "Producer finished: %d messages sent, %d errors, ran for %.0fs",
                self._msg_count,
                self._error_count,
                elapsed,
            )


# ── Entrypoint ───────────────────────────────────────────────────────────────


def main() -> None:
    """Run the Binance producer."""
    logger.info("Binance Producer starting")
    producer = BinanceProducer()
    asyncio.run(producer.run())


if __name__ == "__main__":
    main()
