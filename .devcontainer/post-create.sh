#!/usr/bin/env bash
# ============================================================================
# Post-create script for Dev Container
# ============================================================================
# Runs once after the container is created. Installs all project dependencies
# so the environment is ready to use immediately.
# ============================================================================
set -e

echo "=========================================="
echo " Broker Workbench - Dev Container Setup"
echo "=========================================="

# -------------------------------------------
# 1. Python backend dependencies
# -------------------------------------------
echo ""
echo ">> Setting up Python virtual environment..."
cd /workspaces/*/backend 2>/dev/null || cd /workspaces/Hackathon_v2/backend

python -m venv /workspaces/${PWD%%/backend}/venv 2>/dev/null || true

# Install into the workspace-level venv
VENV_DIR="$(cd .. && pwd)/venv"
python -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo ">> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyodbc  # For Azure SQL connectivity
pip install pytest httpx  # Dev/test dependencies

# -------------------------------------------
# 2. React frontend dependencies
# -------------------------------------------
echo ""
echo ">> Installing frontend dependencies..."
cd ../frontend-react
npm ci

# -------------------------------------------
# 3. Database setup
# -------------------------------------------
echo ""
echo ">> Setting up local SQLite database..."
cd ../data/db
python database_setup.py 2>/dev/null || echo "   (database setup skipped — may need .env values)"

# -------------------------------------------
# 4. Azure CLI login reminder
# -------------------------------------------
echo ""
echo "=========================================="
echo " Setup complete!"
echo "=========================================="
echo ""
echo " Quick start:"
echo "   Backend:  cd backend && uvicorn main:app --reload"
echo "   Frontend: cd frontend-react && npm run dev"
echo "   Full stack: docker-compose up (from repo root)"
echo ""
echo " To use Azure AI agents, run: az login"
echo "=========================================="
