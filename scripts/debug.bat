@echo off
echo Debugging Real-time Data Processing Pipeline...
echo ==========================================

echo.
echo == Service Status ==
docker-compose ps

echo.
echo == Checking ZooKeeper ==
docker exec zookeeper bash -c "echo 'ruok' | nc localhost 2181"

echo.
echo == Checking Kafka ==
docker exec kafka bash -c "kafka-topics --bootstrap-server localhost:9092 --list"

echo.
echo == Checking Pinot Controller ==
curl -s http://localhost:9000/health || echo "Pinot Controller not accessible"

echo.
echo == Checking Pinot Broker ==
curl -s http://localhost:8099/health || echo "Pinot Broker not accessible"

echo.
echo == Checking Pinot Server ==
curl -s http://localhost:8098/health || echo "Pinot Server not accessible"

echo.
echo == Checking Superset ==
curl -s http://localhost:8088/health || echo "Superset not accessible"

echo.
echo == Recent Logs from Failed Services ==
echo.
echo "=== Pinot Controller Logs (last 20 lines) ==="
docker logs --tail 20 pinot-controller

echo.
echo "=== Pinot Server Logs (last 20 lines) ==="
docker logs --tail 20 pinot-server

echo.
echo "=== Superset Logs (last 20 lines) ==="
docker logs --tail 20 superset

echo.
echo ==========================================
echo Debug complete. Check the output above for issues.
pause
