#!/bin/bash
set -e

echo "Running migrations..."
cd /app/backend
uv run alembic upgrade head

echo "Starting server..."
cd /app
exec uv run python main.py

echo "Press Ctrl+C to exit log."