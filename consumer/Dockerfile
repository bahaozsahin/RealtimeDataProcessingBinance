FROM python:3.12-slim

LABEL description="Binance Redpanda → PostgreSQL Consumer"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching)
COPY consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities and application code
COPY shared/ ./shared/
COPY consumer/ .

# Run as non-root user
RUN addgroup --system app && adduser --system --ingroup app app
USER app

CMD ["python", "consumer.py"]
