import { useState, useEffect, useCallback } from "react";
import type {
  Policy,
  Client,
  Carrier,
  RenewalDashboard,
  ChatMessage,
  DashboardMetrics,
} from "@/types";

const API_BASE = "/api";

// Generic fetch hook
function useFetch<T>(url: string, initialData: T) {
  const [data, setData] = useState<T>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
}

// Policies
export function usePolicies() {
  return useFetch<Policy[]>(`${API_BASE}/policies/`, []);
}

export function usePolicy(policyId: string) {
  return useFetch<Policy | null>(`${API_BASE}/policies/${policyId}`, null);
}

// Clients
export function useClients() {
  return useFetch<Client[]>(`${API_BASE}/clients/`, []);
}

export function useClient(clientId: string) {
  return useFetch<Client | null>(`${API_BASE}/clients/${clientId}`, null);
}

// Carriers
export function useCarriers() {
  return useFetch<Carrier[]>(`${API_BASE}/carriers/`, []);
}

// Renewals
export function useRenewalDashboard() {
  return useFetch<RenewalDashboard | null>(
    `${API_BASE}/renewals/dashboard`,
    null,
  );
}

// Dashboard Metrics (aggregated)
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
          fetch(`${API_BASE}/renewals/dashboard`),
          fetch(`${API_BASE}/carriers/`),
          fetch(`${API_BASE}/clients/`),
        ]);

        const renewals = renewalsRes.ok ? await renewalsRes.json() : null;
        const carriers = carriersRes.ok ? await carriersRes.json() : [];
        const clients = clientsRes.ok ? await clientsRes.json() : [];

        setMetrics({
          totalPremiumAtRisk: renewals?.total_premium_at_risk || 0,
          policiesInRenewal: renewals?.total_policies || 0,
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

  const sendMessage = useCallback(
    async (
      content: string,
      agentType: "claims" | "crosssell" | "quote" | "triage" = "triage",
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
      const assistantId = (Date.now() + 1).toString();
      const placeholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        agentType,
      };
      setMessages((prev) => [...prev, placeholder]);

      try {
        const response = await fetch(`${API_BASE}/agent/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: content, agent: agentType }),
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

            let event: { type: string; content?: string; agent?: string };
            try {
              event = JSON.parse(raw);
            } catch {
              continue; // skip malformed event
            }

            if (event.type === "status") {
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
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: finalContent,
                        agentType: resolvedAgent as ChatMessage["agentType"],
                        suggestions: extractSuggestions(finalContent),
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
    [],
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
function extractSuggestions(text: string): string[] {
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

  // If no next steps found, generate contextual suggestions based on content
  if (suggestions.length === 0) {
    if (
      text.toLowerCase().includes("quote") ||
      text.toLowerCase().includes("premium")
    ) {
      suggestions.push("Compare all carriers");
      suggestions.push("Request formal quote");
    }
    if (text.toLowerCase().includes("renewal")) {
      suggestions.push("View renewal timeline");
    }
    if (
      text.toLowerCase().includes("claim") ||
      text.toLowerCase().includes("coverage")
    ) {
      suggestions.push("Review coverage details");
    }
    if (
      text.toLowerCase().includes("cross-sell") ||
      text.toLowerCase().includes("opportunity")
    ) {
      suggestions.push("Show all opportunities");
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
