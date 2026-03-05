-- ============================================================
-- Raw tickers table (consumer writes here)
-- Two indexes: one for queries, one for dedup.
-- Depends on: 001_schemas.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS raw.raw_tickers (
    id          BIGSERIAL        PRIMARY KEY,
    trade_id    BIGINT           NOT NULL,
    symbol      TEXT             NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    quantity    DOUBLE PRECISION NOT NULL,
    trade_time  TIMESTAMPTZ      NOT NULL,
    event_time  TIMESTAMPTZ      NOT NULL,
    buyer_maker BOOLEAN          NOT NULL,
    ingested_at TIMESTAMPTZ      NOT NULL,
    loaded_at   TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- For dbt incremental scans and Grafana time-range queries
CREATE INDEX IF NOT EXISTS idx_raw_tickers_symbol_time
    ON raw.raw_tickers (symbol, trade_time);

-- For dedup: ON CONFLICT (symbol, trade_id) DO NOTHING
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_tickers_dedup
    ON raw.raw_tickers (symbol, trade_id);
