import { useState, useRef, useEffect, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button, Input, ScrollArea } from "@/components/ui";
import { useChat } from "@/hooks";
import {
  Send,
  RefreshCw,
  MessageSquare,
  BarChart3,
  Target,
  DollarSign,
  Calendar,
  User,
  GripVertical,
  TrendingUp,
  Shield,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Helper to format cell content with colors and badges
function formatCellContent(content: ReactNode): ReactNode {
  if (typeof content !== "string") return content;
  const text = content.trim();

  // Currency values - green for lower prices
  if (/^\$[\d,]+(\.\d{2})?$/.test(text)) {
    const amount = parseFloat(text.replace(/[$,]/g, ""));
    const isLow = amount < 5000;
    return (
      <span
        className={cn(
          "font-semibold",
          isLow
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-slate-700 dark:text-slate-300",
        )}
      >
        {text}
      </span>
    );
  }

  // AM Best ratings - colored badges
  if (/^A\+?\+?$/.test(text)) {
    const colors = {
      "A++":
        "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-800",
      "A+": "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800",
      A: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700",
    };
    return (
      <span
        className={cn(
          "inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold border",
          colors[text as keyof typeof colors] || colors["A"],
        )}
      >
        {text}
      </span>
    );
  }

  // Time values - subtle styling
  if (/^\d+(\.\d+)?\s*(hrs?|hours?|days?)$/i.test(text)) {
    const hours = parseFloat(text);
    const isFast = hours <= 2;
    return (
      <span
        className={cn(
          "text-xs",
          isFast
            ? "text-emerald-600 dark:text-emerald-400 font-medium"
            : "text-slate-600 dark:text-slate-400",
        )}
      >
        {isFast && "⚡ "}
        {text}
      </span>
    );
  }

  return content;
}

// Helper to format text content with inline highlights
function formatTextContent(text: string): ReactNode {
  // Check for urgency patterns
  const urgencyMatch = text.match(
    /(Renewal Urgency|Urgency)[:\s]*(High|Medium|Low)/i,
  );
  if (urgencyMatch) {
    const level = urgencyMatch[2].toLowerCase();
    const colors = {
      high: "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400",
      medium:
        "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400",
      low: "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400",
    };
    const icons = { high: "🔴", medium: "🟡", low: "🟢" };
    const beforeText = text.slice(0, urgencyMatch.index);
    const afterText = text.slice(
      (urgencyMatch.index || 0) + urgencyMatch[0].length,
    );
    return (
      <>
        {beforeText}
        <span
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border ml-1",
            colors[level as keyof typeof colors],
          )}
        >
          {icons[level as keyof typeof icons]} {urgencyMatch[2]}
        </span>
        {afterText}
      </>
    );
  }

  // Check for premium/currency in text
  const currencyMatch = text.match(/(\$[\d,]+(?:\.\d{2})?)/g);
  if (currencyMatch) {
    const parts = text.split(/(\$[\d,]+(?:\.\d{2})?)/);
    return (
      <>
        {parts.map((part, i) =>
          /^\$[\d,]+/.test(part) ? (
            <span
              key={i}
              className="font-semibold text-emerald-600 dark:text-emerald-400"
            >
              {part}
            </span>
          ) : (
            part
          ),
        )}
      </>
    );
  }

  // Check for policy numbers
  if (/Policy Number[:\s]+([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d+)/i.test(text)) {
    const match = text.match(
      /(Policy Number[:\s]+)([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d+)/i,
    );
    if (match) {
      return (
        <>
          {match[1]}
          <code className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-xs font-mono text-blue-600 dark:text-blue-400">
            {match[2]}
          </code>
        </>
      );
    }
  }

  // Check for dates
  const dateMatch = text.match(
    /(\d{2}\/\d{2}\/\d{4})\s*-\s*(\d{2}\/\d{2}\/\d{4})/,
  );
  if (dateMatch) {
    return (
      <>
        {text.slice(0, dateMatch.index)}
        <span className="inline-flex items-center gap-1 text-slate-600 dark:text-slate-400">
          <Calendar className="h-3 w-3" />
          <span className="font-medium">{dateMatch[1]}</span>
          <span className="text-slate-400">→</span>
          <span className="font-medium">{dateMatch[2]}</span>
        </span>
        {text.slice((dateMatch.index || 0) + dateMatch[0].length)}
      </>
    );
  }

  return text;
}

// Custom table components for ReactMarkdown
const markdownComponents: Components = {
  // Enhanced paragraph with smart formatting
  p: ({ children }) => {
    // Convert children to string for pattern matching
    const text =
      typeof children === "string"
        ? children
        : Array.isArray(children)
          ? children.map((c) => (typeof c === "string" ? c : "")).join("")
          : "";

    // Check if this looks like a section header (ends with "Policy" or similar)
    if (
      /^(Commercial|Workers'?|Professional|Cyber|General|Auto)\s+.*(Policy|Insurance|Coverage)$/i.test(
        text.trim(),
      )
    ) {
      return (
        <div className="mt-4 mb-2 px-3 py-2 bg-gradient-to-r from-slate-100 to-slate-50 dark:from-slate-800 dark:to-slate-700 rounded-lg border-l-4 border-blue-500">
          <span className="font-semibold text-slate-800 dark:text-slate-200">
            {children}
          </span>
        </div>
      );
    }

    return (
      <p className="my-1.5">
        {typeof children === "string" ? formatTextContent(children) : children}
      </p>
    );
  },

  // Enhanced list items with key-value detection
  li: ({ children }) => {
    const text =
      typeof children === "string"
        ? children
        : Array.isArray(children)
          ? children.map((c) => (typeof c === "string" ? c : "")).join("")
          : "";

    // Detect key: value pattern
    const kvMatch = text.match(/^([^:]+):\s*(.+)$/);
    if (kvMatch) {
      const [, key, value] = kvMatch;
      return (
        <li className="flex items-start gap-2 py-1 border-b border-dashed border-slate-200 dark:border-slate-700 last:border-0">
          <span className="text-slate-500 dark:text-slate-400 font-medium min-w-[120px] text-xs uppercase tracking-wide">
            {key}:
          </span>
          <span className="text-slate-800 dark:text-slate-200 font-medium">
            {formatTextContent(value)}
          </span>
        </li>
      );
    }

    return (
      <li className="py-0.5">
        {typeof children === "string" ? formatTextContent(children) : children}
      </li>
    );
  },

  // Styled unordered lists
  ul: ({ children }) => (
    <ul className="my-3 space-y-0 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-3 shadow-sm">
      {children}
    </ul>
  ),

  // Strong text with emphasis
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900 dark:text-slate-100">
      {children}
    </strong>
  ),

  table: ({ children }) => (
    <div className="my-4 overflow-x-auto rounded-xl border-2 border-slate-200 dark:border-slate-700 shadow-md">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gradient-to-r from-slate-700 to-slate-800 dark:from-slate-800 dark:to-slate-900 text-white">
      {children}
    </thead>
  ),
  th: ({ children }) => (
    <th className="px-4 py-3 text-left font-semibold text-xs uppercase tracking-wider border-r border-slate-600 last:border-r-0">
      {children}
    </th>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
      {children}
    </tbody>
  ),
  tr: ({ children }) => (
    <tr className="group transition-all duration-150 hover:bg-blue-50 dark:hover:bg-blue-950/40 cursor-pointer hover:shadow-sm">
      {children}
    </tr>
  ),
  td: ({ children }) => (
    <td className="px-4 py-3 border-r border-slate-100 dark:border-slate-800 last:border-r-0 group-hover:border-blue-100 dark:group-hover:border-blue-900 transition-colors">
      {formatCellContent(children)}
    </td>
  ),
};

