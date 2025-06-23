# preprocessing_unit.py
#
# The Preprocessing and Decision Logic Unit microservice. This service acts as
# the central hub for incoming raw data, processing it, storing it, and
# dispatching it for further analysis based on defined logic. All dispatching,
# including emergencies, is routed through the Orchestrator.

import json
import logging
import time
import requests
import os
from concurrent.futures import ThreadPoolExecutor
from kafka import KafkaConsumer, KafkaProducer
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- Configuration ---

class Config:
    """Centralized configuration for the microservice."""
    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
    RAW_DATA_TOPIC = 'raw-data'
    CONSUMER_GROUP_ID = 'preprocessing-group'
    
    # Mapping data types to their respective Kafka topics
    PRIORITY_TOPIC_MAP = {
        "H": "H-priority-topic",
        "M": "M-priority-topic",
        "L": "L-priority-topic",
        "default-stream": "default-stream-topic"
    }

    # InfluxDB Connection Details
    INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
    INFLUXDB_TOKEN = os.getenv('INFLUXDB_TOKEN', 'tUujj2tC9k6WkiTYXA9tB2c1wHnPjFt-2hCcOptcJlDD5KNNM-vQgKRb7ij7ZmdlHowT5vRSRvAFCWroMPwieA==')
    INFLUXDB_ORG = 'my-org'
    INFLUXDB_BUCKET = 'smartwatch-data'

    # Orchestrator API endpoint
    ORCHESTRATOR_ASSIGNMENT_URL = "http://orchestrator-service/api/v1/request_assignment"

    # Concurrency Settings
    MAX_CONCURRENT_TASKS = 3

    # Clinical Emergency Thresholds
    HEART_RATE_EMERGENCY_HIGH = 160
    HEART_RATE_EMERGENCY_LOW = 40
    SPO2_EMERGENCY_LOW = 88

# --- Logging Setup ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Service Class ---

class PreprocessingUnit:
    """Encapsulates the logic for the preprocessing service."""
    
    def __init__(self):
        """Initializes all necessary clients for external services."""
        logging.info("Initializing Preprocessing Unit...")
        
        self.consumer = KafkaConsumer(
            Config.RAW_DATA_TOPIC,
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            group_id=Config.CONSUMER_GROUP_ID,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest'
        )

        self.producer = KafkaProducer(
            bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        self.influx_client = InfluxDBClient(
            url=Config.INFLUXDB_URL, 
            token=Config.INFLUXDB_TOKEN, 
            org=Config.INFLUXDB_ORG
        )
        self.influx_write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
        logging.info("InfluxDB client initialized.")
        
        logging.info("Preprocessing Unit is online and ready.")

    def _write_to_influxdb(self, data):
        """Writes the preprocessed health data to InfluxDB."""
        health_data = data.get('healthData', {})
        point = Point("health_metrics") \
            .tag("userId", data.get('userId')) \
            .tag("dataType", data.get('dataType')) \
            .field("heart_rate", health_data.get('heart_rate', 0)) \
            .field("spo2", health_data.get('spo2', 0.0)) \
            .time(int(data.get('processedTimestamp') * 1e9))

        try:
            self.influx_write_api.write(bucket=Config.INFLUXDB_BUCKET, record=point)
            logging.info(f"Successfully wrote data for user {data['userId']} to InfluxDB.")
        except Exception as e:
            logging.error(f"Failed to write to InfluxDB for user {data['userId']}: {e}")

    def _call_orchestrator(self, data):
        """Makes a request to the Orchestrator to get a worker assignment."""
        logging.info(f"Contacting Orchestrator for task assignment for user {data['userId']}...")
        try:
            payload = {
                "recordId": data['recordId'],
                "userId": data['userId'],
                "location": data['location'],
                "dataType": data['dataType']
            }
            response = requests.post(Config.ORCHESTRATOR_ASSIGNMENT_URL, json=payload, timeout=10)
            response.raise_for_status()
            
            assignment = response.json()
            logging.info(f"Orchestrator assigned task to: {assignment.get('assignedTarget')}")
            return assignment
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to connect or get valid response from Orchestrator: {e}")
            return None

    def _trigger_emergency_alert(self, data):
        """Logs a critical alert for monitoring and external systems."""
        logging.critical(f"EMERGENCY DETECTED for user {data['userId']} with vitals: {data.get('healthData')}. "
                         "Proceeding with high-priority orchestration.")
        # This function is now for alerting/monitoring, not for workflow control.
        # An external system could monitor logs for this CRITICAL message.

    def process_message(self, raw_message):
        """The core processing logic for a single raw data message."""
        data = raw_message.value
        data['processedTimestamp'] = time.time()
        
        health_info = data.get('healthData', {})
        hr = health_info.get('heart_rate', 0)
        spo2 = health_info.get('spo2', 100)

        # Step 1: Check for critical conditions.
        is_emergency = (
            hr > Config.HEART_RATE_EMERGENCY_HIGH or
            hr < Config.HEART_RATE_EMERGENCY_LOW or
            spo2 < Config.SPO2_EMERGENCY_LOW
        )

        # If an emergency is detected, tag the data and log a critical alert.
        # The workflow will NOT stop here.
        if is_emergency:
            data['dataType'] = 'H'
            self._trigger_emergency_alert(data)
        
        # Step 2: Write to the database for all cases (normal and emergency).
        self._write_to_influxdb(data)
        
        # Step 3: ALWAYS contact the Orchestrator for assignment.
        # The Orchestrator's logic is responsible for correctly routing 'H' priority tasks.
        assignment = self._call_orchestrator(data)
        
        if not assignment or 'assignedTarget' not in assignment:
            logging.error("Failed to get a valid assignment from Orchestrator. Aborting task.")
            return
            
        # Step 4: Produce to the downstream topic specified by the Orchestrator's logic.
        target_topic = Config.PRIORITY_TOPIC_MAP.get(data['dataType'])
        if target_topic:
            data['assignment'] = assignment
            logging.info(f"Producing message for user {data['userId']} to topic '{target_topic}'.")
            self.producer.send(target_topic, value=data)
            self.producer.flush()
        else:
            logging.warning(f"No target topic found for dataType '{data['dataType']}'. Message dropped.")
            
    def run(self):
        """Starts the service, consuming messages and processing them concurrently."""
        logging.info(f"Starting consumer loop with a thread pool of size {Config.MAX_CONCURRENT_TASKS}.")
        with ThreadPoolExecutor(max_workers=Config.MAX_CONCURRENT_TASKS) as executor:
            for message in self.consumer:
                executor.submit(self.process_message, message)

if __name__ == "__main__":
    try:
        service = PreprocessingUnit()
        service.run()
    except Exception as e:
        logging.critical(f"A fatal error occurred in the main execution loop: {e}")