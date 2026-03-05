-- ============================================================
-- Materialized View (auto-pipes Kafka Engine → ReplacingMergeTree)
-- Transforms epoch-ms to DateTime64, casts string prices to Float64.
-- Depends on: 001_kafka_engine.sql, 002_replacing_merge_tree.sql
-- ============================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS binance_mv TO binance_tickers AS
SELECT
    trade_id,
    symbol,
    toFloat64(price)                        AS price,
    toFloat64(quantity)                     AS quantity,
    toDateTime64(timestamp / 1000, 3)       AS trade_time,
    toDateTime64(event_time / 1000, 3)      AS event_time,
    buyer_maker,
    parseDateTimeBestEffort(ingested_at)    AS ingested_at
FROM binance_queue;
