"""
Broker Workbench AI Agents

This module contains AI agents powered by Azure AI Foundry that assist
insurance brokers with:
- Quote comparison across carriers
- Cross-sell opportunity identification
- Claims impact analysis
- Natural language policy queries
"""

from .tools import (
    get_client_info,
    get_client_policies,
    get_policy_details,
    get_renewals_by_urgency,
    get_carriers_for_policy_type,
    compare_carrier_rates,
    get_coverage_gaps,
    get_claims_history,
)

from .quote_agent import QuoteComparisonAgent
from .crosssell_agent import CrossSellAgent
from .claims_agent import ClaimsImpactAgent
from .triage_agent import TriageAgent

__all__ = [
    # Agents
    "TriageAgent",
    # Tools
    "get_client_info",
    "get_client_policies", 
    "get_policy_details",
    "get_renewals_by_urgency",
    "get_carriers_for_policy_type",
    "compare_carrier_rates",
    "get_coverage_gaps",
    "get_claims_history",
    # Agents
    "QuoteComparisonAgent",
    "CrossSellAgent",
    "ClaimsImpactAgent",
]
