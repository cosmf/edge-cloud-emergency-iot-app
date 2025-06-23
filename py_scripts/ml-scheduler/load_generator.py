# load_generator.py
#
# A multi-threaded load generator to stress-test the ML scheduler service.
# This script simulates a high-traffic environment by sending a continuous
# stream of random, concurrent requests to the scheduler's /predict endpoint.

import requests
import json
import time
import random
import threading
import uuid
import logging  # <--- FIXED: Import the logging library

# --- Logging Setup ---
# FIXED: Configure the logging module to print messages to the console.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Configuration ---

class Config:
    """Configuration for the Load Generator."""
    SCHEDULER_URL = "http://127.0.0.1:5001/predict"
    CONCURRENT_WORKERS = 20
    WAIT_INTERVAL = (0.1, 0.5)
    EDGE_WORKERS = [f"edge-worker-{i:02d}" for i in range(8)]
    CLOUD_WORKERS = [f"cloud-worker-{i:02d}" for i in range(3)]
    ALL_WORKERS = EDGE_WORKERS + CLOUD_WORKERS

# --- Helper Functions for Random Data Generation ---

def generate_random_system_state():
    """Creates a randomized snapshot of the system's state."""
    worker_status = {worker: random.choice(['available', 'busy']) for worker in Config.ALL_WORKERS}
    
    return {
        "worker_status": worker_status,
        "avg_network_latency": random.randint(20, 150),
        "avg_server_load": round(random.uniform(0.2, 0.98), 2),
        "cloud_cost_factor": round(random.uniform(0.5, 1.5), 2)
    }

def generate_random_task_info():
    """Creates a randomized task description."""
    data_type_choices = ['default-stream'] * 7 + ['L', 'M', 'H']
    
    return {
        "recordId": str(uuid.uuid4()),
        "userId": f"user_{random.randint(0, 49):03d}",
        "dataType": random.choice(data_type_choices),
        "size": random.randint(50, 2000),
        "location": {
            "x": random.randint(0, 1000),
            "y": random.randint(0, 1000)
        }
    }

# --- Main Worker Thread Function ---

def run_load_worker(worker_name):
    """
    The main function for each thread. It loops forever, sending requests.
    """
    logging.info(f"Load worker '{worker_name}' started.")
    
    while True:
        try:
            payload = {
                "task_info": generate_random_task_info(),
                "system_state": generate_random_system_state()
            }
            
            response = requests.post(Config.SCHEDULER_URL, json=payload, timeout=2)
            
            # Use logging instead of print for thread-safe, formatted output
            if response.status_code == 200:
                assigned_worker = response.json().get('assigned_worker', 'N/A')
                log_message = (f"-> Sent '{payload['task_info']['dataType']}' task. "
                               f"Response: {response.status_code} "
                               f"-> Assigned: {assigned_worker}")
                logging.info(log_message)
            else:
                logging.warning(f"-> Request failed! Status: {response.status_code}, "
                                f"Response: {response.text}")

        except requests.exceptions.RequestException as e:
            logging.error(f"!! Request Exception: {e} !!")
        
        time.sleep(random.uniform(*Config.WAIT_INTERVAL))

# --- Main Execution ---

if __name__ == "__main__":
    logging.info("--- Starting High-Traffic Load Generator ---")
    logging.info(f"Targeting Scheduler at: {Config.SCHEDULER_URL}")
    logging.info(f"Spawning {Config.CONCURRENT_WORKERS} concurrent workers...")
    
    threads = []
    for i in range(Config.CONCURRENT_WORKERS):
        thread_name = f"Generator-{i+1:02d}"
        thread = threading.Thread(target=run_load_worker, name=thread_name, args=(thread_name,))
        threads.append(thread)
        thread.start()
        
    for thread in threads:
        thread.join()