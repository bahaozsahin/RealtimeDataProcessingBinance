FROM python:3.12-slim

LABEL description="Binance WebSocket Producer"

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root user
RUN addgroup --system app && adduser --system --ingroup app app
USER app

CMD ["python", "producer.py"]
