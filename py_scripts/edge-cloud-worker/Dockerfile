# Dockerfile for the Cloud-Edge Worker
#
# Build command: docker build -t edge-cloud-sim/cloud-edge-worker:v1.0 -f worker.Dockerfile .


FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cloud_edge_worker.py .
ENTRYPOINT ["python", "cloud_edge_worker.py"]
CMD ["default-worker-id"] # A default value if no ID is provided