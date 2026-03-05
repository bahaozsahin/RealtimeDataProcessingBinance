-- ============================================================
-- Permissions for the binance user
-- (binance is the POSTGRES_USER created by the container entrypoint)
-- Depends on: 001_schemas.sql, 002_raw_tickers.sql
-- ============================================================

-- Schema usage
GRANT USAGE  ON SCHEMA raw          TO binance;
GRANT USAGE  ON SCHEMA staging      TO binance;
GRANT USAGE  ON SCHEMA intermediate TO binance;
GRANT USAGE  ON SCHEMA gold         TO binance;

-- Existing tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw          TO binance;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA staging      TO binance;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA intermediate TO binance;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gold         TO binance;

-- Future tables created by dbt
ALTER DEFAULT PRIVILEGES IN SCHEMA staging      GRANT ALL ON TABLES TO binance;
ALTER DEFAULT PRIVILEGES IN SCHEMA intermediate GRANT ALL ON TABLES TO binance;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold         GRANT ALL ON TABLES TO binance;

-- Sequences for BIGSERIAL
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw TO binance;
