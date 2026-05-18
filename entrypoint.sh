#!/bin/bash
set -e

URLPATH=${URLPATH:-dashboard}

echo "Replacing frontend URL path with: $URLPATH"

find /app/frontend/dist -type f \( -name "*.js" -o -name "*.css" -o -name "*.html" \) \
    -exec sed -i "s|__URLPATH__|$URLPATH|g" {} +

echo "Running migrations..."
cd /app/backend
uv run alembic upgrade head

echo "Starting server..."
cd /app
exec uv run python main.py