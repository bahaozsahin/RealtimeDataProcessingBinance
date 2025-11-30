"""
Superset configuration for Binance Real-time Data Processing
"""
import os
import pendulum

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://superset:superset@postgres:5432/superset')
SQLALCHEMY_DATABASE_URI = DATABASE_URL

# Redis configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379')

# Cache configuration
CACHE_CONFIG = {
    'CACHE_TYPE': 'RedisCache',
    'CACHE_DEFAULT_TIMEOUT': int(pendulum.duration(minutes=5).total_seconds()),
    'CACHE_KEY_PREFIX': 'superset_',
    'CACHE_REDIS_URL': REDIS_URL,
}

# Celery configuration
CELERY_CONFIG = {
    'broker_url': REDIS_URL,
    'result_backend': REDIS_URL,
    'task_always_eager': False,
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'UTC',
    'enable_utc': True,
    'task_routes': {
        'superset.sql_lab': {
            'queue': 'sql_lab',
        },
    },
    # Enhanced with Pendulum for better time handling
    'beat_schedule': {
        'cleanup-old-logs': {
            'task': 'superset.tasks.cleanup_old_logs',
            'schedule': pendulum.duration(hours=24).total_seconds(),
        },
    },
}

# Feature flags
FEATURE_FLAGS = {
    'ENABLE_TEMPLATE_PROCESSING': True,
    'ALERT_REPORTS': True,
    'DASHBOARD_NATIVE_FILTERS': True,
    'DASHBOARD_CROSS_FILTERS': True,
    'GLOBAL_ASYNC_QUERIES': False,  # Disable async queries to avoid JWT issues
    'VERSIONED_EXPORT': True,
    'EMBEDDED_SUPERSET': True,
}

# Security
SECRET_KEY = os.getenv('SUPERSET_SECRET_KEY', 'binance_realtime_data_processing_jwt_secret_key_2025_very_long_and_secure_random_string_for_production')
WTF_CSRF_ENABLED = True
WTF_CSRF_TIME_LIMIT = None

# JWT Configuration for async queries
JWT_ACCESS_TOKEN_EXPIRES = pendulum.duration(days=1)
JWT_REFRESH_TOKEN_EXPIRES = pendulum.duration(days=30)
SUPERSET_WEBSERVER_TIMEOUT = int(pendulum.duration(minutes=5).total_seconds())

# Disable async query manager to avoid JWT issues
GLOBAL_ASYNC_QUERIES_TRANSPORT = 'polling'
GLOBAL_ASYNC_QUERIES_REDIS_CONFIG = None
GLOBAL_ASYNC_QUERIES_REDIS_STREAM_PREFIX = None
ASYNC_QUERY_MANAGER_CLASS = None

# Session configuration
PERMANENT_SESSION_LIFETIME = pendulum.duration(hours=24)

# File upload configuration
UPLOAD_FOLDER = '/app/superset_home/uploads/'
UPLOAD_CHUNK_SIZE = 4096

# SQL Lab configuration
SQL_MAX_ROW = 100000
SQLLAB_TIMEOUT = int(pendulum.duration(minutes=5).total_seconds())
SQLLAB_ASYNC_TIME_LIMIT_SEC = int(pendulum.duration(minutes=10).total_seconds())

# Authentication
AUTH_TYPE = 1  # Flask-AppBuilder AUTH_DB
AUTH_USER_REGISTRATION = False
AUTH_USER_REGISTRATION_ROLE = "Public"

# Logging
ENABLE_PROXY_FIX = True
LOG_LEVEL = 'INFO'

# Custom CSS
CUSTOM_CSS = """
.navbar-brand {
    font-weight: bold;
    color: #f7931a !important;
}
"""

# Dashboard configuration
DASHBOARD_AUTO_REFRESH_INTERVALS = [
    [int(pendulum.duration(seconds=10).total_seconds()), '10 seconds'],
    [int(pendulum.duration(seconds=30).total_seconds()), '30 seconds'],
    [int(pendulum.duration(minutes=1).total_seconds()), '1 minute'],
    [int(pendulum.duration(minutes=2).total_seconds()), '2 minutes'],
    [int(pendulum.duration(minutes=5).total_seconds()), '5 minutes'],
    [int(pendulum.duration(minutes=10).total_seconds()), '10 minutes'],
    [int(pendulum.duration(minutes=30).total_seconds()), '30 minutes'],
    [int(pendulum.duration(hours=1).total_seconds()), '1 hour'],
]

# Enable time picker
DEFAULT_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# Pendulum-specific configuration
PENDULUM_TIMEZONE = 'UTC'
PENDULUM_LOCALE = 'en'

# Time-based configuration using Pendulum
TIME_GRAIN_FUNCTIONS = {
    'PT1S': 'DATE_TRUNC(\'second\', {col})',
    'PT1M': 'DATE_TRUNC(\'minute\', {col})',
    'PT1H': 'DATE_TRUNC(\'hour\', {col})',
    'P1D': 'DATE_TRUNC(\'day\', {col})',
    'P1W': 'DATE_TRUNC(\'week\', {col})',
    'P1M': 'DATE_TRUNC(\'month\', {col})',
    'P1Y': 'DATE_TRUNC(\'year\', {col})',
}

# Enhanced time range options for crypto trading
COMMON_TIME_RANGES = {
    'Last 5 minutes': f'No filter (last {int(pendulum.duration(minutes=5).total_seconds())} seconds)',
    'Last 15 minutes': f'No filter (last {int(pendulum.duration(minutes=15).total_seconds())} seconds)',
    'Last 30 minutes': f'No filter (last {int(pendulum.duration(minutes=30).total_seconds())} seconds)',
    'Last 1 hour': f'No filter (last {int(pendulum.duration(hours=1).total_seconds())} seconds)',
    'Last 4 hours': f'No filter (last {int(pendulum.duration(hours=4).total_seconds())} seconds)',
    'Last 24 hours': f'No filter (last {int(pendulum.duration(hours=24).total_seconds())} seconds)',
    'Last 7 days': f'No filter (last {int(pendulum.duration(days=7).total_seconds())} seconds)',
}
