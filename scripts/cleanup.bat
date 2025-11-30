@echo off
echo Cleaning up Real-time Data Processing Pipeline...
echo ==========================================

echo Stopping all services...
docker-compose down

echo Removing all containers...
docker-compose down --remove-orphans

echo Removing volumes (this will delete all data)...
docker-compose down -v

echo Removing any orphaned containers...
docker container prune -f

echo Removing unused Docker resources...
docker system prune -f

echo Removing custom networks...
docker network prune -f

echo Removing any dangling images...
docker image prune -f

echo Checking for any remaining containers...
docker ps -a

echo.
echo ==========================================
echo Cleanup complete. You can now start fresh with start.bat
echo Note: All data has been removed including ZooKeeper and Kafka data
pause
