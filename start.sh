#!/bin/bash

# Railway Deployment Cache Bust - 2025-01-19
# Set default port if PORT environment variable is not set
PORT=${PORT:-8000}

echo "=== MirrorOS Public API Starting ==="
echo "PORT environment variable: ${PORT}"
echo "Starting gunicorn on port $PORT"

# Start gunicorn with the specified port
exec gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile - app:create_app