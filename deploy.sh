#!/bin/bash

# Variables
PROJECT_DIR="/home/ec2-user/your-repo"
VENV_DIR="$PROJECT_DIR/venv"
LOG_FILE="$PROJECT_DIR/flask.log"
FLASK_APP="app.py"  # Change if your entry point is different

echo "=== Starting Deployment: $(date) ==="

# Navigate to project directory
cd "$PROJECT_DIR" || exit 1

# Pull latest changes from GitHub
echo "Pulling latest code from GitHub..."
git reset --hard
git pull origin main

# Activate virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Kill existing Flask process (if any)
echo "Killing existing Flask app (if running)..."
pkill -f "$FLASK_APP"

# Start the Flask app in the background using nohup
echo "Starting Flask app with nohup..."
nohup python "$FLASK_APP" > "$LOG_FILE" 2>&1 &

echo "Deployment complete. Flask app is running."
