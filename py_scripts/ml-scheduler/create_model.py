# create_model.py
#
# This script creates an enhanced synthetic dataset based on realistic operational
# scenarios. It then trains and saves the ML model for the scheduler service.

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
NUM_SAMPLES = 4000
EDGE_WORKERS = [f"edge-worker-{i:02d}" for i in range(8)]
CLOUD_WORKERS = [f"cloud-worker-{i:02d}" for i in range(3)]

def generate_training_data():
    """Generates a synthetic dataset based on specific, logical scenarios."""
    logging.info("Generating scenario-based training data...")
    data = []
    
    for _ in range(NUM_SAMPLES):
        scenario = np.random.choice(['IDEAL_EDGE', 'CONGESTED_EDGE', 'BIG_DATA', 'EXPENSIVE_CLOUD'])
        
        # Default values
        data_size_kb = np.random.randint(10, 200)
        network_latency = np.random.uniform(10, 40)
        server_load = np.random.uniform(0.1, 0.4)
        cloud_cost_factor = np.random.uniform(0.8, 1.2)
        
        # Modify defaults based on scenario
        if scenario == 'CONGESTED_EDGE':
            server_load = np.random.uniform(0.9, 0.99)
            network_latency = np.random.uniform(100, 200)
        elif scenario == 'BIG_DATA':
            data_size_kb = np.random.randint(800, 2000)
        elif scenario == 'EXPENSIVE_CLOUD':
            cloud_cost_factor = np.random.uniform(1.5, 2.0)
            
        # Determine the optimal target worker based on the scenario's features
        chosen_worker = ""
        if scenario == 'CONGESTED_EDGE' or scenario == 'BIG_DATA':
            # In these cases, the powerful cloud is the best choice
            chosen_worker = np.random.choice(CLOUD_WORKERS)
        elif scenario == 'EXPENSIVE_CLOUD':
            # When cloud is expensive, we tolerate a busy edge worker
            chosen_worker = np.random.choice(EDGE_WORKERS)
        else: # IDEAL_EDGE
            chosen_worker = np.random.choice(EDGE_WORKERS)
            
        data.append([data_size_kb, network_latency, server_load, cloud_cost_factor, chosen_worker])
        
    df = pd.DataFrame(data, columns=['data_size_kb', 'network_latency', 'server_load', 'cloud_cost_factor', 'target_worker'])
    logging.info(f"Generated {len(df)} data samples across 4 scenarios.")
    return df

def train_and_save_model(df):
    """Trains the model and saves it."""
    logging.info("Starting model training...")
    X = df[['data_size_kb', 'network_latency', 'server_load', 'cloud_cost_factor']]
    y = df['target_worker']
    
    encoder = LabelEncoder()
    y_encoded = encoder.fit_transform(y)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X, y_encoded)
    
    logging.info("Model training complete.")
    joblib.dump({'model': model, 'encoder': encoder}, 'scheduler_model.joblib')
    logging.info("Model and encoder saved to 'scheduler_model.joblib'.")

if __name__ == "__main__":
    dataset = generate_training_data()
    train_and_save_model(dataset)
    print("\nEnhanced model creation complete.")