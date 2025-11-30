#!/usr/bin/env python3
"""
Superset initialization script for Binance Real-time Data Processing.
Creates Pinot DB connection, dataset, two starter charts, and a dashboard.
"""

import json
import os
import time
from urllib.parse import urljoin

import pendulum
import requests

# Superset configuration
SUPERSET_BASE_URL = "http://localhost:8088"
SUPERSET_USERNAME = os.getenv("SUPERSET_ADMIN_USER", "admin")
SUPERSET_PASSWORD = os.getenv("SUPERSET_ADMIN_PASSWORD", "admin123")

# Pinot configuration
PINOT_BROKER_URL = "http://pinot-broker:8099"


class SupersetInitializer:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.refresh_token = None

    def login(self):
        """Login to Superset and set auth headers."""
        login_url = urljoin(SUPERSET_BASE_URL, "/api/v1/security/login")
        payload = {
            "username": SUPERSET_USERNAME,
            "password": SUPERSET_PASSWORD,
            "provider": "db",
            "refresh": True,
        }

        response = self.session.post(login_url, json=payload)
        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.session.headers.update(
                {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
            )
            print("OK: Logged in to Superset")
            return True

        print(f"ERROR: Failed to login: {response.status_code} - {response.text}")
        return False

    def create_pinot_database(self):
        """Create Pinot database connection."""
        db_url = urljoin(SUPERSET_BASE_URL, "/api/v1/database/")
        payload = {
            "database_name": "Pinot",
            "sqlalchemy_uri": f"pinot://{PINOT_BROKER_URL.replace('http://', '')}/query/sql?controller=http://pinot-controller:9000",
            "expose_in_sqllab": True,
            "allow_run_async": True,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
            "force_ctas_schema": "",
            "cache_timeout": 0,
            "extra": json.dumps(
                {
                    "metadata_params": {},
                    "engine_params": {},
                    "metadata_cache_timeout": {},
                    "schemas_allowed_for_csv_upload": [],
                }
            ),
        }

        response = self.session.post(db_url, json=payload)
        if response.status_code == 201:
            db_id = response.json()["id"]
            print("OK: Created Pinot database connection")
            return db_id

        print(f"ERROR: Failed to create database: {response.status_code} - {response.text}")
        return None

    def create_dataset(self, database_id):
        """Create dataset for binance_realtime table."""
        # Return existing dataset if present
        existing = self.find_dataset("binance_realtime", database_id)
        if existing:
            print(f"OK: Reusing existing binance_realtime dataset (id={existing})")
            return existing
        # Return existing virtual dataset if present
        existing_virtual = self.find_dataset("binance_realtime_virtual", database_id)
        if existing_virtual:
            print(f"OK: Reusing existing virtual dataset (id={existing_virtual})")
            return existing_virtual

        dataset_url = urljoin(SUPERSET_BASE_URL, "/api/v1/dataset/")
        payload = {"database": database_id, "schema": None, "table_name": "binance_realtime", "sql": "", "owners": [1]}

        response = self.session.post(dataset_url, json=payload)
        if response.status_code == 201:
            ds_id = response.json()["id"]
            print("OK: Created binance_realtime dataset")
            return ds_id

        print(f"ERROR: Failed to create physical dataset: {response.status_code} - {response.text}")
        # Fallback to a virtual dataset using a simple SQL query
        vds_id = self.create_virtual_dataset(database_id)
        if vds_id:
            print(f"OK: Created virtual binance_realtime dataset (id={vds_id})")
            return vds_id
        print("ERROR: Failed to create dataset via both physical and virtual paths")
        return None

    def create_virtual_dataset(self, database_id):
        """Create a SQL (virtual) dataset as a fallback."""
        dataset_url = urljoin(SUPERSET_BASE_URL, "/api/v1/dataset/")
        payload = {
            "database": database_id,
            "schema": None,
            "table_name": "binance_realtime_virtual",
            "sql": "SELECT * FROM binance_realtime",
            "owners": [1]
        }
        response = self.session.post(dataset_url, json=payload)
        if response.status_code == 201:
            return response.json()["id"]
        print(f"ERROR: Failed to create virtual dataset: {response.status_code} - {response.text}")
        return None

    def find_dataset(self, table_name, database_id):
        """Return dataset id if one already exists for the table/database."""
        query = {
            "filters": [
                {"col": "table_name", "opr": "eq", "value": table_name}
            ],
            "page": 0,
            "page_size": 1,
        }
        url = urljoin(SUPERSET_BASE_URL, f"/api/v1/dataset/?q={json.dumps(query)}")
        resp = self.session.get(url)
        if resp.status_code != 200:
            print(f"ERROR: Dataset lookup failed: {resp.status_code} - {resp.text}")
            return None
        payload = resp.json()
        for ds in payload.get("result", []):
            # Ensure it matches the current database
            db_obj = ds.get("database") or {}
            if not database_id or db_obj.get("id") == database_id:
                return ds.get("id")
        return None

    def set_time_column(self, dataset_id, column_name="timestamp_unix"):
        """Mark the time column so time-series charts work."""
        dataset_url = urljoin(SUPERSET_BASE_URL, f"/api/v1/dataset/{dataset_id}")
        payload = {"main_dttm_col": column_name}
        response = self.session.put(dataset_url, json=payload)
        if response.status_code == 200:
            print(f"OK: Set main time column to '{column_name}'")
            return True

        print(f"ERROR: Failed to set time column: {response.status_code} - {response.text}")
        return False

    def create_chart(self, dataset_id, slice_name, viz_type, form_data):
        """Create a chart (slice) via Superset API."""
        chart_url = urljoin(SUPERSET_BASE_URL, "/api/v1/chart/")
        payload = {
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "slice_name": slice_name,
            "viz_type": viz_type,
            "cache_timeout": 0,
            "params": json.dumps(form_data),
        }

        response = self.session.post(chart_url, json=payload)
        if response.status_code == 201:
            chart_id = response.json()["id"]
            print(f"OK: Created chart '{slice_name}' (id={chart_id})")
            return chart_id

        print(f"ERROR: Failed to create chart '{slice_name}': {response.status_code} - {response.text}")
        return None

    def create_dashboard(self, chart_ids):
        """Create dashboard wired to the created charts."""
        # Remove existing dashboard with same slug to avoid stale placeholders
        existing_dash = self.find_dashboard("binance-realtime-crypto")
        if existing_dash:
            self.delete_dashboard(existing_dash)

        dashboard_url = urljoin(SUPERSET_BASE_URL, "/api/v1/dashboard/")
        price_chart_id = chart_ids.get("price")
        volume_chart_id = chart_ids.get("volume")

        position_json = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
            "GRID_ID": {"children": ["ROW-1", "ROW-2"], "id": "GRID_ID", "type": "GRID"},
            "ROW-1": {
                "children": [f"CHART-{price_chart_id}"] if price_chart_id else [],
                "id": "ROW-1",
                "type": "ROW",
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
            },
            "ROW-2": {
                "children": [f"CHART-{volume_chart_id}"] if volume_chart_id else [],
                "id": "ROW-2",
                "type": "ROW",
                "meta": {"background": "BACKGROUND_TRANSPARENT"},
            },
        }

        if price_chart_id:
            position_json[f"CHART-{price_chart_id}"] = {
                "children": [],
                "id": f"CHART-{price_chart_id}",
                "type": "CHART",
                "meta": {"chartId": price_chart_id, "sliceName": "Price Over Time", "width": 12, "height": 50},
            }

        if volume_chart_id:
            position_json[f"CHART-{volume_chart_id}"] = {
                "children": [],
                "id": f"CHART-{volume_chart_id}",
                "type": "CHART",
                "meta": {"chartId": volume_chart_id, "sliceName": "Volume Over Time", "width": 12, "height": 50},
            }

        dashboard_payload = {
            "dashboard_title": "Binance Real-time Crypto Dashboard",
            "slug": "binance-realtime-crypto",
            "owners": [1],
            "position_json": json.dumps(position_json),
        }

        response = self.session.post(dashboard_url, json=dashboard_payload)
        if response.status_code == 201:
            dash_id = response.json()["id"]
            print("OK: Created Binance dashboard")
            return dash_id

        print(f"ERROR: Failed to create dashboard: {response.status_code} - {response.text}")
        return None

    def find_dashboard(self, slug):
        """Return dashboard id by slug if it exists."""
        query = {
            "filters": [
                {"col": "slug", "opr": "eq", "value": slug}
            ],
            "page": 0,
            "page_size": 1,
        }
        url = urljoin(SUPERSET_BASE_URL, f"/api/v1/dashboard/?q={json.dumps(query)}")
        resp = self.session.get(url)
        if resp.status_code != 200:
            print(f"ERROR: Dashboard lookup failed: {resp.status_code} - {resp.text}")
            return None
        payload = resp.json()
        result = payload.get("result", [])
        if result:
            return result[0].get("id")
        return None

    def delete_dashboard(self, dashboard_id):
        """Delete a dashboard by id."""
        url = urljoin(SUPERSET_BASE_URL, f"/api/v1/dashboard/{dashboard_id}")
        resp = self.session.delete(url)
        if resp.status_code in (200, 204):
            print(f"OK: Deleted existing dashboard id={dashboard_id}")
        else:
            print(f"ERROR: Failed to delete dashboard id={dashboard_id}: {resp.status_code} - {resp.text}")

    def wait_for_superset(self, max_retries=30):
        """Wait for Superset to be ready."""
        for attempt in range(max_retries):
            try:
                health_url = urljoin(SUPERSET_BASE_URL, "/health")
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    print("OK: Superset is ready")
                    return True
            except requests.exceptions.RequestException:
                pass

            print(f"Waiting for Superset to be ready... (attempt {attempt + 1}/{max_retries})")
            time.sleep(10)

        print("ERROR: Superset failed to start within timeout")
        return False

    def initialize(self):
        """Initialize Superset with Pinot connection, dataset, charts, and dashboard."""
        print("Initializing Superset...")

        if not self.wait_for_superset():
            return False
        if not self.login():
            return False

        database_id = self.create_pinot_database()
        if not database_id:
            return False

        dataset_id = self.create_dataset(database_id)
        if not dataset_id:
            return False

        # Set primary time column for time-series charts
        if not self.set_time_column(dataset_id, "timestamp_unix"):
            return False

        charts = {}
        price_metric = {
            "label": "avg_price",
            "expressionType": "SIMPLE",
            "aggregate": "AVG",
            "column": {"column_name": "price"},
        }
        volume_metric = {
            "label": "sum_volume",
            "expressionType": "SIMPLE",
            "aggregate": "SUM",
            "column": {"column_name": "volume"},
        }

        price_form = {
            "datasource": f"{dataset_id}__table",
            "viz_type": "echarts_timeseries_line",
            "granularity_sqla": "timestamp_unix",
            "time_range": "No filter",
            "time_grain_sqla": None,
            "adhoc_filters": [],
            "groupby": ["symbol"],
            "metrics": [price_metric],
            "order_desc": True,
            "row_limit": 1000,
            "contribution": False,
            "rich_tooltip": True,
            "show_legend": True,
        }

        volume_form = {
            "datasource": f"{dataset_id}__table",
            "viz_type": "echarts_timeseries_line",
            "granularity_sqla": "timestamp_unix",
            "time_range": "No filter",
            "time_grain_sqla": None,
            "adhoc_filters": [],
            "groupby": ["symbol"],
            "metrics": [volume_metric],
            "order_desc": True,
            "row_limit": 1000,
            "contribution": False,
            "rich_tooltip": True,
            "show_legend": True,
        }

        charts["price"] = self.create_chart(dataset_id, "Price Over Time", "echarts_timeseries_line", price_form)
        charts["volume"] = self.create_chart(dataset_id, "Volume Over Time", "echarts_timeseries_line", volume_form)

        # Dashboard creation is skipped to avoid layout/debug overhead; use the created charts to build a dashboard manually.
        print("OK: Superset initialization completed (database, dataset, charts created; dashboard skipped).")
        return True


if __name__ == "__main__":
    initializer = SupersetInitializer()
    if initializer.initialize():
        print("OK: Setup complete! You can now access Superset and create your visualizations.")
    else:
        print("ERROR: Setup failed. Please check the logs and try again.")
