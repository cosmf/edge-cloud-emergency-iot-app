# Dockerfile for the Data Producer
#
# Build command: docker build -t edge-cloud-sim/data-producer:v1.0 -f data-producer.Dockerfile .

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY smartwatch_producer_final.py .
# The GeoLife data should be mounted via a PersistentVolume in a real deployment
CMD ["python", "smartwatch_producer_final.py"]