#!/bin/bash

# Pinot Cleanup Script
echo "=== Pinot Cleanup Script ==="

# Delete existing table
echo "Deleting existing table..."
curl -X DELETE "http://pinot-controller:9000/tables/binance_realtime" 2>/dev/null || true

# Delete existing schema
echo "Deleting existing schema..."
curl -X DELETE "http://pinot-controller:9000/schemas/binance_realtime" 2>/dev/null || true

# Wait for cleanup
echo "Waiting for cleanup to complete..."
sleep 5

# Verify cleanup
echo "Verifying cleanup..."
echo "Remaining schemas:"
curl -s "http://pinot-controller:9000/schemas" | python3 -m json.tool

echo "Remaining tables:"
curl -s "http://pinot-controller:9000/tables" | python3 -m json.tool

echo "=== Cleanup Complete ==="
