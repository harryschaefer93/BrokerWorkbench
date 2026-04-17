// API Types - matching backend schemas

export interface Client {
  client_id: string;
  first_name: string;
  last_name: string;
  business_name?: string;
  email: string;
  phone?: string;
  risk_profile?: string;
  created_at?: string;
}

export interface Carrier {
  carrier_id: string;
  name: string;
  rating?: string;
  specialties?: string[];
  api_status?: string;
  supported_policy_types?: string[];
}

export interface Policy {
  policy_id: string;
  client_id: string;
  carrier_id: string;
  policy_type: string;
  premium: number;
  coverage_amount: number;
  effective_date: string;
  expiration_date: string;
  status: string;
  client_name?: string;
  carrier_name?: string;
}

export interface RenewalInfo {
  policy_id: string;
  client_name: string;
  policy_type: string;
  carrier_name: string;
  premium: number;
  expiration_date: string;
  days_until_expiry: number;
  urgency: 'critical' | 'high' | 'medium' | 'low';
  priority_score: number;
}

export interface RenewalDashboard {
  critical: RenewalInfo[];
  high: RenewalInfo[];
  medium: RenewalInfo[];
  low: RenewalInfo[];
  total_premium_at_risk: number;
  total_policies: number;
}

export interface CarrierQuote {
  carrier_name: string;
  carrier_id: string;
  premium: number;
  coverage_amount: number;
  deductible: number;
  features?: string[];
  savings?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  agentType?: 'claims' | 'crosssell' | 'quote';
  suggestions?: string[];
}

export interface CrossSellOpportunity {
  client_id: string;
  client_name: string;
  current_coverage: string;
  recommended: string;
  estimated_premium: string;
  reason: string;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  client_name?: string;
  priority: 'high' | 'medium' | 'low';
  due_date?: string;
  premium?: number;
}

export interface DashboardMetrics {
  totalPremiumAtRisk: number;
  policiesInRenewal: number;
  activeCarriers: number;
  totalClients: number;
}
