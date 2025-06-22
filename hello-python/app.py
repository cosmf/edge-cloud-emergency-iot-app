from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def hello():
    message = "Hello from your first microservice!"
    pod_name = os.environ.get('HOSTNAME', 'unknown pod')
    return f"<h1>{message}</h1><p>Running on pod: {pod_name}</p>"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)