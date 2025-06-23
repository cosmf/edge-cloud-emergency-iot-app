import kagglehub

# Download latest version
path = kagglehub.dataset_download("arashnic/microsoft-geolife-gps-trajectory-dataset")

print("Path to dataset files:", path)