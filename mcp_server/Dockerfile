# ============================================================================
# Broker Workbench - MCP Server Container
# ============================================================================
# Wraps the 10 broker-domain tools as a Model Context Protocol server
# (streamable-http transport) for the Foundry Agent Service to consume.
#
# Build context MUST be the repo root so we can COPY both mcp_server/ and
# backend/db/ (the MCP tools import backend's SQLAlchemy session factories
# directly to avoid duplicating connection logic).
# ============================================================================

FROM python:3.11-slim

WORKDIR /app

# OS deps for aioodbc / Azure SQL parity (mirrors backend/Dockerfile minus
# the Azure CLI bits — the MCP server makes no Azure calls of its own).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc-dev \
    ca-certificates \
    apt-transport-https \
    lsb-release \
    gcc \
    g++ \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY mcp_server/requirements.txt /app/mcp_server/requirements.txt
RUN pip install --no-cache-dir -r /app/mcp_server/requirements.txt
RUN pip install --no-cache-dir pyodbc

# Copy the MCP server package
COPY mcp_server/ /app/mcp_server/

# Copy backend db package — connection.py + models.py + repository.py are
# the shared DB layer. `backend.db.connection` uses `from db.models import …`
# (absolute), so we also expose /app/backend on PYTHONPATH.
COPY backend/db/ /app/backend/db/
# Make `backend` a regular package so `from backend.db.connection import …` works.
RUN touch /app/backend/__init__.py

ENV PYTHONPATH=/app:/app/backend

# Non-root user (matches backend pattern). Pre-create /app/data so the named
# volume mount from docker-compose (broker_db:/app/data) is writable on boot.
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl --fail http://localhost:8001/mcp -H "Accept: application/json" || exit 1

CMD ["python", "-m", "mcp_server.server"]
