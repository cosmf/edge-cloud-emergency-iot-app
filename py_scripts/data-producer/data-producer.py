# smartwatch_producer_final.py


import requests
import json
import time
import random
import threading
import uuid
import logging
import csv
import os
import pandas as pd

# --- Configuration ---

class Config:
    """Groups all simulation parameters for easy management."""
    USER_IDS_TO_SIMULATE = [f"{i:03d}" for i in range(50)]
    GEOLIFE_DATA_PATH = '/home/cosmf/.cache/kagglehub/datasets/arashnic/microsoft-geolife-gps-trajectory-dataset/versions/1/Geolife Trajectories 1.3/Data'
    KONG_API_GATEWAY_URL = "http://edge-cloud-sim.com/ingest"
    TRANSMISSION_INTERVAL_SECONDS = (1, 3)
    TRACE_FILE_PATH = 'position_trace_real.csv'
    TRACE_SAVE_INTERVAL_SECONDS = 30

# --- Logging Setup ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Data Loading from GeoLife Dataset ---

def load_user_trajectory(base_path, user_id):
    """
    Loads all .plt files for a single user and concatenates them into one trajectory.
    This simulates fetching a user's entire historical movement data from a database.
    """
    trajectory_path = os.path.join(base_path, user_id, 'Trajectory')
    if not os.path.exists(trajectory_path):
        return None

    all_files = [os.path.join(trajectory_path, f) for f in os.listdir(trajectory_path) if f.endswith('.plt')]
    df_list = []
    column_names = ['latitude', 'longitude', 'unused', 'altitude', 'date_days', 'time_fraction', 'timestamp']
    
    for filepath in all_files:
        try:
            df = pd.read_csv(filepath, header=None, skiprows=6, names=column_names, usecols=['latitude', 'longitude'])
            if not df.empty:
                df_list.append(df)
        except Exception as e:
            logging.warning(f"Could not read {filepath}: {e}")

    if not df_list: return None
    return pd.concat(df_list, ignore_index=True)

def load_all_trajectories(base_path, user_ids):
    """
    Conceptually, this function loads all user data into MongoDB.
    In our script, it will load it into a dictionary in memory.
    """
    logging.info("Loading all user trajectories from GeoLife dataset source...")
    trajectory_database = {}
    for user_id in user_ids:
        user_df = load_user_trajectory(base_path, user_id)
        if user_df is not None:
            trajectory_database[user_id] = user_df
            logging.info(f"Loaded {len(user_df)} GPS points for user {user_id}")
        else:
            logging.warning(f"No trajectory data found for user {user_id}")
    return trajectory_database

# --- Trace Generation ---

trace_records = []
trace_lock = threading.Lock()

def save_trace_periodically(filepath, interval):
    # This function is the same as before, saving trace data to a CSV.
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'user_id', 'latitude', 'longitude'])
    while True:
        time.sleep(interval)
        with trace_lock:
            if not trace_records: continue
            records_to_write = list(trace_records)
            trace_records.clear()
        try:
            with open(filepath, 'a', newline='') as f:
                writer = csv.writer(f)
                for record in records_to_write:
                    writer.writerow([record['timestamp'], record['user_id'], record['latitude'], record['longitude']])
            logging.info(f"Successfully wrote {len(records_to_write)} records to {filepath}")
        except IOError as e:
            logging.error(f"Failed to write trace file: {e}")

# --- Main Producer Class ---

class Smartwatch(threading.Thread):
    """A producer that replays real GPS data for a specific user."""

    def __init__(self, user_id, trajectory_df):
        super().__init__(name=user_id)
        self.user_id = user_id
        self.numeric_id = int(user_id)
        self.trajectory_df = trajectory_df
        self.trajectory_step = 0

    def _move_along_route(self):
        # Gets the next GPS coordinate from the loaded trajectory data.
        self.trajectory_step = (self.trajectory_step + 1) % len(self.trajectory_df)
        current_pos_series = self.trajectory_df.iloc[self.trajectory_step]
        self.current_pos = (current_pos_series.latitude, current_pos_series.longitude)
        
        with trace_lock:
            trace_records.append({
                "timestamp": time.time(),
                "user_id": self.user_id,
                "latitude": self.current_pos[0],
                "longitude": self.current_pos[1]
            })

    def _generate_health_data(self):
        """
        Generates health data with a layered priority model.
        Acute anomalies (e.g., heart rate > 140) override static risk profiles.
        """
        # 1. Simulate baseline sensor data
        data = {"heart_rate": random.randint(55, 110), "spo2": random.uniform(95.0, 99.5)}
        
        # 2. Check for acute, overriding anomalies first
        if data["heart_rate"] > 140 or data["spo2"] < 92:
            return data, "H"  # Emergency, overrides all other logic
        if data["heart_rate"] > 120 or data["spo2"] < 94:
            return data, "M"  # High-priority alert
        
        base_priority = "L" if data["heart_rate"] > 105 else "default-stream"

        # 3. If no acute event, apply the static risk profile for at-risk patients
        if self.numeric_id % 5 == 0:
            # High-risk cohort (Users 0, 5, 10, 15)
            if self.numeric_id < 20:
                if random.random() < 0.10: return data, "H" # 10% chance of H
                if random.random() < 0.20: return data, "M" # 20% chance of M
            
            # Medium-risk cohort (Users 20, 25, 30, 35)
            elif self.numeric_id < 40:
                if random.random() < 0.15: return data, "M" # 15% chance of M
                if random.random() < 0.25: return data, "L" # 25% chance of L

            # Low-risk cohort (Users 40, 45)
            else:
                if random.random() < 0.20: return data, "L" # 20% chance of L

        return data, base_priority

    def run(self):
        while True:
            self._move_along_route()
            health_data, priority = self._generate_health_data()

            payload = {
                "recordId": str(uuid.uuid4()),
                "userId": self.user_id,
                "timestamp": time.time(),
                "location": {"latitude": self.current_pos[0], "longitude": self.current_pos[1]},
                "dataType": priority,
                "healthData": health_data,
            }
            
            if priority != "default-stream":
                logging.info(f"Uploading '{priority}' data from position {self.current_pos}")
            
            try:
                requests.post(Config.KONG_API_GATEWAY_URL, json=payload, timeout=5)
            except requests.exceptions.RequestException as e:
                logging.warning(f"Gateway connection failed: {e}")
            
            time.sleep(random.uniform(*Config.TRANSMISSION_INTERVAL_SECONDS))

# --- Simulation Entrypoint ---

if __name__ == "__main__":
    logging.info("--- Initializing Smartwatch Producer Simulation with Real Trajectories & Risk Profiles ---")
    
    trajectory_db = load_all_trajectories(Config.GEOLIFE_DATA_PATH, Config.USER_IDS_TO_SIMULATE)
    
    if not trajectory_db:
        logging.error(f"No trajectory data loaded. Check GEOLIFE_DATA_PATH in Config. Exiting.")
        exit()

    trace_saver_thread = threading.Thread(
        target=save_trace_periodically,
        args=(Config.TRACE_FILE_PATH, Config.TRACE_SAVE_INTERVAL_SECONDS),
        daemon=True,
        name="TraceSaver"
    )
    trace_saver_thread.start()

    logging.info(f"Spawning {len(trajectory_db)} producer threads...")
    producers = []
    for user_id_str, traj_df in trajectory_db.items():
        producer_thread = Smartwatch(user_id=user_id_str, trajectory_df=traj_df)
        producers.append(producer_thread)
        producer_thread.start()

    logging.info("All producer threads started. Simulation is running.")