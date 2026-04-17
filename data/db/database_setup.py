#!/usr/bin/env python3
"""
Insurance Broker Workbench Database Setup
Creates two databases (SQLite) or two schemas in one database (Azure SQL):
1. Master Data - Reference/lookup data (carriers, clients, products, market rates)
2. Transactional Data - Operational data (policies, quotes, claims, tasks, etc.)

Usage:
  # SQLite (local development) — default
  python data/db/database_setup.py

  # Azure SQL (reads DATABASE_URL or AZURE_SQL_CONNECTION_STRING from env/.env)
  python data/db/database_setup.py --target azure-sql

  # Schema only (no seed data)
  python data/db/database_setup.py --target azure-sql --schema-only

  # Seed data only (tables must already exist)
  python data/db/database_setup.py --target azure-sql --seed-only
"""

import argparse
import sqlite3
import random
import datetime
from datetime import timedelta
import json
import os
import sys
from pathlib import Path

class InsuranceDatabaseSetup:
    def __init__(self, target="sqlite"):
        self.target = target  # "sqlite" or "azure-sql"
        if target == "sqlite":
            self.master_db = "master_data.db"
            self.transactional_db = "transactional_data.db"
        else:
            # Azure SQL: single database, two schemas (master_data, txn)
            self._conn = None  # lazy pyodbc connection

    # ─── Connection helpers ───────────────────────────────────────────

    def _get_azure_connection_string(self) -> str:
        """Resolve Azure SQL ODBC connection string from env."""
        # Load .env from project root
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).resolve().parents[2] / ".env"
            load_dotenv(env_path)
        except ImportError:
            pass

        url = os.getenv("DATABASE_URL") or os.getenv("AZURE_SQL_CONNECTION_STRING")
        if not url:
            raise ValueError(
                "Set DATABASE_URL or AZURE_SQL_CONNECTION_STRING environment variable "
                "to your Azure SQL connection string."
            )
        # SQLAlchemy format: mssql+pyodbc://server:port/db?driver=...&Authentication=...
        # Convert to raw ODBC connection string for pyodbc
        if url.startswith("mssql+pyodbc://"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url.replace("mssql+pyodbc://", "https://"))
            host = parsed.hostname
            port = parsed.port or 1433
            database = parsed.path.lstrip("/")
            params = parse_qs(parsed.query)
            driver = params.get("driver", ["ODBC Driver 18 for SQL Server"])[0]
            encrypt = params.get("Encrypt", ["yes"])[0]
            trust_cert = params.get("TrustServerCertificate", ["no"])[0]
            auth = params.get("Authentication", ["ActiveDirectoryDefault"])[0]
            return (
                f"Driver={{{driver}}};"
                f"Server=tcp:{host},{port};"
                f"Database={database};"
                f"Encrypt={encrypt};"
                f"TrustServerCertificate={trust_cert};"
                f"Authentication={auth};"
            )
        # Assume it's already an ODBC string
        return url

    def _get_azure_conn(self):
        """Get (or create) a pyodbc connection to Azure SQL."""
        if self._conn is None:
            import pyodbc
            import struct
            conn_str = self._get_azure_connection_string()

            # Strip Authentication= from the ODBC string (we use token auth instead)
            import re
            conn_str = re.sub(r'Authentication=[^;]*;?', '', conn_str)

            # Get AAD token via azure-identity (AzureCliCredential for local dev)
            from azure.identity import AzureCliCredential
            credential = AzureCliCredential()
            token = credential.get_token("https://database.windows.net/.default")
            token_bytes = token.token.encode("utf-16-le")
            token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

            SQL_COPT_SS_ACCESS_TOKEN = 1256
            self._conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
        return self._conn

    def _get_sqlite_conn(self, db_name: str):
        return sqlite3.connect(db_name)

    def _execute(self, cursor, sql: str, params=None):
        """Execute a single statement, handling target differences."""
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

    def _executemany(self, cursor, sql: str, data_list):
        if self.target == "sqlite":
            cursor.executemany(sql, data_list)
        else:
            # pyodbc executemany works the same way
            cursor.executemany(sql, data_list)

    # ─── Schema prefix helpers ────────────────────────────────────────

    def _mp(self, table: str) -> str:
        """Master-data prefixed table name."""
        return f"master_data.{table}" if self.target == "azure-sql" else table

    def _tp(self, table: str) -> str:
        """Transactional prefixed table name."""
        return f"txn.{table}" if self.target == "azure-sql" else table

    def _identity_col(self) -> str:
        """Primary-key auto-increment clause."""
        if self.target == "azure-sql":
            return "INT IDENTITY(1,1) PRIMARY KEY"
        return "INTEGER PRIMARY KEY"

    def _bool_type(self) -> str:
        return "BIT" if self.target == "azure-sql" else "BOOLEAN"

    def _bool_val(self, val: bool):
        """Boolean literal for parameterized inserts."""
        if self.target == "azure-sql":
            return 1 if val else 0
        return val
        
    def create_master_database(self):
        """Create master data database/schema with reference tables"""
        if self.target == "sqlite":
            conn = self._get_sqlite_conn(self.master_db)
        else:
            conn = self._get_azure_conn()
        cursor = conn.cursor()
        
        pk = self._identity_col()
        mp = self._mp

        # Carriers table
        cursor.execute(f"""
        CREATE TABLE {mp('carriers')} (
            carrier_id {pk},
            carrier_name VARCHAR(100) NOT NULL,
            carrier_code VARCHAR(10) UNIQUE NOT NULL,
            api_endpoint VARCHAR(255),
            api_status VARCHAR(20) DEFAULT 'active',
            rating VARCHAR(10),
            specialty_lines VARCHAR(MAX),
            market_share DECIMAL(5,2),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """) if self.target == "azure-sql" else cursor.execute("""
        CREATE TABLE carriers (
            carrier_id INTEGER PRIMARY KEY,
            carrier_name VARCHAR(100) NOT NULL,
            carrier_code VARCHAR(10) UNIQUE NOT NULL,
            api_endpoint VARCHAR(255),
            api_status VARCHAR(20) DEFAULT 'active',
            rating VARCHAR(10),
            specialty_lines TEXT,
            market_share DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Clients table (Master data)
        cursor.execute(f"""
        CREATE TABLE {mp('clients')} (
            client_id {pk},
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
        )
        """) if self.target == "azure-sql" else cursor.execute("""
        CREATE TABLE clients (
            client_id INTEGER PRIMARY KEY,
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
            risk_score INTEGER DEFAULT 50,
            customer_since DATE,
            total_premium_ytd DECIMAL(12,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Product Lines table
        cursor.execute(f"""
        CREATE TABLE {mp('product_lines')} (
            product_id {pk},
            product_name VARCHAR(100) NOT NULL,
            product_category VARCHAR(50) NOT NULL,
            base_premium_range VARCHAR(50),
            risk_factors VARCHAR(MAX),
            coverage_options VARCHAR(MAX),
            target_market VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """) if self.target == "azure-sql" else cursor.execute("""
        CREATE TABLE product_lines (
            product_id INTEGER PRIMARY KEY,
            product_name VARCHAR(100) NOT NULL,
            product_category VARCHAR(50) NOT NULL,
            base_premium_range VARCHAR(50),
            risk_factors TEXT,
            coverage_options TEXT,
            target_market VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Market Rates table
        fk_carrier = f"FOREIGN KEY (carrier_id) REFERENCES {mp('carriers')} (carrier_id)" if self.target == "azure-sql" else "FOREIGN KEY (carrier_id) REFERENCES carriers (carrier_id)"
        cursor.execute(f"""
        CREATE TABLE {mp('market_rates')} (
            rate_id {pk},
            carrier_id {'INT' if self.target == 'azure-sql' else 'INTEGER'},
            product_category VARCHAR(50),
            risk_profile VARCHAR(50),
            base_rate DECIMAL(10,2),
            rate_factor DECIMAL(5,3),
            effective_date DATE,
            expiration_date DATE,
            market_region VARCHAR(50),
            created_at {'DATETIME' if self.target == 'azure-sql' else 'TIMESTAMP'} DEFAULT CURRENT_TIMESTAMP,
            {fk_carrier}
        )
        """)
        
        conn.commit()
        if self.target == "sqlite":
            conn.close()
        print("✅ Master database/schema created successfully")
    
    def create_transactional_database(self):
        """Create transactional database/schema for operational data"""
        if self.target == "sqlite":
            conn = self._get_sqlite_conn(self.transactional_db)
        else:
            conn = self._get_azure_conn()
        cursor = conn.cursor()

        pk = self._identity_col()
        tp = self._tp
        bt = self._bool_type()
        ts = "DATETIME" if self.target == "azure-sql" else "TIMESTAMP"
        text_t = "VARCHAR(MAX)" if self.target == "azure-sql" else "TEXT"
        int_t = "INT" if self.target == "azure-sql" else "INTEGER"

        # Policies table
        cursor.execute(f"""
        CREATE TABLE {tp('policies')} (
            policy_id {pk},
            policy_number VARCHAR(50) UNIQUE NOT NULL,
            client_id {int_t} NOT NULL,
            carrier_id {int_t} NOT NULL,
            product_category VARCHAR(50) NOT NULL,
            policy_status VARCHAR(20) DEFAULT 'active',
            premium_amount DECIMAL(12,2),
            deductible DECIMAL(10,2),
            coverage_limit DECIMAL(15,2),
            effective_date DATE,
            expiration_date DATE,
            renewal_date DATE,
            auto_renew {bt} DEFAULT {'1' if self.target == 'azure-sql' else 'true'},
            commission_rate DECIMAL(5,2),
            commission_amount DECIMAL(10,2),
            last_review_date DATE,
            notes {text_t},
            created_at {ts} DEFAULT CURRENT_TIMESTAMP,
            updated_at {ts} DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Quotes table
        cursor.execute(f"""
        CREATE TABLE {tp('quotes')} (
            quote_id {pk},
            client_id {int_t} NOT NULL,
            carrier_id {int_t} NOT NULL,
            product_category VARCHAR(50),
            quote_number VARCHAR(50),
            quoted_premium DECIMAL(12,2),
            coverage_details {text_t},
            quote_status VARCHAR(20) DEFAULT 'pending',
            valid_until DATE,
            competitive_position VARCHAR(20),
            savings_vs_current DECIMAL(10,2),
            quote_source VARCHAR(50),
            response_time_seconds {int_t},
            created_at {ts} DEFAULT CURRENT_TIMESTAMP,
            presented_at {ts},
            decision_at {ts}
        )
        """)

        # Tasks/Priorities table
        fk_policy_tasks = f"FOREIGN KEY (policy_id) REFERENCES {tp('policies')} (policy_id)" if self.target == "azure-sql" else ""
        cursor.execute(f"""
        CREATE TABLE {tp('tasks')} (
            task_id {pk},
            client_id {int_t},
            policy_id {int_t},
            task_type VARCHAR(50) NOT NULL,
            priority_level VARCHAR(10) NOT NULL,
            task_title VARCHAR(200) NOT NULL,
            task_description {text_t},
            due_date DATE,
            status VARCHAR(20) DEFAULT 'pending',
            assigned_to VARCHAR(100),
            potential_value DECIMAL(12,2),
            completion_notes {text_t},
            created_at {ts} DEFAULT CURRENT_TIMESTAMP,
            completed_at {ts}
            {(',' + fk_policy_tasks) if fk_policy_tasks else ''}
        )
        """)

        # Claims table
        fk_policy_claims = f"FOREIGN KEY (policy_id) REFERENCES {tp('policies')} (policy_id)"
        cursor.execute(f"""
        CREATE TABLE {tp('claims')} (
            claim_id {pk},
            policy_id {int_t} NOT NULL,
            claim_number VARCHAR(50) UNIQUE NOT NULL,
            claim_type VARCHAR(50),
            claim_amount DECIMAL(12,2),
            claim_status VARCHAR(30) DEFAULT 'reported',
            date_of_loss DATE,
            reported_date DATE,
            description {text_t},
            adjuster_name VARCHAR(100),
            settlement_amount DECIMAL(12,2),
            impact_on_renewal VARCHAR(20),
            created_at {ts} DEFAULT CURRENT_TIMESTAMP,
            updated_at {ts} DEFAULT CURRENT_TIMESTAMP,
            {fk_policy_claims}
        )
        """)

        # AI Interactions table
        cursor.execute(f"""
        CREATE TABLE {tp('ai_interactions')} (
            interaction_id {pk},
            user_id VARCHAR(100),
            session_id VARCHAR(100),
            interaction_type VARCHAR(50),
            user_query {text_t},
            ai_response {text_t},
            context_data {text_t},
            confidence_score DECIMAL(3,2),
            feedback_rating {int_t},
            processing_time_ms {int_t},
            created_at {ts} DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Documents table
        cursor.execute(f"""
        CREATE TABLE {tp('documents')} (
            document_id {pk},
            client_id {int_t},
            policy_id {int_t},
            document_type VARCHAR(50),
            document_name VARCHAR(255),
            file_path VARCHAR(500),
            file_size_bytes {int_t},
            mime_type VARCHAR(100),
            generated_by VARCHAR(50),
            tags {text_t},
            last_accessed {ts},
            created_at {ts} DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Cross-sell Opportunities table
        cursor.execute(f"""
        CREATE TABLE {tp('cross_sell_opportunities')} (
            opportunity_id {pk},
            client_id {int_t} NOT NULL,
            current_product_category VARCHAR(50),
            recommended_product_category VARCHAR(50),
            opportunity_type VARCHAR(50),
            estimated_premium DECIMAL(10,2),
            confidence_score DECIMAL(3,2),
            status VARCHAR(20) DEFAULT 'identified',
            reasoning {text_t},
            ai_generated {bt} DEFAULT {'0' if self.target == 'azure-sql' else 'false'},
            created_at {ts} DEFAULT CURRENT_TIMESTAMP,
            presented_at {ts},
            decision_at {ts}
        )
        """)

        conn.commit()
        if self.target == "sqlite":
            conn.close()
        print("✅ Transactional database/schema created successfully")
    
    def populate_master_data(self):
        """Populate master database with sample data"""
        if self.target == "sqlite":
            conn = self._get_sqlite_conn(self.master_db)
        else:
            conn = self._get_azure_conn()
        cursor = conn.cursor()

        mp = self._mp
        ph = "?" if self.target == "sqlite" else "?"  # pyodbc uses ? too
        
        # Sample carriers
        carriers_data = [
            ('State Farm', 'SF', 'https://api.statefarm.com/v1', 'connected', 'A+', 'Auto,Home,Life', 18.5),
            ('Allstate', 'AS', 'https://api.allstate.com/quotes', 'connected', 'A+', 'Auto,Home,Commercial', 9.2),
            ('Progressive', 'PG', 'https://api.progressive.com/rating', 'slow', 'A', 'Auto,Commercial', 12.1),
            ('Geico', 'GE', 'https://geico-partner.com/api', 'offline', 'A++', 'Auto,Umbrella', 14.8),
            ('Liberty Mutual', 'LM', 'https://api.libertymutual.com', 'connected', 'A', 'Commercial,Auto', 6.3),
            ('Travelers', 'TR', 'https://travelers-api.com/v2', 'connected', 'A++', 'Commercial,Home', 4.1),
            ('Nationwide', 'NW', 'https://api.nationwide.com', 'connected', 'A+', 'Auto,Home,Commercial', 3.8),
            ('USAA', 'US', 'https://usaa-partners.com/api', 'connected', 'A++', 'Auto,Home,Life', 2.9),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {mp('carriers')} (carrier_name, carrier_code, api_endpoint, api_status, rating, specialty_lines, market_share)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, carriers_data)
        else:
            cursor.executemany("""
            INSERT INTO carriers (carrier_name, carrier_code, api_endpoint, api_status, rating, specialty_lines, market_share)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, carriers_data)
        
        # Sample clients
        clients_data = [
            ('Smith Family', 'individual', None, 'John Smith', 'john.smith@email.com', '555-0101', '123 Main St', '', 'Springfield', 'IL', '62701', 25, '2019-03-15', 2400.00),
            ('ABC Corporation', 'business', 'Manufacturing', 'Sarah Johnson', 'sarah@abccorp.com', '555-0202', '456 Business Ave', 'Suite 200', 'Chicago', 'IL', '60601', 75, '2020-01-10', 15600.00),
            ('Davis Enterprise', 'business', 'Technology', 'Mike Davis', 'mike@davisenterprise.com', '555-0303', '789 Tech Blvd', '', 'Naperville', 'IL', '60540', 45, '2021-06-20', 8900.00),
            ('Johnson Family', 'individual', None, 'Emily Johnson', 'emily.johnson@email.com', '555-0404', '321 Oak Street', '', 'Peoria', 'IL', '61601', 30, '2018-09-12', 3200.00),
            ('Williams Auto Group', 'business', 'Automotive', 'Robert Williams', 'rob@williamsauto.com', '555-0505', '654 Commerce St', '', 'Rockford', 'IL', '61101', 60, '2019-11-08', 22400.00),
            ('Anderson Family', 'individual', None, 'Lisa Anderson', 'lisa.anderson@email.com', '555-0606', '987 Pine Ave', '', 'Champaign', 'IL', '61820', 20, '2022-02-14', 1800.00),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {mp('clients')} (client_name, client_type, business_industry, primary_contact_name, email, phone, 
                           address_line1, address_line2, city, state, zip_code, risk_score, customer_since, total_premium_ytd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, clients_data)
        else:
            cursor.executemany("""
            INSERT INTO clients (client_name, client_type, business_industry, primary_contact_name, email, phone, 
                           address_line1, address_line2, city, state, zip_code, risk_score, customer_since, total_premium_ytd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, clients_data)
        
        # Sample product lines
        products_data = [
            ('Personal Auto Insurance', 'auto', '$1,200-$4,000', '["age", "driving_record", "vehicle_type", "location"]', 
             '["liability", "collision", "comprehensive", "uninsured_motorist"]', 'Individual drivers and families'),
            ('Homeowners Insurance', 'home', '$800-$3,500', '["property_value", "location", "age_of_home", "security_features"]',
             '["dwelling", "personal_property", "liability", "additional_living_expenses"]', 'Homeowners'),
            ('Commercial Auto', 'commercial', '$2,500-$25,000', '["fleet_size", "driver_profiles", "business_use", "cargo_type"]',
             '["liability", "physical_damage", "cargo", "hired_auto"]', 'Business fleets'),
            ('General Liability', 'commercial', '$500-$15,000', '["business_type", "revenue", "employee_count", "location"]',
             '["bodily_injury", "property_damage", "personal_injury", "products_liability"]', 'All businesses'),
            ('Umbrella Policy', 'umbrella', '$200-$800', '["underlying_limits", "assets", "risk_exposure"]',
             '["excess_liability", "worldwide_coverage"]', 'High-net-worth individuals and businesses'),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {mp('product_lines')} (product_name, product_category, base_premium_range, risk_factors, coverage_options, target_market)
            VALUES (?, ?, ?, ?, ?, ?)
            """, products_data)
        else:
            cursor.executemany("""
            INSERT INTO product_lines (product_name, product_category, base_premium_range, risk_factors, coverage_options, target_market)
            VALUES (?, ?, ?, ?, ?, ?)
            """, products_data)
        
        # Sample market rates
        market_rates_data = []
        carriers = [1, 2, 3, 4, 5, 6, 7, 8]  # carrier_ids
        categories = ['auto', 'home', 'commercial', 'umbrella']
        risk_profiles = ['low', 'medium', 'high']
        
        for carrier in carriers:
            for category in categories:
                for risk in risk_profiles:
                    base_rate = random.uniform(800, 3000)
                    if risk == 'low':
                        factor = random.uniform(0.8, 1.0)
                    elif risk == 'medium':
                        factor = random.uniform(1.0, 1.3)
                    else:  # high risk
                        factor = random.uniform(1.3, 1.8)
                    
                    market_rates_data.append((
                        carrier, category, risk, base_rate, factor,
                        '2025-01-01', '2025-12-31', 'Illinois'
                    ))
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {mp('market_rates')} (carrier_id, product_category, risk_profile, base_rate, rate_factor, 
                                effective_date, expiration_date, market_region)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, market_rates_data)
        else:
            cursor.executemany("""
            INSERT INTO market_rates (carrier_id, product_category, risk_profile, base_rate, rate_factor, 
                                effective_date, expiration_date, market_region)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, market_rates_data)
        
        conn.commit()
        if self.target == "sqlite":
            conn.close()
        print("✅ Master data populated successfully")
    
    def populate_transactional_data(self):
        """Populate transactional database with sample operational data"""
        if self.target == "sqlite":
            conn = self._get_sqlite_conn(self.transactional_db)
        else:
            conn = self._get_azure_conn()
        cursor = conn.cursor()

        tp = self._tp
        bv = self._bool_val
        
        # Sample policies
        policies_data = [
            ('POL12344', 1, 1, 'auto', 'renewal_due', 2400.00, 500.00, 300000.00, '2025-02-01', '2026-02-01', '2026-01-15', bv(True), 12.5, 300.00, '2025-12-01', 'Family auto policy, good driving record'),
            ('POL98765', 2, 2, 'commercial', 'active', 15600.00, 2500.00, 1000000.00, '2025-08-15', '2026-08-15', '2026-07-15', bv(True), 15.0, 2340.00, '2025-10-01', 'Manufacturing business, multiple vehicles'),
            ('POL54321', 3, 3, 'auto', 'active', 1800.00, 750.00, 250000.00, '2025-06-01', '2026-06-01', '2026-05-15', bv(True), 12.0, 216.00, '2025-11-01', 'New client, good credit score'),
            ('POL67890', 4, 1, 'home', 'active', 3200.00, 1000.00, 500000.00, '2025-03-01', '2026-03-01', '2026-02-15', bv(True), 14.0, 448.00, '2025-09-01', 'Single family home, updated systems'),
            ('POL11111', 5, 2, 'commercial', 'active', 22400.00, 5000.00, 2000000.00, '2025-11-01', '2026-11-01', '2026-10-15', bv(True), 16.0, 3584.00, '2025-12-15', 'Auto dealership, multiple locations'),
            ('POL22222', 6, 4, 'auto', 'active', 1800.00, 500.00, 300000.00, '2025-12-01', '2026-12-01', '2026-11-15', bv(True), 11.5, 207.00, '2026-01-01', 'Recent customer, clean record'),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('policies')} (policy_number, client_id, carrier_id, product_category, policy_status, 
                            premium_amount, deductible, coverage_limit, effective_date, expiration_date, 
                            renewal_date, auto_renew, commission_rate, commission_amount, last_review_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, policies_data)
        else:
            cursor.executemany("""
            INSERT INTO policies (policy_number, client_id, carrier_id, product_category, policy_status, 
                            premium_amount, deductible, coverage_limit, effective_date, expiration_date, 
                            renewal_date, auto_renew, commission_rate, commission_amount, last_review_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, policies_data)
        
        # Sample quotes (for Smith Family renewal)
        quotes_data = [
            (1, 1, 'auto', 'QT-SF-001', 2280.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'presented', '2026-02-15', 'current', 120.00, 'api', 2.1, '2026-01-25 10:30:00'),
            (1, 2, 'auto', 'QT-AS-001', 2150.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'presented', '2026-02-15', 'best', 250.00, 'api', 3.5, '2026-01-25 10:32:00'),
            (1, 3, 'auto', 'QT-PG-001', 2090.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'presented', '2026-02-15', 'best', 310.00, 'api', 8.2, '2026-01-25 10:35:00'),
            (1, 4, 'auto', 'QT-GE-001', 2050.00, '{"liability": "300/100/100", "collision": "500", "comprehensive": "500"}', 'pending', '2026-02-15', 'best', 350.00, 'manual', None, '2026-01-25 11:00:00'),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('quotes')} (client_id, carrier_id, product_category, quote_number, quoted_premium, 
                          coverage_details, quote_status, valid_until, competitive_position, savings_vs_current, 
                          quote_source, response_time_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, quotes_data)
        else:
            cursor.executemany("""
            INSERT INTO quotes (client_id, carrier_id, product_category, quote_number, quoted_premium, 
                          coverage_details, quote_status, valid_until, competitive_position, savings_vs_current, 
                          quote_source, response_time_seconds, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, quotes_data)
        
        # Sample tasks
        tasks_data = [
            (1, 1, 'renewal', 'high', 'Smith Family - Auto Renewal', 'Review renewal options and present quotes', '2026-02-03', 'in_progress', 'John Broker', 2400.00, None),
            (2, None, 'follow_up', 'high', 'ABC Corp - Claim Review', 'Review $45,000 claim and assess impact', '2026-01-31', 'pending', 'John Broker', 45000.00, None),
            (3, None, 'follow_up', 'medium', 'Follow up: Davis Enterprise', 'Quote was requested 2 days ago, follow up needed', '2026-02-01', 'pending', 'John Broker', 8900.00, None),
            (4, 4, 'cross_sell', 'low', 'Johnson Annual Review', 'Annual policy review scheduled', '2026-02-10', 'pending', 'John Broker', 3200.00, None),
            (1, None, 'cross_sell', 'medium', 'Smith Family - Home Insurance', 'Auto policy holder with no home insurance', '2026-02-05', 'identified', 'John Broker', 1500.00, None),
            (4, None, 'cross_sell', 'medium', 'Johnson Family - Umbrella Policy', 'Teen driver added, recommend umbrella coverage', '2026-02-07', 'identified', 'John Broker', 285.00, None),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('tasks')} (client_id, policy_id, task_type, priority_level, task_title, task_description, 
                         due_date, status, assigned_to, potential_value, completion_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tasks_data)
        else:
            cursor.executemany("""
            INSERT INTO tasks (client_id, policy_id, task_type, priority_level, task_title, task_description, 
                         due_date, status, assigned_to, potential_value, completion_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tasks_data)
        
        # Sample claims
        claims_data = [
            (2, 'CLM-ABC-001', 'property_damage', 45000.00, 'investigating', '2025-12-15', '2025-12-16', 'Equipment damage due to electrical surge', 'Jane Adjuster', None, 'minor'),
            (1, 'CLM-SF-002', 'auto_accident', 8500.00, 'settled', '2025-10-10', '2025-10-11', 'Rear-end collision, minor injuries', 'Bob Claims', 7200.00, 'none'),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('claims')} (policy_id, claim_number, claim_type, claim_amount, claim_status, 
                          date_of_loss, reported_date, description, adjuster_name, settlement_amount, impact_on_renewal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, claims_data)
        else:
            cursor.executemany("""
            INSERT INTO claims (policy_id, claim_number, claim_type, claim_amount, claim_status, 
                          date_of_loss, reported_date, description, adjuster_name, settlement_amount, impact_on_renewal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, claims_data)
        
        # Sample AI interactions
        ai_interactions_data = [
            ('john.broker', 'sess_001', 'insight', 'Show me high-risk clients', 'Based on your portfolio analysis, I found 3 clients requiring attention: ABC Corp (active claim), Williams Auto Group (high fleet exposure), and Smith Family (teen driver added). Would you like detailed recommendations for each?', '{"client_ids": [2, 5, 1], "risk_factors": ["active_claims", "fleet_size", "young_drivers"]}', 0.89, 5, 1250),
            ('john.broker', 'sess_002', 'recommendation', 'Best cross-sell opportunities?', 'Top opportunities: 1) Smith Family - Home insurance ($1,200-1,800 est.), 2) Johnson Family - Umbrella policy ($285 est.), 3) Anderson Family - Auto + Home bundle (15% savings). These represent $45K potential new premium.', '{"opportunities": [{"client_id": 1, "product": "home"}, {"client_id": 4, "product": "umbrella"}]}', 0.92, 4, 890),
            ('john.broker', 'sess_003', 'summary', 'Summarize Smith Family renewal', 'Smith Family auto renewal summary: Current premium $2,400 with State Farm. Best quotes: Geico $2,050 (save $350), Progressive $2,090 (save $310), Allstate $2,150 (save $250). Recommend presenting Geico quote with umbrella policy option ($285). Total opportunity: $635 savings + new premium.', '{"client_id": 1, "policy_id": 1, "quotes": [2050, 2090, 2150], "cross_sell": "umbrella"}', 0.95, 5, 780),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('ai_interactions')} (user_id, session_id, interaction_type, user_query, ai_response, 
                                   context_data, confidence_score, feedback_rating, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ai_interactions_data)
        else:
            cursor.executemany("""
            INSERT INTO ai_interactions (user_id, session_id, interaction_type, user_query, ai_response, 
                                   context_data, confidence_score, feedback_rating, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ai_interactions_data)
        
        # Sample cross-sell opportunities
        cross_sell_data = [
            (1, 'auto', 'home', 'gap_coverage', 1500.00, 0.85, 'identified', 'Auto policy holder with no home insurance detected. Property records show home ownership.', bv(True)),
            (4, 'home', 'umbrella', 'risk_increase', 285.00, 0.78, 'identified', 'Teen driver added to household. Recommend umbrella policy for increased liability protection.', bv(True)),
            (6, 'auto', 'home', 'gap_coverage', 1200.00, 0.82, 'identified', 'New auto customer, property records indicate home ownership. Bundle opportunity.', bv(True)),
            (2, 'commercial', 'cyber', 'risk_increase', 4500.00, 0.71, 'presented', 'Manufacturing business with no cyber coverage. Industry trend shows increased risk.', bv(True)),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('cross_sell_opportunities')} (client_id, current_product_category, recommended_product_category, 
                                            opportunity_type, estimated_premium, confidence_score, status, reasoning, ai_generated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, cross_sell_data)
        else:
            cursor.executemany("""
            INSERT INTO cross_sell_opportunities (client_id, current_product_category, recommended_product_category, 
                                            opportunity_type, estimated_premium, confidence_score, status, reasoning, ai_generated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, cross_sell_data)
        
        # Sample documents
        documents_data = [
            (1, 1, 'quote_comparison', 'Smith_Family_Auto_Quotes_2026.pdf', '/documents/quotes/smith_auto_2026.pdf', 245760, 'application/pdf', 'ai', '["auto", "renewal", "comparison"]'),
            (2, 2, 'policy_doc', 'ABC_Corp_Commercial_Policy.pdf', '/documents/policies/abc_corp_commercial.pdf', 1048576, 'application/pdf', 'system', '["commercial", "policy", "manufacturing"]'),
            (1, None, 'presentation', 'Smith_Family_Insurance_Review.pptx', '/documents/presentations/smith_review.pptx', 2097152, 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'ai', '["presentation", "review", "cross-sell"]'),
        ]
        
        if self.target == "azure-sql":
            cursor.executemany(f"""
            INSERT INTO {tp('documents')} (client_id, policy_id, document_type, document_name, file_path, 
                             file_size_bytes, mime_type, generated_by, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, documents_data)
        else:
            cursor.executemany("""
            INSERT INTO documents (client_id, policy_id, document_type, document_name, file_path, 
                             file_size_bytes, mime_type, generated_by, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, documents_data)
        
        conn.commit()
        if self.target == "sqlite":
            conn.close()
        print("✅ Transactional data populated successfully")
    

    

    
    def run_setup(self, schema_only=False, seed_only=False):
        """Run complete database setup"""
        label = "Azure SQL" if self.target == "azure-sql" else "SQLite"
        print(f"🚀 Starting Insurance Broker Workbench Database Setup ({label})...")

        if not seed_only:
            self.create_master_database()
            self.create_transactional_database()

        if not schema_only:
            self.populate_master_data()
            self.populate_transactional_data()

        # Close Azure SQL connection if open
        if self.target == "azure-sql" and self._conn:
            self._conn.close()
            self._conn = None

        print(f"\n🎉 Database setup completed successfully! (target: {label})")

        if self.target == "sqlite":
            print("\nCreated files:")
            print("📁 master_data.db - Master/reference data")
            print("📁 transactional_data.db - Operational data")
        else:
            print("\nCreated schemas:")
            print("📂 master_data.* — carriers, clients, product_lines, market_rates")
            print("📂 txn.* — policies, quotes, tasks, claims, ai_interactions, documents, cross_sell_opportunities")
        
        print("\nNext steps:")
        print("1. Review the sample data")
        print("2. Run the backend: uvicorn main:app --reload")


def main():
    parser = argparse.ArgumentParser(description="Insurance Broker Workbench Database Setup")
    parser.add_argument(
        "--target",
        choices=["sqlite", "azure-sql"],
        default="sqlite",
        help="Database target: 'sqlite' (default, local dev) or 'azure-sql' (reads DATABASE_URL / AZURE_SQL_CONNECTION_STRING from env)",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Create tables/schemas only, do not seed data",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Seed data only (tables must already exist)",
    )
    args = parser.parse_args()

    if args.schema_only and args.seed_only:
        print("❌ Cannot use both --schema-only and --seed-only")
        sys.exit(1)

    setup = InsuranceDatabaseSetup(target=args.target)
    setup.run_setup(schema_only=args.schema_only, seed_only=args.seed_only)


if __name__ == "__main__":
    main()