// Agent configurations with unique icons and colors
const agentConfig = {
  claims: {
    name: "Claims Agent",
    icon: Shield,
    gradient: "from-rose-500 to-red-600",
    textColor: "text-rose-600",
  },
  crosssell: {
    name: "Cross-sell Agent",
    icon: TrendingUp,
    gradient: "from-emerald-500 to-teal-600",
    textColor: "text-emerald-600",
  },
  quote: {
    name: "Quote Agent",
    icon: FileText,
    gradient: "from-blue-500 to-indigo-600",
    textColor: "text-blue-600",
  },
};

const promptSuggestions = [
  {
    label: "Claims impact",
    icon: BarChart3,
    prompt: "Analyze claims impact for CLI001",
  },
  {
    label: "Cross-sell",
    icon: Target,
    prompt: "Find cross-sell opportunities",
  },
  {
    label: "Get quote",
    icon: DollarSign,
    prompt: "Get a quote for commercial auto",
  },
  { label: "Renewals", icon: Calendar, prompt: "Show upcoming renewals" },
];

interface ChatMessageProps {
  message: {
    id: string;
    role: "user" | "assistant";
    content: string;
    timestamp: Date;
    agentType?: string;
    suggestions?: string[];
  };
  onSuggestionClick?: (suggestion: string) => void;
  isClearing?: boolean;
  isStreaming?: boolean;
}

