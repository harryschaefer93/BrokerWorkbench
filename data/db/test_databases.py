#!/usr/bin/env python3
"""
Test Database Connections and Sample Queries
Demonstrates how to query the created databases
"""

import sqlite3
import json
from datetime import datetime

class DatabaseTester:
    def __init__(self):
        self.master_db = "master_data.db"
        self.transactional_db = "transactional_data.db"
    
    def test_master_data_queries(self):
        """Test master data database queries"""
        print("🧪 Testing Master Data Database Queries...")
        
        conn = sqlite3.connect(self.master_db)
        cursor = conn.cursor()
        
        # Query 1: Carrier performance summary
        print("\n📊 Carrier Summary:")
        cursor.execute("""
            SELECT 
                carrier_name,
                api_status,
                rating,
                specialty_lines,
                market_share
            FROM carriers 
            ORDER BY market_share DESC
        """)
        
        for row in cursor.fetchall():
            print(f"  {row[0]:<15} | {row[1]:<10} | {row[2]:<4} | {row[4]:.1f}% market share")
        
        # Query 2: Client risk distribution
        print("\n🎯 Client Risk Distribution:")
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN risk_score < 30 THEN 'Low Risk'
                    WHEN risk_score < 70 THEN 'Medium Risk'
                    ELSE 'High Risk'
                END as risk_category,
                COUNT(*) as client_count,
                AVG(total_premium_ytd) as avg_premium,
                SUM(total_premium_ytd) as total_premium
            FROM clients
            GROUP BY 
                CASE 
                    WHEN risk_score < 30 THEN 'Low Risk'
                    WHEN risk_score < 70 THEN 'Medium Risk'
                    ELSE 'High Risk'
                END
            ORDER BY avg_premium DESC
        """)
        
        for row in cursor.fetchall():
            print(f"  {row[0]:<12} | {row[1]:>3} clients | ${row[2]:>8,.0f} avg | ${row[3]:>10,.0f} total")
        
        # Query 3: Market rate analysis
        print("\n💰 Market Rate Analysis by Category:")
        cursor.execute("""
            SELECT 
                mr.product_category,
                c.carrier_name,
                mr.risk_profile,
                mr.base_rate,
                mr.rate_factor,
                ROUND(mr.base_rate * mr.rate_factor, 2) as effective_rate
            FROM market_rates mr
            JOIN carriers c ON mr.carrier_id = c.carrier_id
            WHERE mr.product_category = 'auto'
            ORDER BY mr.risk_profile, effective_rate
            LIMIT 10
        """)
        
        print("  Category | Carrier        | Risk   | Base Rate | Factor | Effective")
        for row in cursor.fetchall():
            print(f"  {row[0]:<8} | {row[1]:<14} | {row[2]:<6} | ${row[3]:>8,.0f} | {row[4]:.3f}  | ${row[5]:>8,.0f}")
        
        conn.close()
    
    def test_transactional_queries(self):
        """Test transactional database queries"""
        print("\n\n🧪 Testing Transactional Database Queries...")
        
        conn = sqlite3.connect(self.transactional_db)
        cursor = conn.cursor()
        
        # Query 1: Portfolio summary
        print("\n📋 Active Portfolio Summary:")
        cursor.execute("""
            SELECT 
                product_category,
                COUNT(*) as policy_count,
                SUM(premium_amount) as total_premium,
                AVG(premium_amount) as avg_premium,
                COUNT(CASE WHEN policy_status = 'renewal_due' THEN 1 END) as renewals_due
            FROM policies
            GROUP BY product_category
            ORDER BY total_premium DESC
        """)
        
        print("  Category    | Policies | Total Premium | Avg Premium | Renewals Due")
        for row in cursor.fetchall():
            print(f"  {row[0]:<11} | {row[1]:>8} | ${row[2]:>11,.0f} | ${row[3]:>9,.0f} | {row[4]:>11}")
        
        # Query 2: Quote comparison for renewal (attach master DB for carrier names)
        conn.execute(f"ATTACH DATABASE '{self.master_db}' AS master")
        
        print("\n🔄 Smith Family Renewal Quotes:")
        cursor.execute("""
            SELECT 
                c.carrier_name,
                q.quoted_premium,
                q.competitive_position,
                q.savings_vs_current,
                q.quote_status,
                q.response_time_seconds
            FROM quotes q
            JOIN master.carriers c ON q.carrier_id = c.carrier_id
            WHERE q.client_id = 1
            ORDER BY q.quoted_premium
        """)
        
        print("  Carrier     | Quote    | Position | Savings | Status    | Response Time")
        for row in cursor.fetchall():
            response_time = f"{row[5]:.1f}s" if row[5] else "N/A"
            print(f"  {row[0]:<11} | ${row[1]:>7,.0f} | {row[2]:<8} | ${row[3]:>6,.0f} | {row[4]:<9} | {response_time:>12}")
        
        # Query 3: Priority tasks dashboard
        print("\n📈 Priority Tasks by Category:")
        cursor.execute("""
            SELECT 
                task_type,
                priority_level,
                COUNT(*) as task_count,
                SUM(potential_value) as total_value,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed
            FROM tasks
            GROUP BY task_type, priority_level
            ORDER BY 
                CASE priority_level 
                    WHEN 'high' THEN 1 
                    WHEN 'medium' THEN 2 
                    ELSE 3 
                END,
                total_value DESC
        """)
        
        print("  Type        | Priority | Count | Total Value | Completed")
        for row in cursor.fetchall():
            print(f"  {row[0]:<11} | {row[1]:<8} | {row[2]:>5} | ${row[3]:>9,.0f} | {row[4]:>9}")
        
        # Query 4: Cross-sell opportunities (attach master DB for client names)
        print("\n🎯 Cross-sell Opportunities:")
        cursor.execute("""
            SELECT 
                c.client_name,
                cs.current_product_category,
                cs.recommended_product_category,
                cs.estimated_premium,
                cs.confidence_score,
                cs.status
            FROM cross_sell_opportunities cs
            JOIN master.clients c ON cs.client_id = c.client_id
            WHERE cs.status IN ('identified', 'presented')
            ORDER BY cs.confidence_score DESC, cs.estimated_premium DESC
        """)
        
        print("  Client              | Current  | Recommended | Premium | Confidence | Status")
        for row in cursor.fetchall():
            print(f"  {row[0]:<19} | {row[1]:<8} | {row[2]:<11} | ${row[3]:>6,.0f} | {row[4]:>9.2f} | {row[5]}")
        
        # Query 5: AI interaction insights
        print("\n🤖 Recent AI Interaction Summary:")
        cursor.execute("""
            SELECT 
                interaction_type,
                COUNT(*) as interaction_count,
                AVG(confidence_score) as avg_confidence,
                AVG(feedback_rating) as avg_rating,
                AVG(processing_time_ms) as avg_processing_time
            FROM ai_interactions
            GROUP BY interaction_type
            ORDER BY interaction_count DESC
        """)
        
        print("  Type           | Count | Avg Confidence | Avg Rating | Avg Time (ms)")
        for row in cursor.fetchall():
            print(f"  {row[0]:<14} | {row[1]:>5} | {row[2]:>13.2f} | {row[3]:>9.1f} | {row[4]:>12.0f}")
        
        conn.close()
    
    def test_analytics_queries(self):
        """Test complex analytics queries"""
        print("\n\n📊 Testing Advanced Analytics Queries...")
        
        # Combined query across both databases (cross-database analytics)
        master_conn = sqlite3.connect(self.master_db)
        trans_conn = sqlite3.connect(self.transactional_db)
        
        # Attach transactional DB to master DB for cross-database queries
        master_conn.execute(f"ATTACH DATABASE '{self.transactional_db}' AS trans")
        
        cursor = master_conn.cursor()
        
        # Complex analytics query
        print("\n🔍 Client Performance Analytics:")
        cursor.execute("""
            SELECT 
                c.client_name,
                c.client_type,
                c.risk_score,
                COUNT(p.policy_id) as policy_count,
                SUM(p.premium_amount) as total_premium,
                COUNT(cl.claim_id) as claim_count,
                COALESCE(SUM(cl.settlement_amount), 0) as total_claims,
                COUNT(cs.opportunity_id) as cross_sell_opportunities,
                SUM(cs.estimated_premium) as cross_sell_potential
            FROM clients c
            LEFT JOIN trans.policies p ON c.client_id = p.client_id
            LEFT JOIN trans.claims cl ON p.policy_id = cl.policy_id
            LEFT JOIN trans.cross_sell_opportunities cs ON c.client_id = cs.client_id
            GROUP BY c.client_id, c.client_name, c.client_type, c.risk_score
            ORDER BY total_premium DESC
        """)
        
        print("  Client              | Type       | Risk | Policies | Premium   | Claims | Settlements | Cross-sell Opps")
        for row in cursor.fetchall():
            print(f"  {row[0]:<19} | {row[1]:<10} | {row[2]:>4} | {row[3]:>8} | ${row[4]:>8,.0f} | {row[5]:>6} | ${row[6]:>10,.0f} | {row[7]:>14}")
        
        master_conn.close()
    
    def generate_sample_api_responses(self):
        """Generate sample API response data for the web application"""
        print("\n\n🔌 Generating Sample API Responses...")
        
        conn = sqlite3.connect(self.transactional_db)
        cursor = conn.cursor()
        
        # Dashboard summary data
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN task_type = 'renewal' AND priority_level = 'high' THEN 1 END) as urgent_renewals,
                COUNT(CASE WHEN task_type = 'claim_review' AND priority_level = 'high' THEN 1 END) as urgent_claims,
                SUM(CASE WHEN policy_status = 'active' THEN premium_amount ELSE 0 END) as total_active_premium,
                COUNT(CASE WHEN policy_status = 'active' THEN 1 END) as active_policies
            FROM tasks 
            CROSS JOIN policies
        """)
        
        dashboard_data = cursor.fetchone()
        
        # Quote comparison data (attach master DB)
        conn.execute(f"ATTACH DATABASE '{self.master_db}' AS master")
        cursor.execute("""
            SELECT 
                c.carrier_name,
                c.carrier_code,
                q.quoted_premium,
                q.savings_vs_current,
                q.competitive_position,
                q.quote_status
            FROM quotes q
            JOIN master.carriers c ON q.carrier_id = c.carrier_id
            WHERE q.client_id = 1
            ORDER BY q.quoted_premium
        """)
        
        quotes_data = cursor.fetchall()
        
        # Sample API response structure
        api_response = {
            "dashboard": {
                "urgent_tasks": dashboard_data[0] + dashboard_data[1],
                "total_premium": float(dashboard_data[2]) if dashboard_data[2] else 0,
                "active_policies": dashboard_data[3],
                "timestamp": datetime.now().isoformat()
            },
            "smith_family_quotes": [
                {
                    "carrier": row[0],
                    "code": row[1],
                    "premium": float(row[2]),
                    "savings": float(row[3]) if row[3] else 0,
                    "position": row[4],
                    "status": row[5]
                } for row in quotes_data
            ],
            "carriers_status": [
                {"name": "State Farm", "status": "connected", "response_time": 2.1},
                {"name": "Allstate", "status": "connected", "response_time": 3.5},
                {"name": "Progressive", "status": "slow", "response_time": 8.2},
                {"name": "Geico", "status": "offline", "response_time": None}
            ]
        }
        
        # Save API response sample
        with open('/root/sample_api_response.json', 'w') as f:
            json.dump(api_response, f, indent=2)
        
        print("✅ Sample API responses saved to sample_api_response.json")
        
        conn.close()
    
    def run_all_tests(self):
        """Run all database tests"""
        print("🚀 Running Database Tests...")
        
        self.test_master_data_queries()
        self.test_transactional_queries()
        self.test_analytics_queries()
        self.generate_sample_api_responses()
        
        print("\n\n🎉 All database tests completed successfully!")
        print("\nThe databases are ready for integration with your Insurance Broker Workbench!")

if __name__ == "__main__":
    tester = DatabaseTester()
    tester.run_all_tests()