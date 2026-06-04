import { useState, useEffect, useCallback, useMemo } from "react";
import type {
  Policy,
  Client,
  Carrier,
  RenewalDashboard,
  ChatMessage,
  DashboardMetrics,
  ToolCall,
} from "@/types";

const API_BASE = "/api";
const CONV_ID_KEY = "bw-conv-id";

function getOrCreateConversationId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(CONV_ID_KEY);
    if (existing) return existing;
    const fresh =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(CONV_ID_KEY, fresh);
    return fresh;
  } catch {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

// Generic fetch hook (with optional response adapter)
function useFetch<TRaw, TOut = TRaw>(
  url: string,
  initialData: TOut,
  adapt?: (raw: TRaw) => TOut,
) {
  const [data, setData] = useState<TOut>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const raw = (await response.json()) as TRaw;
      setData(adapt ? adapt(raw) : (raw as unknown as TOut));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    } finally {
      setLoading(false);
    }
  }, [url, adapt]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

// ---------------------------------------------------------------------------
// v2 → FE shape adapters. v2 routers are the SQL-backed source of truth
// (see backend/routers/*_v2.py). Field-name remapping lives here so backend
// Pydantic stays truthful to the DB schema.
// ---------------------------------------------------------------------------

type V2Policy = {
  policy_id: number;
  policy_number: string;
  client_id: number;
  carrier_id: number;
  product_category: string;
  policy_status: string;
  premium_amount?: number | null;
  coverage_limit?: number | null;
  effective_date?: string | null;
  expiration_date?: string | null;
};

type V2Client = {
  client_id: number;
  client_name: string;
  client_type: string;
  business_industry?: string | null;
  email?: string | null;
  phone?: string | null;
  risk_score?: number | null;
};

type V2Carrier = {
  carrier_id: number;
  carrier_name: string;
  carrier_code: string;
  rating?: string | null;
  api_status?: string | null;
  specialty_lines?: string | null;
};

type V2RenewalItem = {
  policy_id: number;
  policy_number: string;
  client_id: number;
  client_name?: string | null;
  carrier_id: number;
  carrier_name?: string | null;
  product_category: string;
  premium_amount?: number | null;
  expiration_date: string;
  days_until_expiration: number;
  urgency: "critical" | "high" | "medium" | "low";
  priority_score: number;
};

type V2RenewalDashboard = {
  summary: {
    total_renewals: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    total_premium_at_risk: number;
  };
  by_timeframe: Record<string, number>;
  top_priority: V2RenewalItem[];
};

const adaptPolicy = (p: V2Policy): Policy => ({
  policy_id: String(p.policy_id),
  client_id: String(p.client_id),
  carrier_id: String(p.carrier_id),
  policy_type: p.product_category,
  premium: p.premium_amount ?? 0,
  coverage_amount: p.coverage_limit ?? 0,
  effective_date: p.effective_date ?? "",
  expiration_date: p.expiration_date ?? "",
  status: p.policy_status,
});

const adaptClient = (c: V2Client): Client => ({
  client_id: String(c.client_id),
  first_name: c.client_name.split(" ")[0] ?? c.client_name,
  last_name: c.client_name.split(" ").slice(1).join(" "),
  business_name: c.business_industry ?? undefined,
  email: c.email ?? "",
  phone: c.phone ?? undefined,
  risk_profile: c.risk_score != null ? String(c.risk_score) : undefined,
});

const adaptCarrier = (c: V2Carrier): Carrier => ({
  carrier_id: String(c.carrier_id),
  name: c.carrier_name,
  rating: c.rating ?? undefined,
  api_status: c.api_status ?? undefined,
  specialties: c.specialty_lines
    ? c.specialty_lines.split(",").map((s) => s.trim()).filter(Boolean)
    : undefined,
  supported_policy_types: c.specialty_lines
    ? c.specialty_lines.split(",").map((s) => s.trim()).filter(Boolean)
    : undefined,
});

const adaptRenewalItem = (r: V2RenewalItem) => ({
  policy_id: String(r.policy_id),
  client_name: r.client_name ?? "",
  policy_type: r.product_category,
  carrier_name: r.carrier_name ?? "",
  premium: r.premium_amount ?? 0,
  expiration_date: r.expiration_date,
  days_until_expiry: r.days_until_expiration,
  urgency: r.urgency,
  priority_score: r.priority_score,
});

const adaptRenewalDashboard = (d: V2RenewalDashboard): RenewalDashboard => {
  // v2 returns top_priority (top 5 by score) — bucket them by urgency so the
  // existing FE shape ({critical, high, medium, low}) still works.
  const buckets: Record<"critical" | "high" | "medium" | "low", ReturnType<typeof adaptRenewalItem>[]> = {
    critical: [],
    high: [],
    medium: [],
    low: [],
  };
  for (const item of d.top_priority ?? []) {
    const adapted = adaptRenewalItem(item);
    buckets[item.urgency]?.push(adapted);
  }
  return {
    critical: buckets.critical,
    high: buckets.high,
    medium: buckets.medium,
    low: buckets.low,
    total_premium_at_risk: d.summary.total_premium_at_risk,
    total_policies: d.summary.total_renewals,
  };
};

