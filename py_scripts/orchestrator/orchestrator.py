# orchestrator.py
#
# This script implements the Orchestrator, the central control-plane microservice
# for the edge-cloud system. It operates as a REST API server to manage worker
# state, dispatch tasks, and trigger offline analysis.

import json
import logging
import time
import os
import threading
import subprocess
from flask import Flask, request, jsonify
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- Configuration ---

class Config:
    """Centralized configuration for the Orchestrator."""
    # API Server Settings
    API_HOST = '0.0.0.0'
    API_PORT = 5000

    # InfluxDB Connection Details
    INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
    INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'tUujj2tC9k6WkiTYXA9tB2c1wHnPjFt-2hCcOptcJlDD5KNNM-vQgKRb7ij7ZmdlHowT5vRSRvAFCWroMPwieA==')
    INFLUXDB_ORG = 'moby.lab'
    INFLUXDB_BUCKET_STATE = 'dge-cloud-bucket' # A dedicated bucket for worker state

    # A static list of known workers in the system. In a dynamic system, this could
    # be discovered via a registration process.
    KNOWN_WORKER_IDS = [f"worker-{i:02d}" for i in range(5)] # Example: 5 workers

    # Analysis Notebook Settings
    INPUT_NOTEBOOK_PATH = "analysis/HealthAnalysis.ipynb"
    OUTPUT_NOTEBOOK_PATH = "analysis/reports/HealthAnalysis_Report_{timestamp}.ipynb"

# --- Logging Setup ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Orchestrator] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Orchestrator Service ---

class Orchestrator:
    """The main application class for the Orchestrator REST API."""

    def __init__(self):
        """Initializes the Flask app, database connections, and state."""
        self.app = Flask(__name__)
        self._register_routes()

        self.worker_status_cache = {}
        self.cache_lock = threading.Lock()

        # Initialize InfluxDB client for writing state
        self.influx_client = InfluxDBClient(
            url=Config.INFLUXDB_URL, 
            token=Config.INFLUXDB_TOKEN, 
            org=Config.INFLUXDB_ORG
        )
        self.influx_write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
        
        self._load_initial_worker_status()

    def _register_routes(self):
        """Binds the API methods to their respective URL routes."""
        self.app.add_url_rule("/api/v1/request_assignment", "request_assignment", self.handle_assignment_request, methods=["POST"])
        self.app.add_url_rule("/api/v1/report_completion", "report_completion", self.handle_completion_report, methods=["POST"])
        self.app.add_url_rule("/api/v1/trigger_analysis", "trigger_analysis", self.trigger_analysis_notebook, methods=["POST"])
        self.app.add_url_rule("/api/v1/status", "get_status", self.get_system_status, methods=["GET"])

    def _load_initial_worker_status(self):
        """Initializes the status of all known workers to 'available'."""
        logging.info("Initializing worker status cache...")
        with self.cache_lock:
            for worker_id in Config.KNOWN_WORKER_IDS:
                # In a real system, you might query InfluxDB for the last known state.
                # Here, we initialize all workers as 'available'.
                self.worker_status_cache[worker_id] = "available"
                self._write_worker_status_to_influx(worker_id, "available")
        logging.info(f"Initialized {len(Config.KNOWN_WORKER_IDS)} workers.")

    def _write_worker_status_to_influx(self, worker_id, status):
        """Writes a worker's status change to InfluxDB."""
        point = Point("worker_status") \
            .tag("workerId", worker_id) \
            .field("status", status) \
            .time(int(time.time() * 1e9))
        try:
            self.influx_write_api.write(bucket=Config.INFLUXDB_BUCKET_STATE, record=point)
        except Exception as e:
            logging.error(f"Failed to write status for {worker_id} to InfluxDB: {e}")

    def _call_scheduler(self, task_data):
        """
        Decision-making logic to select a worker.
        This is the placeholder for the ML-based scheduling algorithm.
        """
        logging.info("Scheduler seeking available worker...")
        # Current logic: Simple first-available.
        # Future logic: Call an external ML service with `task_data` and get a worker_id back.
        # response = requests.post("http://scheduler-ml-service/predict", json=task_data)
        
        with self.cache_lock:
            for worker_id, status in self.worker_status_cache.items():
                if status == "available":
                    logging.info(f"Scheduler selected worker: {worker_id}")
                    return worker_id
        
        logging.warning("Scheduler could not find any available workers.")
        return None

    # --- API Endpoint Handlers ---

    def handle_assignment_request(self):
        """Handles requests from the Preprocessing Unit for a task assignment."""
        task_data = request.get_json()
        logging.info(f"Received assignment request for user {task_data.get('userId')}")

        assigned_worker = self._call_scheduler(task_data)

        if assigned_worker:
            with self.cache_lock:
                self.worker_status_cache[assigned_worker] = "busy"
                self._write_worker_status_to_influx(assigned_worker, "busy")
            
            return jsonify({
                "status": "ASSIGNED",
                "assignedTarget": assigned_worker,
                "taskId": task_data.get('recordId')
            }), 200
        else:
            return jsonify({"error": "No available workers to process the request."}), 503 # Service Unavailable

    def handle_completion_report(self):
        """Handles reports from workers that have finished a task."""
        report = request.get_json()
        worker_id = report.get('workerId')
        logging.info(f"Received completion report from worker {worker_id}.")

        if worker_id in self.worker_status_cache:
            with self.cache_lock:
                self.worker_status_cache[worker_id] = "available"
                self._write_worker_status_to_influx(worker_id, "available")
            
            # Here you could add logic to handle the 'results' or 'isEmergency' flag
            if report.get('isEmergency'):
                logging.critical(f"Emergency event for task {report.get('recordId')} successfully processed by {worker_id}.")
                
            return jsonify({"status": "ACKNOWLEDGED"}), 200
        else:
            return jsonify({"error": f"Unknown worker ID: {worker_id}"}), 404

    def trigger_analysis_notebook(self):
        """Triggers an offline analysis by running a parameterized Jupyter Notebook."""
        logging.info("Received request to trigger analysis notebook.")
        
        # We use Papermill to execute the notebook in the background. This makes the call non-blocking.
        # pip install papermill
        timestamp = int(time.time())
        output_path = Config.OUTPUT_NOTEBOOK_PATH.format(timestamp=timestamp)
        
        command = [
            "papermill",
            Config.INPUT_NOTEBOOK_PATH,
            output_path,
            "-p", "execution_timestamp", str(timestamp) # Example of passing a parameter
        ]
        
        # Run the command in a separate thread to not block the API response
        def run_notebook():
            try:
                logging.info(f"Executing command: {' '.join(command)}")
                subprocess.run(command, check=True, capture_output=True, text=True)
                logging.info(f"Successfully executed notebook. Report saved to {output_path}")
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to execute notebook: {e.stderr}")
        
        threading.Thread(target=run_notebook).start()
        
        return jsonify({
            "status": "ANALYSIS_TRIGGERED",
            "report_path": output_path
        }), 202 # 202 Accepted

    def get_system_status(self):
        """A simple endpoint to view the current status of all workers."""
        with self.cache_lock:
            return jsonify(self.worker_status_cache)

    def run(self):
        """Starts the Flask API server."""
        logging.info(f"Orchestrator starting on {Config.API_HOST}:{Config.API_PORT}")
        self.app.run(host=Config.API_HOST, port=Config.API_PORT, threaded=True)

if __name__ == "__main__":
    orchestrator_service = Orchestrator()
    orchestrator_service.run()