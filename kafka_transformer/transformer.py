from kafka import KafkaConsumer, KafkaProducer
import json
import os
import logging
from dotenv import load_dotenv
import pendulum
import statistics

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
KAFKA_TOPIC_TRANSFORMED = os.getenv("KAFKA_TOPIC_TRANSFORMED", "transformed-topic")
KAFKA_CONSUMER_GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP_ID", "binance-consumer-group")

class BinanceDataTransformer:
    def __init__(self):
        self.consumer = None
        self.producer = None
        self.price_history = []
        self.max_history_length = 100
        
    def create_kafka_connections(self):
        """Create Kafka consumer and producer"""
        try:
            self.consumer = KafkaConsumer(
                KAFKA_TOPIC_BINANCE,
                bootstrap_servers=[KAFKA_BROKER_URL],
                group_id=KAFKA_CONSUMER_GROUP_ID,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True
            )
            
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
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
    
    def calculate_technical_indicators(self, current_price):
        """Calculate basic technical indicators"""
        self.price_history.append(float(current_price))
        
        # Keep only recent history
        if len(self.price_history) > self.max_history_length:
            self.price_history.pop(0)
        
        indicators = {}
        
        if len(self.price_history) >= 2:
            # Price change
            price_change = self.price_history[-1] - self.price_history[-2]
            price_change_pct = (price_change / self.price_history[-2]) * 100
            
            indicators['price_change'] = price_change
            indicators['price_change_percent'] = price_change_pct
        
        if len(self.price_history) >= 5:
            # Simple moving average (5 periods)
            indicators['sma_5'] = statistics.mean(self.price_history[-5:])
        
        if len(self.price_history) >= 20:
            # Simple moving average (20 periods)
            indicators['sma_20'] = statistics.mean(self.price_history[-20:])
            
            # Volatility (standard deviation of last 20 prices)
            indicators['volatility'] = statistics.stdev(self.price_history[-20:])
        
        if len(self.price_history) >= 10:
            # Min/Max in last 10 periods
            recent_prices = self.price_history[-10:]
            indicators['min_10'] = min(recent_prices)
            indicators['max_10'] = max(recent_prices)
        
        return indicators
    
    def transform_message(self, message):
        """Transform incoming Binance message"""
        try:
            # Extract ticker data
            ticker_data = message.get('data', {})
            
            # Get current price
            current_price = float(ticker_data.get('c', 0))
            
            # Calculate technical indicators
            indicators = self.calculate_technical_indicators(current_price)
            
            # Parse original timestamp
            original_timestamp = message.get('timestamp')
            if original_timestamp:
                try:
                    original_time = pendulum.parse(original_timestamp)
                except:
                    original_time = pendulum.now('UTC')
            else:
                original_time = pendulum.now('UTC')
            
            # Current processing time
            processing_time = pendulum.now('UTC')
            
            # Calculate processing latency
            processing_latency = (processing_time - original_time).total_seconds()
            
            # Create transformed message with flattened structure
            transformed = {
                'timestamp': processing_time.to_iso8601_string(),
                'timestamp_unix': int(processing_time.timestamp()),  # Convert to int for LONG type
                'original_timestamp': original_timestamp,
                'processing_latency_ms': processing_latency * 1000,
                'symbol': message.get('symbol', 'UNKNOWN'),
                'stream_type': message.get('stream_type', 'ticker'),
                'price': current_price,
                'volume': float(ticker_data.get('v', 0)),
                'high_24h': float(ticker_data.get('h', 0)),
                'low_24h': float(ticker_data.get('l', 0)),
                'price_change_24h': float(ticker_data.get('p', 0)),
                'price_change_percent_24h': float(ticker_data.get('P', 0)),
                'weighted_avg_price': float(ticker_data.get('w', 0)),
                'prev_close_price': float(ticker_data.get('x', 0)),
                'open_price': float(ticker_data.get('o', 0)),
                'bid_price': float(ticker_data.get('b', 0)),
                'ask_price': float(ticker_data.get('a', 0)),
                'count': int(ticker_data.get('n', 0)),
                # Flatten technical indicators
                'price_change': indicators.get('price_change', 0.0),
                'price_change_percent': indicators.get('price_change_percent', 0.0),
                'sma_5': indicators.get('sma_5', 0.0),
                'sma_20': indicators.get('sma_20', 0.0),
                'volatility': indicators.get('volatility', 0.0),
                'min_10': indicators.get('min_10', 0.0),
                'max_10': indicators.get('max_10', 0.0),
                # Flatten time metadata
                'hour_of_day': processing_time.hour,
                'day_of_week': processing_time.day_of_week,
                'day_name': processing_time.format('dddd'),
                'is_weekend': processing_time.day_of_week in [6, 7],
                'is_market_hours': self._is_market_hours(processing_time),
                'timezone': str(processing_time.timezone),
                'quarter': processing_time.quarter,
                'week_of_year': processing_time.week_of_year,
                # Flatten metadata
                'transformer_version': '1.0.0'
            }
            
            return transformed
            
        except Exception as e:
            logger.error(f"Error transforming message: {e}")
            return None
    
    def _is_market_hours(self, dt):
        """Check if current time is during major market hours"""
        # Convert to different timezone for market hours check
        ny_time = dt.in_timezone('America/New_York')
        london_time = dt.in_timezone('Europe/London')
        tokyo_time = dt.in_timezone('Asia/Tokyo')
        
        # Check if any major market is open (simplified)
        ny_open = 9 <= ny_time.hour <= 16 and ny_time.day_of_week <= 5
        london_open = 8 <= london_time.hour <= 16 and london_time.day_of_week <= 5
        tokyo_open = 9 <= tokyo_time.hour <= 15 and tokyo_time.day_of_week <= 5
        
        return ny_open or london_open or tokyo_open
    
    def process_messages(self):
        """Process messages from Kafka"""
        logger.info(f"Starting to consume messages from topic: {KAFKA_TOPIC_BINANCE}")
        
        try:
            for message in self.consumer:
                try:
                    # Transform the message
                    transformed_data = self.transform_message(message.value)
                    
                    if transformed_data:
                        # Send to transformed topic
                        self.producer.send(
                            KAFKA_TOPIC_TRANSFORMED,
                            key=transformed_data['symbol'],
                            value=transformed_data
                        )
                        
                        logger.info(f"Transformed and sent: {transformed_data['symbol']} - "
                                  f"Price: {transformed_data['price']}, "
                                  f"Change: {transformed_data.get('price_change_percent', 'N/A')}%")
                    
                except Exception as e:
                    logger.error(f"Error processing individual message: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in message processing loop: {e}")
    
    def close(self):
        """Close connections"""
        if self.consumer:
            self.consumer.close()
        if self.producer:
            self.producer.close()

def main():
    transformer = BinanceDataTransformer()
    
    if not transformer.create_kafka_connections():
        logger.error("Failed to create Kafka connections. Exiting.")
        return
    
    try:
        transformer.process_messages()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal. Shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        transformer.close()

if __name__ == "__main__":
    main()
