# Real-time Data Processing Pipeline - Troubleshooting Guide

## Common ZooKeeper Issues

### 1. "Len error 1195725856" - Protocol Error
**Symptom**: ZooKeeper logs show protocol errors with large numbers
**Cause**: Network communication issues or protocol mismatches
**Solutions**:
- Run `scripts\cleanup.bat` to remove all containers and volumes
- Ensure no other ZooKeeper instances are running on port 2181
- Check Docker Desktop is allocated enough memory (minimum 4GB)
- Verify no firewall is blocking Docker internal networking

### 2. ZooKeeper Connection Timeout
**Symptom**: Services can't connect to ZooKeeper on port 2181
**Cause**: Service startup timing or network issues
**Solutions**:
- Wait longer for ZooKeeper to fully start (can take 30-60 seconds)
- Check ZooKeeper logs: `docker logs binance-zookeeper`
- Verify ZooKeeper is listening: `docker exec binance-zookeeper netstat -tlnp`

### 3. Kafka Broker Issues
**Symptom**: Kafka fails to start or connect to ZooKeeper
**Cause**: ZooKeeper not ready or network issues
**Solutions**:
- Ensure ZooKeeper is running and healthy first
- Check Kafka logs: `docker logs binance-kafka`
- Verify Kafka can reach ZooKeeper: `docker exec binance-kafka ping zookeeper`

### 4. Pinot Cluster Formation
**Symptom**: Pinot controller/broker fails to start
**Cause**: ZooKeeper not ready or Pinot configuration issues
**Solutions**:
- Wait for ZooKeeper and Kafka to be fully ready
- Check Pinot logs: `docker logs binance-pinot-controller`
- Verify Pinot can reach ZooKeeper: `docker exec binance-pinot-controller ping zookeeper`

## Startup Best Practices

### 1. Always Use Cleanup First
```batch
scripts\cleanup.bat
```
This ensures no leftover containers or volumes cause conflicts.

### 2. Monitor Startup Process
```batch
scripts\start.bat
```
Wait for each service to show "healthy" status before proceeding.

### 3. Check Service Health
```batch
scripts\debug.bat
```
Use this to monitor logs and verify each service is working.

### 4. Service Startup Order
The services start in this order (managed by Docker Compose):
1. ZooKeeper (30-60 seconds)
2. Kafka (waits for ZooKeeper)
3. Pinot Controller & Broker (waits for ZooKeeper)
4. Application Services (waits for Kafka & Pinot)

## Common Commands

### Check Service Status
```batch
docker-compose ps
```

### View Specific Service Logs
```batch
docker logs binance-zookeeper
docker logs binance-kafka
docker logs binance-pinot-controller
docker logs binance-producer
```

### Check Network Connectivity
```batch
docker exec binance-kafka ping zookeeper
docker exec binance-pinot-controller ping kafka
```

### Restart Single Service
```batch
docker-compose restart zookeeper
docker-compose restart kafka
```

## Memory Requirements

- **Minimum**: 4GB RAM allocated to Docker Desktop
- **Recommended**: 6GB+ RAM for smooth operation
- **ZooKeeper**: 1GB heap
- **Kafka**: 1GB heap  
- **Pinot**: 2GB heap
- **Superset**: 1GB+ depending on usage

## Port Usage

- **ZooKeeper**: 2181 (internal), 2888, 3888
- **Kafka**: 9092 (internal), 9093 (external)
- **Pinot Controller**: 9000
- **Pinot Broker**: 8099
- **Superset**: 8088
- **PostgreSQL**: 5432
- **Redis**: 6379

## If All Else Fails

1. **Complete Docker Reset**:
```batch
scripts\cleanup.bat
docker system prune -a --volumes
```

2. **Restart Docker Desktop**

3. **Check Docker Desktop Settings**:
   - Resources > Advanced > Memory: Set to 6GB+
   - Resources > Advanced > CPUs: Set to 4+
   - Ensure "Use Docker Compose V2" is enabled

4. **Verify System Resources**:
   - Close other applications using lots of memory
   - Check available disk space (need 10GB+)
