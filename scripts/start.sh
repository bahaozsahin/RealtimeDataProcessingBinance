#!/bin/bash

# Real-time Data Processing with Binance - Startup Script

echo "🚀 Starting Real-time Data Processing Pipeline..."
echo "=========================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.example to .env and configure your settings."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running!"
    echo "Please start Docker and try again."
    exit 1
fi

# Clean up any existing containers
echo "🧹 Cleaning up existing containers..."
docker-compose down -v

# Pull latest images
echo "📥 Pulling latest images..."
docker-compose pull

# Build custom images
echo "🔨 Building custom images..."
docker-compose build

# Start services
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 30

# Check service health
echo "🏥 Checking service health..."
docker-compose ps

echo ""
echo "✅ Pipeline started successfully!"
echo "=========================================="
echo "🎛️  Access Points:"
echo "   • Superset Dashboard: http://localhost:8088 (admin/admin123)"
echo "   • Pinot Controller: http://localhost:9000"
echo "   • Pinot Broker: http://localhost:8099"
echo "   • Kafka (external): localhost:9092"
echo ""
echo "📊 Monitor logs with:"
echo "   docker-compose logs -f [service-name]"
echo ""
echo "🛑 Stop pipeline with:"
echo "   docker-compose down"
echo "=========================================="
