# Superset Sample Dashboard Queries

Below are sample SQL queries you can use in Superset to create visualizations for your Binance real-time data:

## 1. Real-time Price Line Chart
```sql
SELECT 
    timestamp,
    price
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC
LIMIT 1000
```

## 2. Price with Moving Averages
```sql
SELECT 
    timestamp,
    price,
    sma_5,
    sma_20
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
  AND sma_5 IS NOT NULL
  AND sma_20 IS NOT NULL
ORDER BY timestamp DESC
LIMIT 500
```

## 3. Volume Over Time
```sql
SELECT 
    timestamp,
    volume
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC
LIMIT 1000
```

## 4. Price Change Distribution
```sql
SELECT 
    price_change_percent,
    COUNT(*) as frequency
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
  AND price_change_percent IS NOT NULL
GROUP BY price_change_percent
ORDER BY price_change_percent
```

## 5. High/Low Price Bands
```sql
SELECT 
    timestamp,
    high_24h,
    low_24h,
    price
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC
LIMIT 1000
```

## 6. Market Hours Analysis
```sql
SELECT 
    is_market_hours,
    AVG(price) as avg_price,
    AVG(volume) as avg_volume,
    AVG(volatility) as avg_volatility,
    COUNT(*) as message_count
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
GROUP BY is_market_hours
```

## 7. Weekend vs Weekday Performance
```sql
SELECT 
    is_weekend,
    day_name,
    AVG(price_change_percent) as avg_price_change,
    AVG(volume) as avg_volume,
    COUNT(*) as trades
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
GROUP BY is_weekend, day_name
ORDER BY is_weekend, day_name
```

## 8. Processing Latency Analysis
```sql
SELECT 
    hour_of_day,
    AVG(processing_latency_ms) as avg_latency_ms,
    MAX(processing_latency_ms) as max_latency_ms,
    MIN(processing_latency_ms) as min_latency_ms,
    COUNT(*) as message_count
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
GROUP BY hour_of_day
ORDER BY hour_of_day
```

## 9. Quarterly Performance
```sql
SELECT 
    quarter,
    AVG(price) as avg_price,
    MIN(price) as min_price,
    MAX(price) as max_price,
    AVG(volume) as avg_volume
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
GROUP BY quarter
ORDER BY quarter
```

## 10. Hourly Trading Patterns
```sql
SELECT 
    hour_of_day,
    day_name,
    AVG(price) as avg_price,
    AVG(volume) as avg_volume,
    COUNT(*) as activity_count
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
GROUP BY hour_of_day, day_name
ORDER BY hour_of_day, day_name
```

## 7. Real-time KPIs with Time Context
```sql
SELECT 
    price as current_price,
    price_change_24h,
    price_change_percent_24h,
    volume,
    high_24h,
    low_24h,
    volatility,
    processing_latency_ms,
    day_name,
    hour_of_day,
    is_market_hours,
    is_weekend
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC
LIMIT 1
```

## 8. Bid-Ask Spread Analysis
```sql
SELECT 
    timestamp,
    bid_price,
    ask_price,
    (ask_price - bid_price) as spread,
    ((ask_price - bid_price) / bid_price) * 100 as spread_percent
FROM binance_realtime 
WHERE symbol = 'BTCUSDT'
ORDER BY timestamp DESC
LIMIT 1000
```

## Dashboard Layout Suggestions:

1. **Real-time Price** - Line chart with timestamp on x-axis, price on y-axis
2. **Technical Indicators** - Multi-line chart showing price, SMA5, SMA20
3. **Volume** - Bar chart or area chart
4. **Current KPIs** - Big number charts for current price, 24h change, volume
5. **Volatility** - Gauge chart or line chart
6. **Price Distribution** - Histogram of price changes
7. **High/Low Bands** - Area chart showing price within daily bands
8. **Bid-Ask Spread** - Line chart showing spread over time

## Chart Types to Use:
- **Line Chart**: Price movements, moving averages, volatility, processing latency
- **Area Chart**: Volume, price bands
- **Bar Chart**: Volume, frequency distributions, hourly patterns
- **Big Number**: Current price, 24h change percentage, processing latency
- **Gauge**: Volatility, spread percentage
- **Histogram**: Price change distribution
- **Heatmap**: Time-based patterns (hour vs day), volatility patterns
- **Pie Chart**: Market hours vs off-hours distribution
- **Scatter Plot**: Price vs volume correlation

## Filters to Add:
- **Time Range**: Last 1 hour, 6 hours, 24 hours
- **Symbol**: Allow switching between different cryptocurrencies
- **Market Hours**: Filter by market hours vs off-hours
- **Weekdays vs Weekends**: Compare trading patterns
- **Processing Latency**: Filter by latency thresholds
- **Refresh Rate**: 10 seconds, 30 seconds, 1 minute for real-time updates

## Pendulum-Enhanced Features:
- **Timezone Awareness**: All timestamps are properly timezone-aware
- **Human-Readable Time**: Uptime and intervals in human-readable format
- **Market Session Detection**: Automatic detection of Asian/European/American trading sessions
- **Processing Latency**: Track real-time processing performance
- **Time-based Analytics**: Quarter, week, day-of-week analysis for better insights
