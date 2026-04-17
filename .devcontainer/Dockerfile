# ============================================================================
# Broker Workbench - Dev Container
# ============================================================================
# Python 3.11 + Node 20 + ODBC drivers + Azure CLI
# ============================================================================

FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# Node.js is installed via devcontainer feature (see devcontainer.json)

# Install ODBC Driver 18 for SQL Server (matches production Dockerfile)
# Remove stale Yarn repo (expired GPG key in base image) before apt-get update
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Azure CLI
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Install Bicep CLI (for infra deployment)
RUN az bicep install

# Set default shell to zsh for better dev experience
ENV SHELL=/bin/zsh