// Policies (v2-backed)
export function usePolicies() {
  return useFetch<V2Policy[], Policy[]>(
    `${API_BASE}/v2/policies/?limit=500`,
    [],
    (raw) => raw.map(adaptPolicy),
  );
}

export function usePolicy(policyId: string) {
  return useFetch<V2Policy | null, Policy | null>(
    `${API_BASE}/v2/policies/${policyId}`,
    null,
    (raw) => (raw ? adaptPolicy(raw) : null),
  );
}

// Clients (v2-backed)
export function useClients() {
  return useFetch<V2Client[], Client[]>(
    `${API_BASE}/v2/clients/?limit=500`,
    [],
    (raw) => raw.map(adaptClient),
  );
}

export function useClient(clientId: string) {
  return useFetch<V2Client | null, Client | null>(
    `${API_BASE}/v2/clients/${clientId}`,
    null,
    (raw) => (raw ? adaptClient(raw) : null),
  );
}

// Carriers (v2-backed)
export function useCarriers() {
  return useFetch<V2Carrier[], Carrier[]>(
    `${API_BASE}/v2/carriers/`,
    [],
    (raw) => raw.map(adaptCarrier),
  );
}

// Renewals (v2-backed)
export function useRenewalDashboard() {
  return useFetch<V2RenewalDashboard | null, RenewalDashboard | null>(
    `${API_BASE}/v2/renewals/dashboard`,
    null,
    (raw) => (raw ? adaptRenewalDashboard(raw) : null),
  );
}

// Dashboard Metrics (aggregated, v2-backed)
export function useDashboardMetrics() {
  const [metrics, setMetrics] = useState<DashboardMetrics>({
    totalPremiumAtRisk: 0,
    policiesInRenewal: 0,
    activeCarriers: 0,
    totalClients: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchMetrics() {
      try {
        const [renewalsRes, carriersRes, clientsRes] = await Promise.all([
          fetch(`${API_BASE}/v2/renewals/dashboard`),
          fetch(`${API_BASE}/v2/carriers/`),
          fetch(`${API_BASE}/v2/clients/?limit=500`),
        ]);

        const renewals = renewalsRes.ok
          ? ((await renewalsRes.json()) as V2RenewalDashboard)
          : null;
        const carriers = carriersRes.ok
          ? ((await carriersRes.json()) as V2Carrier[])
          : [];
        const clients = clientsRes.ok
          ? ((await clientsRes.json()) as V2Client[])
          : [];

        setMetrics({
          totalPremiumAtRisk: renewals?.summary?.total_premium_at_risk ?? 0,
          policiesInRenewal: renewals?.summary?.total_renewals ?? 0,
          activeCarriers: carriers.length,
          totalClients: clients.length,
        });
      } catch (err) {
        console.error("Failed to fetch metrics:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchMetrics();
  }, []);

  return { metrics, loading };
}

// AI Chat
export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const conversationId = useMemo(() => getOrCreateConversationId(), []);

  const sendMessage = useCallback(
    async (
      content: string,
      agentType: "claims" | "crosssell" | "quote" | "triage" = "triage",
      history?: { role: "user" | "assistant"; content: string }[],
    ) => {
      const userMessage: ChatMessage = {
        id: Date.now().toString(),
        role: "user",
        content,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setIsStreaming(false);
      setStatusMessage(null);

      // Add a placeholder assistant message that we will update in place
      // Don't set agentType yet — triage will resolve it via a 'routing' event
      const assistantId = (Date.now() + 1).toString();
      const placeholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, placeholder]);

      try {
        const endpoint = `${API_BASE}/agent/chat/handoff/stream`;
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (conversationId) {
          headers["X-Conversation-Id"] = conversationId;
        }
        const response = await fetch(endpoint, {
          method: "POST",
          headers,
          body: JSON.stringify({ message: content, agent: agentType, history: history || [] }),
        });

        if (!response.ok || !response.body) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        setIsStreaming(true);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullContent = "";

        // Parse the SSE stream
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? ""; // keep any incomplete trailing line

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;

            let event: {
              type: string;
              content?: string;
              agent?: string;
              suggestions?: string[];
              name?: string;
              arguments?: Record<string, unknown>;
              call_id?: string;
              ok?: boolean;
              summary?: string;
            };
            try {
              event = JSON.parse(raw);
            } catch {
              continue; // skip malformed event
            }

            if (event.type === "tool_call") {
              const callId = event.call_id ?? `${Date.now()}`;
              const newCall: ToolCall = {
                id: callId,
                name: event.name ?? "tool",
                arguments: event.arguments ?? {},
                status: "pending",
              };
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, toolCalls: [...(m.toolCalls ?? []), newCall] }
                    : m,
                ),
              );
            } else if (event.type === "tool_result") {
              const callId = event.call_id;
              const nextStatus: ToolCall["status"] = event.ok ? "ok" : "error";
              const nextSummary = event.summary;
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantId || !m.toolCalls?.length) return m;
                  return {
                    ...m,
                    toolCalls: m.toolCalls.map((tc) =>
                      tc.id === callId
                        ? { ...tc, status: nextStatus, summary: nextSummary }
                        : tc,
                    ),
                  };
                }),
              );
            } else if (event.type === "routing") {
              // Triage resolved to a specialist — update agent avatar immediately
              const agentNameMap: Record<string, string> = {
                ClaimsImpactAgent: "claims",
                CrossSellAgent: "crosssell",
                QuoteComparisonAgent: "quote",
                BrokerAgent: "triage",
              };
              const routedAgent = event.agent
                ? agentNameMap[event.agent] ?? agentType
                : agentType;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, agentType: routedAgent as ChatMessage["agentType"] }
                    : m,
                ),
              );
              setStatusMessage(event.content ?? null);
            } else if (event.type === "status") {
              setStatusMessage(event.content ?? null);
            } else if (event.type === "token") {
              fullContent += event.content ?? "";
              const snapshot = fullContent;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: snapshot } : m,
                ),
              );
            } else if (event.type === "done") {
              setStatusMessage(null);
              const finalContent = fullContent;
              // Map backend agent name to frontend agentType key
              const agentNameMap: Record<string, string> = {
                ClaimsImpactAgent: "claims",
                CrossSellAgent: "crosssell",
                QuoteComparisonAgent: "quote",
                BrokerAgent: "triage",
              };
              const resolvedAgent = event.agent
                ? agentNameMap[event.agent] ?? agentType
                : agentType;
              const suggestions = (event as { suggestions?: string[] }).suggestions?.length
                ? (event as { suggestions?: string[] }).suggestions!
                : extractSuggestions(finalContent, resolvedAgent as ChatMessage["agentType"]);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: finalContent,
                        agentType: resolvedAgent as ChatMessage["agentType"],
                        suggestions,
                      }
                    : m,
                ),
              );
            } else if (event.type === "error") {
              throw new Error(event.content ?? "Unknown agent error");
            }
          }
        }
      } catch (err) {
        setStatusMessage(null);
        const errorContent =
          err instanceof Error
            ? err.message
            : "Sorry, I encountered an error. Please try again.";
        // Replace the placeholder with the error text
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: errorContent } : m,
          ),
        );
      } finally {
        setIsLoading(false);
        setIsStreaming(false);
      }
    },
    [conversationId],
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    isLoading,
    isStreaming,
    statusMessage,
    sendMessage,
    clearMessages,
  };
}

