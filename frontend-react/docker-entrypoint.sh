#!/bin/sh
# Substitute API_BACKEND_URL into nginx config at container start
# Default to http://backend:8000 for docker-compose compatibility
export API_BACKEND_URL="${API_BACKEND_URL:-http://backend:8000}"
envsubst '${API_BACKEND_URL}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf
