#!/bin/bash

echo "Waiting for Pinot cluster to be fully ready..."

# Wait for Pinot Controller to be ready
echo "Checking Pinot controller health..."
while ! curl -f http://pinot-controller:9000/health > /dev/null 2>&1; do
    sleep 5
done

# Delete existing schema and table if they exist
echo "Cleaning up existing schema and table..."
curl -X DELETE "http://pinot-controller:9000/tables/binance_realtime" 2>/dev/null || true
curl -X DELETE "http://pinot-controller:9000/schemas/binance_realtime" 2>/dev/null || true

# Wait a bit for cleanup to complete
sleep 5

# Create schema
echo "Creating Pinot schema..."
curl -X POST "http://pinot-controller:9000/schemas" \
  -H "Content-Type: application/json" \
  -d @/opt/pinot/binance_schema.json

if [ $? -eq 0 ]; then
    echo "Schema created successfully!"
else
    echo "Failed to create schema"
    exit 1
fi

echo "Pinot setup completed! You can now create the table manually through the UI."
