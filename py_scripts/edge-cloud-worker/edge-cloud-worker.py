# cloud_edge_worker.py
#
# This script represents a Cloud or Edge Worker. Its primary role is to consume
# tasks from the priority Kafka topics, perform data analysis by fetching historical
# context from InfluxDB, and report the results back to the Orchestrator.

import json
import logging
import time
import requests
import os
import sys
import random
from kafka import KafkaConsumer
from influxdb_client import InfluxDBClient

# --- Configuration ---

class Config:
    """Centralized configuration for the microservice."""
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    KAFKA_TOPICS = [
        "H-priority-topic",
        "M-priority-topic",
        "L-priority-topic",
        "default-stream-topic"
    ]
    CONSUMER_GROUP_ID_PREFIX = 'cloud-edge-worker-group'
    KAFKA_POLL_TIMEOUT_MS = 100 

    # InfluxDB Connection Details
    INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
    INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'tUujj2tC9k6WkiTYXA9tB2c1wHnPjFt-2hCcOptcJlDD5KNNM-vQgKRb7ij7ZmdlHowT5vRSRvAFCWroMPwieA==')
    INFLUXDB_ORG = 'my-org'
    INFLUXDB_BUCKET = 'smartwatch-data'
    
    # Orchestrator API endpoint for reporting completion
    ORCHESTRATOR_COMPLETION_URL = "http://orchestrator-service/api/v1/report_completion"
    
    # Time to wait before polling topics again if all are empty
    IDLE_POLL_INTERVAL_SECONDS = 5
    
    # Worker-specific analysis thresholds
    HEART_RATE_SPIKE_THRESHOLD = 40 # A jump of 40 BPM above baseline is a confirmed emergency
    SPO2_DROP_THRESHOLD = 5         # A drop of 5% in SpO2 from baseline is a confirmed emergency

# --- Logging Setup ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Service Class ---

class CloudEdgeWorker:
    """Encapsulates the logic for a single data processing worker."""

    def __init__(self, worker_id):
        """Initializes clients and connections for the worker."""
        self.worker_id = worker_id
        logging.info(f"Initializing Worker {self.worker_id}...")
        consumer_group = f"{Config.CONSUMER_GROUP_ID_PREFIX}-{self.worker_id}"
        
        self.consumer = KafkaConsumer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            group_id=consumer_group,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest'
        )
        self.consumer.subscribe(topics=Config.KAFKA_TOPICS)

        self.influx_client = InfluxDBClient(
            url=Config.INFLUXDB_URL, 
            token=Config.INFLUXDB_TOKEN, 
            org=Config.INFLUXDB_ORG
        )
        self.influx_query_api = self.influx_client.query_api()
        logging.info("InfluxDB client initialized.")
        logging.info(f"Worker {self.worker_id} is online and ready.")

    def _fetch_patient_history(self, user_id):
        """Fetches the last 10 minutes of data for a patient from InfluxDB."""
        logging.info(f"Fetching historical data for user {user_id} from InfluxDB.")
        flux_query = f'''
            from(bucket: "{Config.INFLUXDB_BUCKET}")
              |> range(start: -10m)
              |> filter(fn: (r) => r["_measurement"] == "health_metrics")
              |> filter(fn: (r) => r["userId"] == "{user_id}")
              |> filter(fn: (r) => r["_field"] == "heart_rate" or r["_field"] == "spo2")
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: 20)
        '''
        try:
            tables = self.influx_query_api.query(query=flux_query)
            results = {"heart_rate": [], "spo2": []}
            for table in tables:
                for record in table.records:
                    if record.get_field() in results:
                        results[record.get_field()].append(record.get_value())
            return results
        except Exception as e:
            logging.error(f"Failed to query InfluxDB for user {user_id}: {e}")
            return {"heart_rate": [], "spo2": []}

    def _report_completion_to_orchestrator(self, task, result, is_emergency):
        """Reports the result of the processed task back to the Orchestrator."""
        logging.info(f"Reporting completion for user {task['userId']} to Orchestrator.")
        payload = {
            "workerId": self.worker_id,
            "recordId": task['recordId'],
            "status": "COMPLETED",
            "results": result,
            "isEmergency": is_emergency
        }
        try:
            response = requests.post(Config.ORCHESTRATOR_COMPLETION_URL, json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Successfully reported completion for user {task['userId']}.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to report completion to Orchestrator: {e}")

    def _process_task(self, message):
        """The main logic for processing a single consumed task."""
        task_data = message.value
        user_id = task_data['userId']
        current_vitals = task_data.get('healthData', {})
        logging.info(f"Started processing task for user {user_id} from topic '{message.topic}'.")
        
        # Step 1: Fetch historical data for context
        history = self._fetch_patient_history(user_id)
        
        # Step 2: Perform deeper analysis to confirm emergency status
        is_emergency_flag = False
        analysis_summary = "Standard analysis complete. No anomalies detected."

        # Analysis Logic: Compare current vitals to historical baseline
        avg_hr = sum(history['heart_rate']) / len(history['heart_rate']) if history['heart_rate'] else 75
        current_hr = current_vitals.get('heart_rate', avg_hr)

        if current_hr > avg_hr + Config.HEART_RATE_SPIKE_THRESHOLD:
            is_emergency_flag = True
            analysis_summary = f"CONFIRMED EMERGENCY: Heart rate spiked to {current_hr} BPM (baseline avg: {avg_hr:.0f} BPM)."
        
        # You could add more rules here for SpO2, etc.
        
        # If an emergency is confirmed, log it with high visibility
        if is_emergency_flag:
            logging.critical(f"Analysis confirmed an EMERGENCY for user {user_id}. Flagging report.")
        
        # Simulate processing time
        time.sleep(random.randint(2, 5))

        # Step 3: Compile the processing result
        processing_result = {
            "analysisTimestamp": time.time(),
            "summary": analysis_summary,
            "isEmergencyConfirmed": is_emergency_flag,
            "historicalPointsFound": len(history['heart_rate']),
            "currentVitals": current_vitals,
            "historicalAvgHeartRate": avg_hr
        }

        # Step 4: Report completion back to the orchestrator with the CONFIRMED flag
        self._report_completion_to_orchestrator(task_data, processing_result, is_emergency_flag)
        logging.info(f"Finished processing task for user {user_id}.")

    def run(self):
        """The main loop that implements prioritized polling of Kafka topics."""
        logging.info(f"Worker {self.worker_id} starting prioritized polling loop.")
        while True:
            found_message = False
            for topic in Config.KAFKA_TOPICS:
                self.consumer.subscribe([topic])
                messages = self.consumer.poll(timeout_ms=Config.KAFKA_POLL_TIMEOUT_MS, max_records=1)
                
                if messages:
                    for partition, records in messages.items():
                        for record in records:
                            self._process_task(record)
                            found_message = True
                            break
                    if found_message:
                        break
            
            if not found_message:
                time.sleep(Config.IDLE_POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cloud_edge_worker.py <worker-id>")
        sys.exit(1)
        
    worker_id_arg = sys.argv[1]
    
    try:
        worker = CloudEdgeWorker(worker_id=worker_id_arg)
        # Use threading to add the worker_id to the log messages for clarity
        main_thread = threading.Thread(target=worker.run, name=worker_id_arg)
        main_thread.start()
        main_thread.join()
    except Exception as e:
        logging.critical(f"A fatal error occurred in worker {worker_id_arg}: {e}")