-- ============================================================
-- Kafka Engine (virtual table — reads from Redpanda)
-- Rows are consumed once and piped through MV in 003.
-- ============================================================

CREATE TABLE IF NOT EXISTS binance_queue (
    trade_id     UInt64,
    symbol       String,
    price        String,
    quantity     String,
    timestamp    UInt64,
    event_time   UInt64,
    buyer_maker  UInt8,
    ingested_at  String
) ENGINE = Kafka
SETTINGS
    kafka_broker_list     = 'redpanda:29092',
    kafka_topic_list      = 'binance-tickers',
    kafka_group_name      = 'clickhouse-consumer',
    kafka_format          = 'JSONEachRow',
    kafka_num_consumers   = 1;
