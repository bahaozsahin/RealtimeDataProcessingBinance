@echo off
echo Starting Real-time Data Processing Pipeline...
echo ==========================================

REM Check if .env file exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Please copy .env.example to .env and configure your settings.
    pause
    exit /b 1
)

REM Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker is not running!
    echo Please start Docker and try again.
    pause
    exit /b 1
)

REM Clean up any existing containers
echo Cleaning up existing containers...
docker-compose down -v

REM Pull latest images
echo Pulling latest images...
docker-compose pull

REM Build custom images
echo Building custom images...
docker-compose build

REM Start services
echo Starting services...
docker-compose up -d

REM Wait for services to be ready
echo Waiting for services to be ready...
timeout /t 30 /nobreak

REM Check service health
echo Checking service health...
docker-compose ps

echo.
echo Pipeline started successfully!
echo ==========================================
echo Access Points:
echo    * Superset Dashboard: http://localhost:8088 (admin/admin123)
echo    * Pinot Controller: http://localhost:9000
echo    * Pinot Broker: http://localhost:8099
echo    * Kafka (external): localhost:9092
echo.
echo Monitor logs with:
echo    docker-compose logs -f [service-name]
echo.
echo Stop pipeline with:
echo    docker-compose down
echo ==========================================
pause
