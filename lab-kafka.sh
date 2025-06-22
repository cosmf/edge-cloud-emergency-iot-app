#!/bin/bash

# Install python 3.10
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev docker-compose-v2

docker compose up -d
