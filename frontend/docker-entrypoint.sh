#!/bin/sh
# ============================================================================
# Frontend Container Entrypoint
# ============================================================================
# Injects API_BACKEND_URL environment variable into the HTML
# ============================================================================

set -e

# Default to localhost if not set
API_BACKEND_URL=${API_BACKEND_URL:-http://localhost:8000}

echo "Configuring frontend with API_BACKEND_URL: $API_BACKEND_URL"

# Inject the API URL into the HTML by adding a script tag
# This sets window.API_BACKEND_URL before the main script runs
sed "s|<script>|<script>window.API_BACKEND_URL = '$API_BACKEND_URL';</script><script>|" \
    /usr/share/nginx/html/index.html.template > /usr/share/nginx/html/index.html

echo "Frontend configured successfully"

# Execute the main command (nginx)
exec "$@"
