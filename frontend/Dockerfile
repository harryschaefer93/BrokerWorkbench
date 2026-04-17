# ============================================================================
# Broker Workbench - Frontend Container (nginx)
# ============================================================================
# Simple nginx container serving static HTML/CSS/JS
# Injects API_BACKEND_URL at runtime via environment variable
# ============================================================================

FROM nginx:alpine

# Install envsubst for environment variable substitution
RUN apk add --no-cache gettext

# Copy static files to nginx html directory
COPY index.html /usr/share/nginx/html/index.html.template

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Use custom entrypoint to inject environment variables
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
