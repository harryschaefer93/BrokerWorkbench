"""
Canonical demo vocabulary for the BrokerWorkbench Field Day seed.

These constants are the single source of truth for industries, product types,
claim frequency/severity baselines, and recommended product mixes. The setup
loader (`data.seed.setup`) and the description generator
(`data.seed.descriptions`) both import from here so the demo data tells a
coherent story.
"""

INDUSTRIES = [
    "Technology", "Healthcare", "Manufacturing", "Construction",
    "Transportation", "Retail", "Professional Services",
]

# product_category values used on Policy.product_category (lowercase, snake_case)
PRODUCT_TYPES = [
    "commercial_property", "general_liability", "workers_comp",
    "commercial_auto", "professional_liability", "cyber_liability", "umbrella",
]

# Industry → claim frequency multiplier (claims per policy per year, baseline 0.15)
INDUSTRY_CLAIM_FREQUENCY = {
    "Technology": 0.10, "Healthcare": 0.25, "Manufacturing": 0.20,
    "Construction": 0.35, "Transportation": 0.30, "Retail": 0.15,
    "Professional Services": 0.12,
}

# Industry → average claim severity (USD)
INDUSTRY_CLAIM_SEVERITY = {
    "Technology": 15_000, "Healthcare": 75_000, "Manufacturing": 25_000,
    "Construction": 45_000, "Transportation": 35_000, "Retail": 18_000,
    "Professional Services": 22_000,
}

# Industry → recommended product types (used to weight policy generation)
INDUSTRY_RECOMMENDED_PRODUCTS = {
    "Technology": ["cyber_liability", "professional_liability", "general_liability", "commercial_property"],
    "Healthcare": ["professional_liability", "general_liability", "cyber_liability", "commercial_property", "workers_comp"],
    "Manufacturing": ["commercial_property", "general_liability", "workers_comp", "commercial_auto", "umbrella"],
    "Construction": ["general_liability", "workers_comp", "commercial_auto", "umbrella", "professional_liability"],
    "Transportation": ["commercial_auto", "general_liability", "workers_comp", "umbrella", "commercial_property"],
    "Retail": ["commercial_property", "general_liability", "workers_comp", "commercial_auto"],
    "Professional Services": ["professional_liability", "cyber_liability", "general_liability", "commercial_property"],
}

# Base annual rate per $1M of coverage per product type
PRODUCT_BASE_RATE_PER_M = {
    "commercial_property": 800, "general_liability": 1200, "workers_comp": 2500,
    "commercial_auto": 3500, "professional_liability": 1500,
    "cyber_liability": 2000, "umbrella": 500,
}

# Claim types per product line (used for description generation)
PRODUCT_CLAIM_TYPES = {
    "commercial_property": ["fire", "water_damage", "theft", "vandalism", "storm"],
    "general_liability": ["slip_and_fall", "product_liability", "bodily_injury", "property_damage"],
    "workers_comp": ["back_injury", "repetitive_strain", "fall", "vehicle_accident", "chemical_exposure"],
    "commercial_auto": ["collision", "rear_end", "comprehensive", "uninsured_motorist"],
    "professional_liability": ["errors_omissions", "missed_deadline", "negligent_advice"],
    "cyber_liability": ["data_breach", "ransomware", "phishing", "business_email_compromise"],
    "umbrella": ["excess_liability_gl", "excess_liability_auto"],
}
