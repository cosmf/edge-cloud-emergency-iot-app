FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY orchestrator.py .
# COPY ./analysis/ ./analysis/ # Uncomment if you have an analysis directory
EXPOSE 5000
CMD ["python", "orchestrator.py"]