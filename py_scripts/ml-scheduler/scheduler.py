# scheduler.py
#
# The dedicated microservice for intelligent task offloading. It loads a
# pre-trained ML model to make real-time decisions based on system state
# and task data from the Orchestrator.

import logging
import os
import random
from flask import Flask, request, jsonify
import numpy as np
import joblib
import pandas as pd  # FIXED: Import the pandas library

# --- Configuration ---

class Config:
    """Configuration for the Scheduler service."""
    API_HOST = '0.0.0.0'
    API_PORT = 5001
    MODEL_PATH = 'scheduler_model.joblib'
    
    EDGE_WORKERS = {f"edge-worker-{i:02d}": {"x": random.randint(0, 1000), "y": random.randint(0, 1000)} for i in range(8)}
    CLOUD_WORKERS = [f"cloud-worker-{i:02d}" for i in range(3)]

# --- Logging Setup ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Scheduler] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- ML Model Service ---

class OffloadingScheduler:
    """Encapsulates the scheduling logic by loading and serving the ML model."""
    
    def __init__(self, model_path):
        """Loads the pre-trained ML model and encoder from disk."""
        try:
            logging.info(f"Loading ML model from {model_path}...")
            model_payload = joblib.load(model_path)
            self.model = model_payload['model']
            self.encoder = model_payload['encoder']
            logging.info("Model loaded successfully.")
        except FileNotFoundError:
            logging.critical(f"FATAL: Model file not found at '{model_path}'.")
            logging.critical("Please run 'create_model.py' first to generate the model file.")
            exit()

    def _calculate_closest_available_edge(self, patient_location, available_edge_workers):
        """Calculates the Euclidean distance to find the closest available edge worker."""
        if not available_edge_workers:
            return None
        min_dist_sq = float('inf')
        closest_worker = None
        px, py = patient_location['x'], patient_location['y']
        
        for worker_id in available_edge_workers:
            worker_loc = Config.EDGE_WORKERS[worker_id]
            dist_sq = (worker_loc['x'] - px)**2 + (worker_loc['y'] - py)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_worker = worker_id
        return closest_worker

    def decide(self, request_data):
        """The main decision function that implements the two-path logic."""
        task_info = request_data.get('task_info', {})
        system_state = request_data.get('system_state', {})
        available_workers = [w for w, s in system_state.get('worker_status', {}).items() if s == 'available']
        data_type = task_info.get('dataType', 'default-stream')

        # Path A: Deterministic Logic for Alerts
        if data_type in ['H', 'M', 'L']:
            # ... (This part is unchanged)
            logging.info(f"Alert '{data_type}' detected. Applying deterministic closest-edge logic.")
            available_edge = [w for w in available_workers if w in Config.EDGE_WORKERS]
            chosen_worker = self._calculate_closest_available_edge(task_info['location'], available_edge)
            if chosen_worker: return chosen_worker
            logging.warning(f"No edge workers available for alert '{data_type}'. Checking for cloud fallback.")
            available_cloud = [w for w in available_workers if w in Config.CLOUD_WORKERS]
            if available_cloud:
                cloud_worker = random.choice(available_cloud)
                logging.critical(f"EMERGENCY FALLBACK: Offloading alert for user {task_info.get('userId')} to cloud worker: {cloud_worker}")
                return cloud_worker
            return None

        # Path B: ML-based Logic for Default Stream
        else:
            logging.info("Default stream data. Applying ML-based scheduling.")
            
            # Create a Pandas DataFrame with the correct feature names
            # This ensures the data format matches what the model was trained on.
            features_df = pd.DataFrame([{
                'data_size_kb': task_info.get('size', 100),
                'network_latency': system_state.get('avg_network_latency', 50),
                'server_load': system_state.get('avg_server_load', 0.5),
                'cloud_cost_factor': system_state.get('cloud_cost_factor', 1.0)
            }])
            
            # Predict using the named DataFrame
            prediction_encoded = self.model.predict(features_df)
            predicted_worker = self.encoder.inverse_transform(prediction_encoded)[0]
            
            if predicted_worker in available_workers:
                logging.info(f"ML model chose available worker: {predicted_worker}")
                return predicted_worker
            else:
                logging.warning(f"ML model chose busy worker '{predicted_worker}'. Falling back to first available worker.")
                return available_workers[0] if available_workers else None

# --- Flask App ---
app = Flask(__name__)
scheduler = OffloadingScheduler(Config.MODEL_PATH)

@app.route("/predict", methods=["POST"])
def predict_offload_target():
    request_data = request.get_json()
    if not request_data:
        return jsonify({"error": "Invalid request body."}), 400

    chosen_worker = scheduler.decide(request_data)
    
    if chosen_worker:
        return jsonify({"assigned_worker": chosen_worker}), 200
    else:
        return jsonify({"error": "Could not determine an assignment. No workers available."}), 503

if __name__ == "__main__":
    app.run(host=Config.API_HOST, port=Config.API_PORT)