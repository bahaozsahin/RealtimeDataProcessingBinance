from kafka import KafkaProducer
import websocket
import json
import os
import logging
from dotenv import load_dotenv
import pendulum

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kafka configuration
KAFKA_BROKER_URL = os.getenv("KAFKA_BROKER_URL", "kafka:9092")
KAFKA_TOPIC_BINANCE = os.getenv("KAFKA_TOPIC_BINANCE", "binance-topic")

# Binance configuration
BINANCE_WS_BASE_URL = os.getenv("BINANCE_WS_BASE_URL", "wss://stream.binance.com:9443/ws/")
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "BTCUSDT")
BINANCE_STREAM_TYPE = os.getenv("BINANCE_STREAM_TYPE", "ticker")

class BinanceKafkaProducer:
    def __init__(self):
        self.producer = None
        self.ws = None
        self.reconnect_interval = 30
        self.max_retries = 5
        self.start_time = pendulum.now('UTC')
        self.last_message_time = None
        
    def create_kafka_producer(self):
        """Create Kafka producer with retry logic"""
        for attempt in range(self.max_retries):
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=[KAFKA_BROKER_URL],
                    value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                    key_serializer=lambda x: x.encode('utf-8') if x else None,
                    retries=3,
                    acks='all',
                    compression_type='gzip'
                )
                logger.info(f"Successfully connected to Kafka at {KAFKA_BROKER_URL}")
                return True
            except Exception as e:
                logger.error(f"Failed to connect to Kafka (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    pendulum.now().add(seconds=5)  # Wait 5 seconds
                    import time
                    time.sleep(5)
                else:
                    return False
        return False
    
    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            
            # Track message timing
            current_time = pendulum.now('UTC')
            self.last_message_time = current_time
            
            # Calculate uptime
            uptime = current_time - self.start_time
            
            # Add timestamp and metadata
            enriched_data = {
                'timestamp': current_time.to_iso8601_string(),
                'timestamp_unix': current_time.timestamp(),
                'timestamp_human': current_time.format('YYYY-MM-DD HH:mm:ss'),
                'symbol': BINANCE_SYMBOL,
                'stream_type': BINANCE_STREAM_TYPE,
                'data': data,
                'metadata': {
                    'producer_uptime_seconds': uptime.total_seconds(),
                    'producer_uptime_human': uptime.in_words(),
                    'timezone': str(current_time.timezone),
                    'day_of_week': current_time.format('dddd'),
                    'hour_of_day': current_time.hour,
                    'is_weekend': current_time.day_of_week in [6, 7],
                    'market_session': self._get_market_session(current_time)
                }
            }
            
            # Send to Kafka
            self.producer.send(
                KAFKA_TOPIC_BINANCE,
                key=BINANCE_SYMBOL,
                value=enriched_data
            )
            
            logger.info(f"Sent message to Kafka: {BINANCE_SYMBOL} - Price: {data.get('c', 'N/A')} - "
                       f"Time: {current_time.format('HH:mm:ss')} - Uptime: {uptime.in_words()}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _get_market_session(self, dt):
        """Determine market session based on time"""
        hour = dt.hour
        if 0 <= hour < 8:
            return "asian"
        elif 8 <= hour < 16:
            return "european"
        elif 16 <= hour < 24:
            return "american"
        else:
            return "unknown"
    
    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
        logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
        import time
        time.sleep(self.reconnect_interval)
        self.connect()
    
    def on_open(self, ws):
        """Handle WebSocket open"""
        logger.info(f"WebSocket connection opened for {BINANCE_SYMBOL}")
    
    def connect(self):
        """Connect to Binance WebSocket"""
        if not self.create_kafka_producer():
            logger.error("Failed to create Kafka producer. Exiting.")
            return
        
        # Create WebSocket URL
        stream_name = f"{BINANCE_SYMBOL.lower()}@{BINANCE_STREAM_TYPE}"
        ws_url = f"{BINANCE_WS_BASE_URL}{stream_name}"
        
        logger.info(f"Connecting to Binance WebSocket: {ws_url}")
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Start WebSocket connection
        self.ws.run_forever()
    
    def close(self):
        """Close connections"""
        if self.producer:
            self.producer.close()
        if self.ws:
            self.ws.close()

def main():
    producer = BinanceKafkaProducer()
    
    try:
        producer.connect()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        producer.close()

if __name__ == "__main__":
    main()