#!/bin/bash

# Navigate to the script's directory
cd "$(dirname "$0")"

# Activate virtual environment
source .venv/bin/activate

# Start uvicorn in the background
nohup uvicorn main:app --host 127.0.0.1 --port 8000 > server.log 2>&1 &

echo "Server started in background. Logs are in backend/server.log"