function ChatMessage({
  message,
  onSuggestionClick,
  isClearing,
  isStreaming,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const agent = message.agentType
    ? agentConfig[message.agentType as keyof typeof agentConfig]
    : null;
  const AgentIcon = agent?.icon || FileText;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: isClearing ? 0 : 1, y: isClearing ? -10 : 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className={cn("flex gap-2", isUser && "flex-row-reverse")}
    >
      <div
        className={cn(
          "h-8 w-8 rounded-full flex items-center justify-center shrink-0 shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : agent
              ? `bg-gradient-to-br ${agent.gradient} text-white`
              : "bg-gradient-to-br from-violet-500 to-purple-600 text-white",
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : (
          <AgentIcon className="h-4 w-4" />
        )}
      </div>

      <div
        className={cn(
          "max-w-[85%] rounded-lg p-3",
          isUser ? "bg-primary text-primary-foreground ml-auto" : "bg-muted",
        )}
      >
        {!isUser && agent && (
          <div
            className={cn(
              "flex items-center gap-1.5 text-xs font-semibold mb-2",
              agent.textColor,
            )}
          >
            <AgentIcon className="h-3 w-3" />
            {agent.name}
          </div>
        )}

        <div
          className={cn(
            "text-sm leading-relaxed prose prose-sm max-w-none",
            isUser ? "prose-invert" : "prose-slate",
            // Headings
            "[&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-foreground",
            "[&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-3 [&_h3]:mb-1.5",
            // Text
            "[&_p]:my-1.5 [&_p]:leading-relaxed",
            "[&_ul]:my-2 [&_ul]:pl-4 [&_ul]:space-y-1",
            "[&_ol]:my-2 [&_ol]:pl-4 [&_ol]:space-y-1",
            "[&_li]:text-sm",
            "[&_strong]:font-semibold [&_strong]:text-foreground",
            // Dividers
            "[&_hr]:my-4 [&_hr]:border-border/50",
          )}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {message.content}
          </ReactMarkdown>
          {isStreaming && (
            <span className="inline-block w-[2px] h-[1em] bg-violet-500 align-middle ml-0.5 animate-pulse" />
          )}
        </div>

        {/* Follow-up suggestions */}
        {message.suggestions && message.suggestions.length > 0 && (
          <div className="mt-3 pt-2 border-t border-dashed border-border/50">
            <div className="text-xs text-muted-foreground mb-2">
              Quick actions:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {message.suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => onSuggestionClick?.(suggestion)}
                  className={cn(
                    "text-xs text-white px-2.5 py-1.5 rounded-full hover:opacity-90 transition-opacity",
                    agent
                      ? `bg-gradient-to-r ${agent.gradient}`
                      : "bg-gradient-to-r from-violet-500 to-purple-600",
                  )}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}

interface AIChatPanelProps {
  defaultWidth?: number;
  minWidth?: number;
  maxWidth?: number;
}

export function AIChatPanel({
  defaultWidth = 320,
  minWidth = 280,
  maxWidth = 600,
}: AIChatPanelProps) {
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem("ai-panel-width");
    return saved ? parseInt(saved, 10) : defaultWidth;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [isClearing, setIsClearing] = useState(false);

  const {
    messages,
    isLoading,
    isStreaming,
    statusMessage,
    sendMessage,
    clearMessages,
  } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const resizeRef = useRef<HTMLDivElement>(null);

  // Persist width
  useEffect(() => {
    localStorage.setItem("ai-panel-width", width.toString());
  }, [width]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Resize handling
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = window.innerWidth - e.clientX;
      setWidth(Math.min(Math.max(newWidth, minWidth), maxWidth));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing, minWidth, maxWidth]);

  const handleSend = () => {
    if (!inputValue.trim() || isLoading) return;

    // Detect agent type from prompt
    let agentType: "claims" | "crosssell" | "quote" = "claims";
    const lowerInput = inputValue.toLowerCase();
    if (
      lowerInput.includes("cross-sell") ||
      lowerInput.includes("opportunity")
    ) {
      agentType = "crosssell";
    } else if (lowerInput.includes("quote") || lowerInput.includes("price")) {
      agentType = "quote";
    }

    sendMessage(inputValue, agentType);
    setInputValue("");
  };

  const handleClear = () => {
    setIsClearing(true);
    setTimeout(() => {
      clearMessages();
      setIsClearing(false);
    }, 300);
  };

  const handlePromptClick = (prompt: string) => {
    setInputValue(prompt);
  };

  // Initial demo message
  const displayMessages =
    messages.length === 0
      ? [
          {
            id: "welcome",
            role: "assistant" as const,
            content:
              "I've analyzed the Smith Family renewal. Progressive offers the best value at $190 savings. Should I draft a comparison presentation?",
            timestamp: new Date(),
            suggestions: [
              "Draft presentation",
              "Show all quotes",
              "Add umbrella recommendation",
            ],
          },
        ]
      : messages;

  return (
    <aside
      className="border-l bg-card h-[calc(100vh-4rem)] flex flex-col relative"
      style={{ width }}
    >
      {/* Resize Handle */}
      <div
        ref={resizeRef}
        onMouseDown={() => setIsResizing(true)}
        className={cn(
          "absolute left-0 top-0 bottom-0 w-1.5 cursor-ew-resize z-10 transition-colors flex items-center justify-center",
          isResizing ? "bg-primary" : "hover:bg-primary/50",
        )}
      >
        <GripVertical className="h-4 w-4 text-muted-foreground opacity-0 hover:opacity-100 transition-opacity" />
      </div>

      <div className="flex-1 flex flex-col p-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4" />
            <h3 className="font-semibold text-sm">AI Assistant</h3>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClear}
            className="h-8 px-2"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Clear
          </Button>
        </div>

        {/* Messages */}
        <ScrollArea ref={scrollRef} className="flex-1 pr-2 -mr-2">
          <div className="space-y-4 pb-2">
            <AnimatePresence>
              {displayMessages.map((msg, idx) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onSuggestionClick={(s) => {
                    setInputValue(s);
                  }}
                  isClearing={isClearing}
                  isStreaming={
                    isStreaming &&
                    idx === displayMessages.length - 1 &&
                    msg.role === "assistant"
                  }
                />
              ))}
            </AnimatePresence>

            {/* Status line — shown while tool calls are in progress */}
            {statusMessage && (
              <motion.div
                key="status"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-2 text-muted-foreground text-xs pl-10"
              >
                <RefreshCw className="h-3 w-3 animate-spin text-violet-500" />
                {statusMessage}
              </motion.div>
            )}

            {/* Connecting dots — only before the stream starts */}
            {isLoading && !isStreaming && !statusMessage && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center gap-2 text-muted-foreground text-sm"
              >
                <div className="h-2 w-2 bg-violet-500 rounded-full animate-bounce" />
                <div className="h-2 w-2 bg-violet-500 rounded-full animate-bounce delay-100" />
                <div className="h-2 w-2 bg-violet-500 rounded-full animate-bounce delay-200" />
              </motion.div>
            )}
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="mt-4 space-y-3">
          <div className="flex gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              placeholder="Ask about policies, claims, or get recommendations..."
              className="flex-1 rounded-full text-sm"
            />
            <Button
              onClick={handleSend}
              disabled={!inputValue.trim() || isLoading}
              className="rounded-full px-4"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>

          {/* Prompt Suggestions */}
          <div className="flex flex-wrap gap-1.5 pt-2 border-t">
            {promptSuggestions.map((suggestion) => {
              const Icon = suggestion.icon;
              return (
                <button
                  key={suggestion.label}
                  onClick={() => handlePromptClick(suggestion.prompt)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-muted hover:bg-primary hover:text-primary-foreground transition-colors"
                >
                  <Icon className="h-3 w-3" />
                  {suggestion.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}
