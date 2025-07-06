# RealtimeDataProcessingBinance
Using Kafka, Binance API, ClickHouse and -A Visualization tool- building a dockerized finance dashboard.
The data flow is basically EtLT.

The Tech stack used in the project is 
| Layer                     | Tool                                                              |
| ------------------------- | ----------------------------------------------------------------- |
| **Source**                | Binance WS API                                                    |
| **Buffer**                | Kafka                                                             |
| **Tiny Transformations**  | Python (producer script)                                          |
| **Load**                  | Kafka → ClickHouse (via Kafka Connect or native ingestion)        |
| **Transform**             | ClickHouse MVs                                                    | 
| **Visualize**             | Grafana (or Superset or any other Open Source Data Viz Solution)  |

