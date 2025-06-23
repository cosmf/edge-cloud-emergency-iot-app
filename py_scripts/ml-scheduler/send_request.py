import requests
import json

# The URL where your scheduler service is running
SCHEDULER_URL = "http://127.0.0.1:5001/predict"

# --- Payload Option 1: Test the ML Path ---
payload_ml = {
    "task_info": {"recordId": "rec-001-abc", "userId": "user_042", "dataType": "default-stream", "size": 650, "location": { "x": 500, "y": 550 }},
    "system_state": {"worker_status": {"edge-worker-00": "available", "edge-worker-01": "busy", "edge-worker-02": "available", "cloud-worker-00": "available"}, "cloud_cost_factor": 0.6}
}

# --- Payload Option 2: Test the Alert Path (Closest Edge Server) ---
payload_alert = {
    "task_info": {"recordId": "rec-002-xyz", "userId": "user_011", "dataType": "H", "location": { "x": 10, "y": 10 }},
    "system_state": {"worker_status": {"edge-worker-00": "available", "edge-worker-01": "busy", "cloud-worker-00": "available"}}
}

# --- Payload Option 3: Test the Alert Path with Cloud Fallback ---
payload_alert_fallback = {
    "task_info": {"recordId": "rec-003-def", "userId": "user_025", "dataType": "H", "location": { "x": 800, "y": 800 }},
    "system_state": {"worker_status": {"edge-worker-00": "busy", "edge-worker-01": "busy", "cloud-worker-00": "available", "cloud-worker-01": "available"}}
}


def send_request(payload, description):
    """Sends a POST request to the scheduler and prints the response."""
    print(f"--- Sending Request: {description} ---")
    try:
        response = requests.post(SCHEDULER_URL, json=payload)
        
        print(f"Status Code: {response.status_code}")
        print("Response JSON:")
        print(json.dumps(response.json(), indent=2))
        print("-" * 30 + "\n")

    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error: Could not connect to the scheduler at {SCHEDULER_URL}.")
        print("Please ensure the 'scheduler.py' script is running in another terminal.")


if __name__ == "__main__":
    send_request(payload_ml, "Test ML-based Offloading")
    send_request(payload_alert, "Test High-Priority Alert (Closest Edge)")
    send_request(payload_alert_fallback, "Test Alert with Cloud Fallback")