-- ============================================================
-- ReplacingMergeTree storage (final deduped table)
-- ORDER BY (symbol, trade_id) is the dedup key.
-- ReplacingMergeTree(event_time) keeps the row with the latest
-- event_time for each (symbol, trade_id) on background merge.
-- For guaranteed dedup at query time, use FINAL keyword.
-- ============================================================

CREATE TABLE IF NOT EXISTS binance_tickers (
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
TTL trade_time + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;
