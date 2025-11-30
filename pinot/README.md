# Pinot Configuration

This directory contains the clean, streamlined Pinot configuration for the Binance real-time data processing pipeline.

## Files Overview

### Core Configuration Files
- `binance_schema.json` - Single, comprehensive schema definition
- `binance_table.json` - Single, optimized REALTIME table configuration (`binance_realtime`)
- `setup.sh` - Creates the schema only (table must be created manually or via API)
- `cleanup.sh` - Cleanup script to remove existing schema and table
- `health_check.sh` - Health check and validation script

### Schema Structure

The `binance_realtime` schema includes:

**Dimension Fields:**
- `symbol` - Trading pair symbol (e.g., BTCUSDT)
- `stream_type` - Type of data stream
- `original_timestamp` - Original timestamp from source
- `day_name` - Day of the week name
- `timezone` - Timezone information
- `transformer_version` - Version of the transformer

**Metric Fields:**
- `price` - Current price
- `volume` - 24h volume
- `high_24h`, `low_24h` - 24h high/low prices
- `price_change_24h`, `price_change_percent_24h` - 24h price changes
- `weighted_avg_price` - Weighted average price
- `prev_close_price`, `open_price` - Previous close and open prices
- `bid_price`, `ask_price` - Current bid/ask prices
- `count` - Number of trades
- `processing_latency_ms` - Processing latency in milliseconds
- Time-based fields: `hour_of_day`, `day_of_week`, `quarter`, `week_of_year`
- Boolean fields: `is_weekend`, `is_market_hours`
- Technical indicators: `price_change`, `price_change_percent`, `sma_5`, `sma_20`, `volatility`, `min_10`, `max_10`

**DateTime Fields:**
- `timestamp_unix` - Unix timestamp (primary time column)

### Table Configuration

The table is configured for:
- **Real-time ingestion** from Kafka topic `transformed-topic`
- **Optimized indexing** with inverted indexes on `symbol` and `stream_type`
- **Bloom filters** on `symbol` for fast lookups
- **Sorted by timestamp** for efficient time-based queries
- **Automatic segmentation** with configurable thresholds

## Usage

### Setup
```bash
# Run the setup script to create schema (table is created separately)
./setup.sh

# Create the REALTIME table after schema is ready
curl -X POST "http://pinot-controller:9000/tables" \
  -H "Content-Type: application/json" \
  -d @binance_table.json
```

### Cleanup
```bash
# Clean up existing schema and table
./cleanup.sh
```

### Health Check
```bash
# Check system health and validate configuration
./health_check.sh
```

## Data Flow

1. **Kafka Producer** sends raw Binance data to `binance-topic`
2. **Kafka Transformer** processes and flattens the data, sends to `transformed-topic`
3. **Pinot** consumes from `transformed-topic` using this configuration
4. **Superset** queries Pinot for visualization

## Key Changes Made

1. **Consolidated multiple conflicting schema files** into a single, comprehensive schema
2. **Flattened nested data structures** for better Pinot performance
3. **Added proper indexing** for common query patterns
4. **Optimized time handling** with proper timestamp configuration
5. **Added data validation** and error handling
6. **Included comprehensive monitoring** and health check capabilities

## Troubleshooting

- If you see schema/table conflicts, run `cleanup.sh` first
- Check `health_check.sh` output for system status
- Verify Kafka topics are receiving data before debugging Pinot
- Check transformer logs for data format issues
