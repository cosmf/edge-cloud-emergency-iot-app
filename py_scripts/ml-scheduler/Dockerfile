# Use an official lightweight Python image as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first to leverage Docker's layer caching
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code AND the trained model file into the container
COPY scheduler.py .
COPY scheduler_model.joblib .

# Expose the port the scheduler's API server will run on
EXPOSE 5001

# Define the command to run the scheduler application
CMD ["python", "scheduler.py"]
