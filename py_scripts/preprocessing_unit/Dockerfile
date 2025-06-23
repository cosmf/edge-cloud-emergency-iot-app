# Dockerfile for the Preprocessing Unit
#
# Build command: docker build -t edge-cloud-sim/preprocessing-unit:v1.0 -f preprocessing.Dockerfile .

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY preprocessing_unit.py .
CMD ["python", "preprocessing_unit.py"]
