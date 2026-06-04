# Broker Workbench MCP Server

A standalone Model Context Protocol (MCP) server that exposes the 10
broker-domain tools as a streamable-HTTP endpoint for the Foundry Agent
Service to consume. Wraps the broker SQL database (carriers, clients,
policies, claims, market_rates).

See [`docs/FIELDDAY_PLAN.md`](../docs/FIELDDAY_PLAN.md) Phase A for the
broader rearchitecture context.

## Boot (Docker)

```bash
docker-compose up mcp_server
```

The server listens on `http://localhost:8001/mcp` and shares the
`broker_db` named volume with the backend, so it sees the same
SQLite database.

## Boot (local dev, no Docker)

```bash
pip install -r mcp_server/requirements.txt
# Point at the local broker database files:
$env:DATABASE_URL = "sqlite+aiosqlite:///./data/db/transactional_data.db"
$env:MASTER_DATABASE_URL = "sqlite+aiosqlite:///./data/db/master_data.db"
python -m mcp_server.server
# In another shell:
mcp inspect http://localhost:8001/mcp
```

## Tools (10)

| Tool | Input | Output |
| --- | --- | --- |
| `get_client_info` | `client_id` | client dict + policy summary |
| `get_all_clients` | – | list of clients with totals |
| `get_client_policies` | `client_id` | list of policies + carrier + urgency |
| `get_policy_details` | `policy_id` | full policy dict + renewal scores |
| `get_renewals_by_urgency` | `urgency?`, `days_ahead` | renewal summary + list |
| `get_carriers_for_policy_type` | `policy_type` | carriers sorted by AM Best |
| `compare_carrier_rates` | `policy_type`, `coverage_limit`, `industry`, `annual_revenue?` | quotes from the `market_rates` table |
| `get_coverage_gaps` | `client_id` | gap analysis + cross-sell opportunities |
| `get_claims_history` | `client_id` | year buckets + 3yr loss ratio + recs |
| `get_loss_ratio_trend` | `client_id` | yearly loss-ratio trend + direction |

The 3 formerly-simulated tools (`get_claims_history`,
`get_loss_ratio_trend`, `compare_carrier_rates`) now read from the broker
database. They mark `"source": "broker_db"` in their responses.

## ID convention

The agent-facing API uses zero-padded prefixed strings; the DB stores
plain ints. Conversion is handled in [`db.py`](db.py).

| String | Int | Helper |
| --- | --- | --- |
| `CLI001` | 1 | `cli_to_int`, `int_to_cli` |
| `POL001` | 1 | `pol_to_int`, `int_to_pol` |
| `CAR001` | 1 | `carrier_to_int`, `int_to_carrier` |

Inputs accept either bare ints-as-strings (`"5"`) or the prefixed form;
all outputs use the prefixed form.
