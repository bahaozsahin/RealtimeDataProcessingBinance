#!/bin/bash

# Pinot Health Check and Validation Script
echo "=== Pinot Health Check ==="

# Check if Pinot Controller is healthy
echo "Checking Pinot Controller health..."
if curl -f http://pinot-controller:9000/health > /dev/null 2>&1; then
    echo "✓ Pinot Controller is healthy"
else
    echo "✗ Pinot Controller is not responding"
    exit 1
fi

# List existing schemas
echo -e "\n=== Existing Schemas ==="
curl -s "http://pinot-controller:9000/schemas" | python3 -m json.tool

# List existing tables
echo -e "\n=== Existing Tables ==="
curl -s "http://pinot-controller:9000/tables" | python3 -m json.tool

# Check specific schema
echo -e "\n=== Binance Schema Details ==="
curl -s "http://pinot-controller:9000/schemas/binance_realtime" | python3 -m json.tool

# Check specific table
echo -e "\n=== Binance Table Details ==="
curl -s "http://pinot-controller:9000/tables/binance_realtime" | python3 -m json.tool

# Check table status
echo -e "\n=== Table Status ==="
curl -s "http://pinot-controller:9000/tables/binance_realtime/state" | python3 -m json.tool

# Query some recent data
echo -e "\n=== Recent Data Sample ==="
curl -X POST "http://pinot-broker:8099/query/sql" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT symbol, price, volume, timestamp_unix FROM binance_realtime ORDER BY timestamp_unix DESC LIMIT 5"}' | python3 -m json.tool

echo -e "\n=== Health Check Complete ==="
