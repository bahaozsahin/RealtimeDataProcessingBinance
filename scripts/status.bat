@echo off
echo ==========================================
echo Real-time Data Processing Pipeline Status
echo ==========================================
echo.

echo Checking services...
docker-compose ps

echo.
echo ==========================================
echo Application Access URLs:
echo ==========================================
echo.
echo Apache Pinot Controller: http://localhost:9000
echo Apache Pinot Broker:     http://localhost:8099
echo Apache Pinot Server:     http://localhost:8098
echo Apache Superset:         http://localhost:8088
echo.

echo ==========================================
echo Kafka Topics:
echo ==========================================
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --list

echo.
echo ==========================================
echo Producer Status:
echo ==========================================
docker logs kafka-producer --tail 5

echo.
echo ==========================================
echo Transformer Status:
echo ==========================================
docker logs kafka-transformer --tail 5

echo.
echo ==========================================
echo Pipeline is ready! You can access:
echo - Pinot Console: http://localhost:9000
echo - Superset: http://localhost:8088
echo ==========================================
pause