// Helper to extract actionable suggestions from response
function extractSuggestions(text: string, agentType?: string): string[] {
  const suggestions: string[] = [];

  // Look for "Next Steps" or "Recommendations" sections
  const nextStepsMatch = text.match(
    /(?:next steps|recommendations|suggested actions)[:\s]*\n([\s\S]*?)(?=\n##|\n---|\n\n\n|$)/i,
  );

  if (nextStepsMatch) {
    // Extract bullet points from the section
    const bulletMatches = nextStepsMatch[1].matchAll(
      /[-•*]\s*(?:\*\*)?([^*\n]+?)(?:\*\*)?(?:\n|$)/g,
    );
    for (const match of bulletMatches) {
      const item = match[1]
        .trim()
        .replace(/^\*\*|\*\*$/g, "") // Remove bold markers
        .replace(/\.$/, ""); // Remove trailing period

      // Only include short, actionable items
      if (item.length > 5 && item.length <= 35) {
        suggestions.push(item);
      } else if (item.length > 35) {
        // Try to shorten by taking first part before dash/comma
        const shortened = item.split(/[—–-]/)[0].split(",")[0].trim();
        if (shortened.length > 5 && shortened.length <= 35) {
          suggestions.push(shortened);
        }
      }
    }
  }

  // If no next steps found, generate contextual suggestions based on agent type
  if (suggestions.length === 0) {
    if (agentType === "claims") {
      suggestions.push("Show claims history", "Analyze impact on premiums", "Identify loss trends");
    } else if (agentType === "quote") {
      suggestions.push("Compare carrier quotes", "Find best coverage match", "Check premium trends");
    } else if (agentType === "crosssell") {
      suggestions.push("Find coverage gaps", "Suggest new product lines", "Identify upsell opportunities");
    } else {
      suggestions.push("Analyze my book of business", "Show upcoming renewals", "Find cross-sell opportunities");
    }
  }

  // Dedupe and limit
  const unique = [...new Set(suggestions)];
  return unique.slice(0, 4);
}

// Connection status
export function useConnectionStatus() {
  const [isConnected, setIsConnected] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    async function checkConnection() {
      try {
        // Health endpoint is at root, not under /api
        const response = await fetch("/health");
        setIsConnected(response.ok);
      } catch {
        setIsConnected(false);
      } finally {
        setChecking(false);
      }
    }

    checkConnection();
    const interval = setInterval(checkConnection, 30000);
    return () => clearInterval(interval);
  }, []);

  return { isConnected, checking };
}
