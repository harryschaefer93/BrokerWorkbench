-- ============================================================
-- Insurance Broker Workbench - Full Azure SQL Setup
-- Run in Azure Portal Query Editor as AAD admin
-- Creates schemas, tables, and seeds all data
-- ============================================================

-- ============================================================
-- PART 1: MASTER DATA SCHEMA + TABLES
-- ============================================================

-- Carriers table
CREATE TABLE master_data.carriers (
    carrier_id INT IDENTITY(1,1) PRIMARY KEY,
    carrier_name VARCHAR(100) NOT NULL,
    carrier_code VARCHAR(10) UNIQUE NOT NULL,
    api_endpoint VARCHAR(255),
    api_status VARCHAR(20) DEFAULT 'active',
    rating VARCHAR(10),
    specialty_lines VARCHAR(MAX),
    market_share DECIMAL(5,2),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Clients table (Master data)
CREATE TABLE master_data.clients (
    client_id INT IDENTITY(1,1) PRIMARY KEY,
    client_name VARCHAR(200) NOT NULL,
    client_type VARCHAR(20) NOT NULL,
    business_industry VARCHAR(100),
    primary_contact_name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(20),
    address_line1 VARCHAR(200),
    address_line2 VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    zip_code VARCHAR(10),
    risk_score INT DEFAULT 50,
    customer_since DATE,
    total_premium_ytd DECIMAL(12,2) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Product Lines table
CREATE TABLE master_data.product_lines (
    product_id INT IDENTITY(1,1) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    product_category VARCHAR(50) NOT NULL,
    base_premium_range VARCHAR(50),
    risk_factors VARCHAR(MAX),
    coverage_options VARCHAR(MAX),
    target_market VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Market Rates table
CREATE TABLE master_data.market_rates (
    rate_id INT IDENTITY(1,1) PRIMARY KEY,
    carrier_id INT,
    product_category VARCHAR(50),
    risk_profile VARCHAR(50),
    base_rate DECIMAL(10,2),
    rate_factor DECIMAL(5,3),
    effective_date DATE,
    expiration_date DATE,
    market_region VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES master_data.carriers (carrier_id)
);
GO

-- ============================================================
-- PART 2: TRANSACTIONAL SCHEMA + TABLES
-- ============================================================

-- Policies table
CREATE TABLE txn.policies (
    policy_id INT IDENTITY(1,1) PRIMARY KEY,
    policy_number VARCHAR(50) UNIQUE NOT NULL,
    client_id INT NOT NULL,
    carrier_id INT NOT NULL,
    product_category VARCHAR(50) NOT NULL,
    policy_status VARCHAR(20) DEFAULT 'active',
    premium_amount DECIMAL(12,2),
    deductible DECIMAL(10,2),
    coverage_limit DECIMAL(15,2),
    effective_date DATE,
    expiration_date DATE,
    renewal_date DATE,
    auto_renew BIT DEFAULT 1,
    commission_rate DECIMAL(5,2),
    commission_amount DECIMAL(10,2),
    last_review_date DATE,
    notes VARCHAR(MAX),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Quotes table
CREATE TABLE txn.quotes (
    quote_id INT IDENTITY(1,1) PRIMARY KEY,
    client_id INT NOT NULL,
    carrier_id INT NOT NULL,
    product_category VARCHAR(50),
    quote_number VARCHAR(50),
    quoted_premium DECIMAL(12,2),
    coverage_details VARCHAR(MAX),
    quote_status VARCHAR(20) DEFAULT 'pending',
    valid_until DATE,
    competitive_position VARCHAR(20),
    savings_vs_current DECIMAL(10,2),
    quote_source VARCHAR(50),
    response_time_seconds INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    presented_at DATETIME,
    decision_at DATETIME
);

-- Tasks table
CREATE TABLE txn.tasks (
    task_id INT IDENTITY(1,1) PRIMARY KEY,
    client_id INT,
    policy_id INT,
    task_type VARCHAR(50) NOT NULL,
    priority_level VARCHAR(10) NOT NULL,
    task_title VARCHAR(200) NOT NULL,
    task_description VARCHAR(MAX),
    due_date DATE,
    status VARCHAR(20) DEFAULT 'pending',
    assigned_to VARCHAR(100),
    potential_value DECIMAL(12,2),
    completion_notes VARCHAR(MAX),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    FOREIGN KEY (policy_id) REFERENCES txn.policies (policy_id)
);

-- Claims table
CREATE TABLE txn.claims (
    claim_id INT IDENTITY(1,1) PRIMARY KEY,
    policy_id INT NOT NULL,
    claim_number VARCHAR(50) UNIQUE NOT NULL,
    claim_type VARCHAR(50),
    claim_amount DECIMAL(12,2),
    claim_status VARCHAR(30) DEFAULT 'reported',
    date_of_loss DATE,
    reported_date DATE,
    description VARCHAR(MAX),
    adjuster_name VARCHAR(100),
    settlement_amount DECIMAL(12,2),
    impact_on_renewal VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (policy_id) REFERENCES txn.policies (policy_id)
);

-- AI Interactions table
CREATE TABLE txn.ai_interactions (
    interaction_id INT IDENTITY(1,1) PRIMARY KEY,
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    interaction_type VARCHAR(50),
    user_query VARCHAR(MAX),
    ai_response VARCHAR(MAX),
    context_data VARCHAR(MAX),
    confidence_score DECIMAL(3,2),
    feedback_rating INT,
    processing_time_ms INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Documents table
CREATE TABLE txn.documents (
    document_id INT IDENTITY(1,1) PRIMARY KEY,
    client_id INT,
    policy_id INT,
    document_type VARCHAR(50),
    document_name VARCHAR(255),
    file_path VARCHAR(500),
    file_size_bytes INT,
    mime_type VARCHAR(100),
    generated_by VARCHAR(50),
    tags VARCHAR(MAX),
    last_accessed DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Cross-sell Opportunities table
CREATE TABLE txn.cross_sell_opportunities (
    opportunity_id INT IDENTITY(1,1) PRIMARY KEY,
    client_id INT NOT NULL,
    current_product_category VARCHAR(50),
    recommended_product_category VARCHAR(50),
    opportunity_type VARCHAR(50),
    estimated_premium DECIMAL(10,2),
    confidence_score DECIMAL(3,2),
    status VARCHAR(20) DEFAULT 'identified',
    reasoning VARCHAR(MAX),
    ai_generated BIT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    presented_at DATETIME,
    decision_at DATETIME
);
GO

-- ============================================================
-- PART 3: SEED MASTER DATA
-- ============================================================

-- Carriers
INSERT INTO master_data.carriers (carrier_name, carrier_code, api_endpoint, api_status, rating, specialty_lines, market_share) VALUES
('State Farm', 'SF', 'https://api.statefarm.com/v1', 'connected', 'A+', 'Auto,Home,Life', 18.5),
('Allstate', 'AS', 'https://api.allstate.com/quotes', 'connected', 'A+', 'Auto,Home,Commercial', 9.2),
('Progressive', 'PG', 'https://api.progressive.com/rating', 'slow', 'A', 'Auto,Commercial', 12.1),
('Geico', 'GE', 'https://geico-partner.com/api', 'offline', 'A++', 'Auto,Umbrella', 14.8),
('Liberty Mutual', 'LM', 'https://api.libertymutual.com', 'connected', 'A', 'Commercial,Auto', 6.3),
('Travelers', 'TR', 'https://travelers-api.com/v2', 'connected', 'A++', 'Commercial,Home', 4.1),
('Nationwide', 'NW', 'https://api.nationwide.com', 'connected', 'A+', 'Auto,Home,Commercial', 3.8),
('USAA', 'US', 'https://usaa-partners.com/api', 'connected', 'A++', 'Auto,Home,Life', 2.9);

-- Clients
INSERT INTO master_data.clients (client_name, client_type, business_industry, primary_contact_name, email, phone, address_line1, address_line2, city, state, zip_code, risk_score, customer_since, total_premium_ytd) VALUES
('Smith Family', 'individual', NULL, 'John Smith', 'john.smith@email.com', '555-0101', '123 Main St', '', 'Springfield', 'IL', '62701', 25, '2019-03-15', 2400.00),
('ABC Corporation', 'business', 'Manufacturing', 'Sarah Johnson', 'sarah@abccorp.com', '555-0202', '456 Business Ave', 'Suite 200', 'Chicago', 'IL', '60601', 75, '2020-01-10', 15600.00),
('Davis Enterprise', 'business', 'Technology', 'Mike Davis', 'mike@davisenterprise.com', '555-0303', '789 Tech Blvd', '', 'Naperville', 'IL', '60540', 45, '2021-06-20', 8900.00),
('Johnson Family', 'individual', NULL, 'Emily Johnson', 'emily.johnson@email.com', '555-0404', '321 Oak Street', '', 'Peoria', 'IL', '61601', 30, '2018-09-12', 3200.00),
('Williams Auto Group', 'business', 'Automotive', 'Robert Williams', 'rob@williamsauto.com', '555-0505', '654 Commerce St', '', 'Rockford', 'IL', '61101', 60, '2019-11-08', 22400.00),
('Anderson Family', 'individual', NULL, 'Lisa Anderson', 'lisa.anderson@email.com', '555-0606', '987 Pine Ave', '', 'Champaign', 'IL', '61820', 20, '2022-02-14', 1800.00);

-- Product Lines
INSERT INTO master_data.product_lines (product_name, product_category, base_premium_range, risk_factors, coverage_options, target_market) VALUES
('Personal Auto Insurance', 'auto', '$1,200-$4,000', '["age", "driving_record", "vehicle_type", "location"]', '["liability", "collision", "comprehensive", "uninsured_motorist"]', 'Individual drivers and families'),
('Homeowners Insurance', 'home', '$800-$3,500', '["property_value", "location", "age_of_home", "security_features"]', '["dwelling", "personal_property", "liability", "additional_living_expenses"]', 'Homeowners'),
('Commercial Auto', 'commercial', '$2,500-$25,000', '["fleet_size", "driver_profiles", "business_use", "cargo_type"]', '["liability", "physical_damage", "cargo", "hired_auto"]', 'Business fleets'),
('General Liability', 'commercial', '$500-$15,000', '["business_type", "revenue", "employee_count", "location"]', '["bodily_injury", "property_damage", "personal_injury", "products_liability"]', 'All businesses'),
('Umbrella Policy', 'umbrella', '$200-$800', '["underlying_limits", "assets", "risk_exposure"]', '["excess_liability", "worldwide_coverage"]', 'High-net-worth individuals and businesses');

-- Market Rates (representative sample for all 8 carriers x 4 categories x 3 risk levels)
INSERT INTO master_data.market_rates (carrier_id, product_category, risk_profile, base_rate, rate_factor, effective_date, expiration_date, market_region) VALUES
-- State Farm (carrier_id=1)
(1, 'auto', 'low', 1250.00, 0.90, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'auto', 'medium', 1850.00, 1.15, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'auto', 'high', 2400.00, 1.55, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'home', 'low', 1100.00, 0.88, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'home', 'medium', 1650.00, 1.10, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'home', 'high', 2200.00, 1.45, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'commercial', 'low', 2800.00, 0.92, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'commercial', 'medium', 1900.00, 1.20, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'commercial', 'high', 2600.00, 1.60, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'umbrella', 'low', 950.00, 0.85, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'umbrella', 'medium', 1400.00, 1.05, '2025-01-01', '2025-12-31', 'Illinois'),
(1, 'umbrella', 'high', 1800.00, 1.50, '2025-01-01', '2025-12-31', 'Illinois'),
-- Allstate (carrier_id=2)
(2, 'auto', 'low', 1300.00, 0.92, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'auto', 'medium', 1750.00, 1.12, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'auto', 'high', 2350.00, 1.48, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'home', 'low', 1050.00, 0.86, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'home', 'medium', 1700.00, 1.08, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'home', 'high', 2350.00, 1.42, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'commercial', 'low', 2650.00, 0.95, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'commercial', 'medium', 2100.00, 1.18, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'commercial', 'high', 2750.00, 1.55, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'umbrella', 'low', 900.00, 0.88, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'umbrella', 'medium', 1350.00, 1.10, '2025-01-01', '2025-12-31', 'Illinois'),
(2, 'umbrella', 'high', 1900.00, 1.45, '2025-01-01', '2025-12-31', 'Illinois'),
-- Progressive (carrier_id=3)
(3, 'auto', 'low', 1150.00, 0.88, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'auto', 'medium', 1900.00, 1.18, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'auto', 'high', 2500.00, 1.62, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'home', 'low', 1200.00, 0.90, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'home', 'medium', 1550.00, 1.12, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'home', 'high', 2100.00, 1.48, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'commercial', 'low', 2900.00, 0.90, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'commercial', 'medium', 2000.00, 1.22, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'commercial', 'high', 2850.00, 1.65, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'umbrella', 'low', 1000.00, 0.82, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'umbrella', 'medium', 1500.00, 1.08, '2025-01-01', '2025-12-31', 'Illinois'),
(3, 'umbrella', 'high', 1950.00, 1.52, '2025-01-01', '2025-12-31', 'Illinois'),
-- Geico (carrier_id=4)
(4, 'auto', 'low', 1180.00, 0.85, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'auto', 'medium', 1800.00, 1.10, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'auto', 'high', 2450.00, 1.50, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'home', 'low', 1080.00, 0.92, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'home', 'medium', 1600.00, 1.15, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'home', 'high', 2250.00, 1.40, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'commercial', 'low', 2700.00, 0.88, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'commercial', 'medium', 1950.00, 1.25, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'commercial', 'high', 2900.00, 1.58, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'umbrella', 'low', 920.00, 0.86, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'umbrella', 'medium', 1380.00, 1.12, '2025-01-01', '2025-12-31', 'Illinois'),
(4, 'umbrella', 'high', 1850.00, 1.48, '2025-01-01', '2025-12-31', 'Illinois'),
-- Liberty Mutual (carrier_id=5)
(5, 'auto', 'low', 1350.00, 0.95, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'auto', 'medium', 1950.00, 1.20, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'auto', 'high', 2550.00, 1.58, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'home', 'low', 1150.00, 0.84, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'home', 'medium', 1680.00, 1.06, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'home', 'high', 2300.00, 1.44, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'commercial', 'low', 2550.00, 0.94, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'commercial', 'medium', 2050.00, 1.15, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'commercial', 'high', 2700.00, 1.62, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'umbrella', 'low', 980.00, 0.90, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'umbrella', 'medium', 1420.00, 1.15, '2025-01-01', '2025-12-31', 'Illinois'),
(5, 'umbrella', 'high', 1880.00, 1.55, '2025-01-01', '2025-12-31', 'Illinois'),
-- Travelers (carrier_id=6)
(6, 'auto', 'low', 1280.00, 0.88, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'auto', 'medium', 1820.00, 1.14, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'auto', 'high', 2380.00, 1.52, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'home', 'low', 1120.00, 0.85, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'home', 'medium', 1620.00, 1.08, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'home', 'high', 2180.00, 1.46, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'commercial', 'low', 2750.00, 0.92, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'commercial', 'medium', 2150.00, 1.20, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'commercial', 'high', 2800.00, 1.58, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'umbrella', 'low', 940.00, 0.84, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'umbrella', 'medium', 1360.00, 1.06, '2025-01-01', '2025-12-31', 'Illinois'),
(6, 'umbrella', 'high', 1920.00, 1.50, '2025-01-01', '2025-12-31', 'Illinois'),
-- Nationwide (carrier_id=7)
(7, 'auto', 'low', 1220.00, 0.92, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'auto', 'medium', 1780.00, 1.16, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'auto', 'high', 2420.00, 1.54, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'home', 'low', 1060.00, 0.90, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'home', 'medium', 1580.00, 1.12, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'home', 'high', 2150.00, 1.42, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'commercial', 'low', 2600.00, 0.90, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'commercial', 'medium', 2080.00, 1.18, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'commercial', 'high', 2720.00, 1.60, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'umbrella', 'low', 960.00, 0.86, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'umbrella', 'medium', 1440.00, 1.10, '2025-01-01', '2025-12-31', 'Illinois'),
(7, 'umbrella', 'high', 1860.00, 1.48, '2025-01-01', '2025-12-31', 'Illinois'),
-- USAA (carrier_id=8)
(8, 'auto', 'low', 1100.00, 0.84, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'auto', 'medium', 1700.00, 1.08, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'auto', 'high', 2300.00, 1.46, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'home', 'low', 1000.00, 0.82, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'home', 'medium', 1520.00, 1.04, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'home', 'high', 2080.00, 1.38, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'commercial', 'low', 2500.00, 0.88, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'commercial', 'medium', 1980.00, 1.14, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'commercial', 'high', 2650.00, 1.56, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'umbrella', 'low', 880.00, 0.82, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'umbrella', 'medium', 1320.00, 1.04, '2025-01-01', '2025-12-31', 'Illinois'),
(8, 'umbrella', 'high', 1780.00, 1.42, '2025-01-01', '2025-12-31', 'Illinois');
GO

-- ============================================================
-- PART 4: SEED TRANSACTIONAL DATA
-- ============================================================

-- Policies
INSERT INTO txn.policies (policy_number, client_id, carrier_id, product_category, policy_status, premium_amount, deductible, coverage_limit, effective_date, expiration_date, renewal_date, auto_renew, commission_rate, commission_amount, last_review_date, notes) VALUES
('POL12344', 1, 1, 'auto', 'renewal_due', 2400.00, 500.00, 300000.00, '2025-02-01', '2026-02-01', '2026-01-15', 1, 12.5, 300.00, '2025-12-01', 'Family auto policy, good driving record'),
('POL98765', 2, 2, 'commercial', 'active', 15600.00, 2500.00, 1000000.00, '2025-08-15', '2026-08-15', '2026-07-15', 1, 15.0, 2340.00, '2025-10-01', 'Manufacturing business, multiple vehicles'),
('POL54321', 3, 3, 'auto', 'active', 1800.00, 750.00, 250000.00, '2025-06-01', '2026-06-01', '2026-05-15', 1, 12.0, 216.00, '2025-11-01', 'New client, good credit score'),
('POL67890', 4, 1, 'home', 'active', 3200.00, 1000.00, 500000.00, '2025-03-01', '2026-03-01', '2026-02-15', 1, 14.0, 448.00, '2025-09-01', 'Single family home, updated systems'),
('POL11111', 5, 2, 'commercial', 'active', 22400.00, 5000.00, 2000000.00, '2025-11-01', '2026-11-01', '2026-10-15', 1, 16.0, 3584.00, '2025-12-15', 'Auto dealership, multiple locations'),
('POL22222', 6, 4, 'auto', 'active', 1800.00, 500.00, 300000.00, '2025-12-01', '2026-12-01', '2026-11-15', 1, 11.5, 207.00, '2026-01-01', 'Recent customer, clean record');

-- Quotes
INSERT INTO txn.quotes (client_id, carrier_id, product_category, quote_number, quoted_premium, coverage_details, quote_status, valid_until, competitive_position, savings_vs_current, quote_source, response_time_seconds, created_at) VALUES
(1, 1, 'auto', 'QT-SF-001', 2280.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'presented', '2026-02-15', 'current', 120.00, 'api', 2, '2026-01-25 10:30:00'),
(1, 2, 'auto', 'QT-AS-001', 2150.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'presented', '2026-02-15', 'best', 250.00, 'api', 3, '2026-01-25 10:32:00'),
(1, 3, 'auto', 'QT-PG-001', 2090.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'presented', '2026-02-15', 'best', 310.00, 'api', 8, '2026-01-25 10:35:00'),
(1, 4, 'auto', 'QT-GE-001', 2050.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'pending', '2026-02-15', 'best', 350.00, 'manual', NULL, '2026-01-25 11:00:00');

-- Tasks
INSERT INTO txn.tasks (client_id, policy_id, task_type, priority_level, task_title, task_description, due_date, status, assigned_to, potential_value, completion_notes) VALUES
(1, 1, 'renewal', 'high', 'Smith Family - Auto Renewal', 'Review renewal options and present quotes', '2026-02-03', 'in_progress', 'John Broker', 2400.00, NULL),
(2, NULL, 'follow_up', 'high', 'ABC Corp - Claim Review', 'Review $45,000 claim and assess impact', '2026-01-31', 'pending', 'John Broker', 45000.00, NULL),
(3, NULL, 'follow_up', 'medium', 'Follow up: Davis Enterprise', 'Quote was requested 2 days ago, follow up needed', '2026-02-01', 'pending', 'John Broker', 8900.00, NULL),
(4, 4, 'cross_sell', 'low', 'Johnson Annual Review', 'Annual policy review scheduled', '2026-02-10', 'pending', 'John Broker', 3200.00, NULL),
(1, NULL, 'cross_sell', 'medium', 'Smith Family - Home Insurance', 'Auto policy holder with no home insurance', '2026-02-05', 'identified', 'John Broker', 1500.00, NULL),
(4, NULL, 'cross_sell', 'medium', 'Johnson Family - Umbrella Policy', 'Teen driver added, recommend umbrella coverage', '2026-02-07', 'identified', 'John Broker', 285.00, NULL);

-- Claims
INSERT INTO txn.claims (policy_id, claim_number, claim_type, claim_amount, claim_status, date_of_loss, reported_date, description, adjuster_name, settlement_amount, impact_on_renewal) VALUES
(2, 'CLM-ABC-001', 'property_damage', 45000.00, 'investigating', '2025-12-15', '2025-12-16', 'Equipment damage due to electrical surge', 'Jane Adjuster', NULL, 'minor'),
(1, 'CLM-SF-002', 'auto_accident', 8500.00, 'settled', '2025-10-10', '2025-10-11', 'Rear-end collision, minor injuries', 'Bob Claims', 7200.00, 'none');

-- AI Interactions
INSERT INTO txn.ai_interactions (user_id, session_id, interaction_type, user_query, ai_response, context_data, confidence_score, feedback_rating, processing_time_ms) VALUES
('john.broker', 'sess_001', 'insight', 'Show me high-risk clients', 'Based on your portfolio analysis, I found 3 clients requiring attention: ABC Corp (active claim), Williams Auto Group (high fleet exposure), and Smith Family (teen driver added). Would you like detailed recommendations for each?', '{"client_ids": [2, 5, 1], "risk_factors": ["active_claims", "fleet_size", "young_drivers"]}', 0.89, 5, 1250),
('john.broker', 'sess_002', 'recommendation', 'Best cross-sell opportunities?', 'Top opportunities: 1) Smith Family - Home insurance ($1,200-1,800 est.), 2) Johnson Family - Umbrella policy ($285 est.), 3) Anderson Family - Auto + Home bundle (15% savings). These represent $45K potential new premium.', '{"opportunities": [{"client_id": 1, "product": "home"}, {"client_id": 4, "product": "umbrella"}]}', 0.92, 4, 890),
('john.broker', 'sess_003', 'summary', 'Summarize Smith Family renewal', 'Smith Family auto renewal summary: Current premium $2,400 with State Farm. Best quotes: Geico $2,050 (save $350), Progressive $2,090 (save $310), Allstate $2,150 (save $250). Recommend presenting Geico quote with umbrella policy option ($285). Total opportunity: $635 savings + new premium.', '{"client_id": 1, "policy_id": 1, "quotes": [2050, 2090, 2150], "cross_sell": "umbrella"}', 0.95, 5, 780);

-- Documents
INSERT INTO txn.documents (client_id, policy_id, document_type, document_name, file_path, file_size_bytes, mime_type, generated_by, tags) VALUES
(1, 1, 'quote_comparison', 'Smith_Family_Auto_Quotes_2026.pdf', '/documents/quotes/smith_auto_2026.pdf', 245760, 'application/pdf', 'ai', '["auto", "renewal", "comparison"]'),
(2, 2, 'policy_doc', 'ABC_Corp_Commercial_Policy.pdf', '/documents/policies/abc_corp_commercial.pdf', 1048576, 'application/pdf', 'system', '["commercial", "policy", "manufacturing"]'),
(1, NULL, 'presentation', 'Smith_Family_Insurance_Review.pptx', '/documents/presentations/smith_review.pptx', 2097152, 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'ai', '["presentation", "review", "cross-sell"]');

-- Cross-sell Opportunities
INSERT INTO txn.cross_sell_opportunities (client_id, current_product_category, recommended_product_category, opportunity_type, estimated_premium, confidence_score, status, reasoning, ai_generated) VALUES
(1, 'auto', 'home', 'gap_coverage', 1500.00, 0.85, 'identified', 'Auto policy holder with no home insurance detected. Property records show home ownership.', 1),
(4, 'home', 'umbrella', 'risk_increase', 285.00, 0.78, 'identified', 'Teen driver added to household. Recommend umbrella policy for increased liability protection.', 1),
(6, 'auto', 'home', 'gap_coverage', 1200.00, 0.82, 'identified', 'New auto customer, property records indicate home ownership. Bundle opportunity.', 1),
(2, 'commercial', 'cyber', 'risk_increase', 4500.00, 0.71, 'presented', 'Manufacturing business with no cyber coverage. Industry trend shows increased risk.', 1);
GO

PRINT 'Setup complete — all tables created and seed data inserted.';
