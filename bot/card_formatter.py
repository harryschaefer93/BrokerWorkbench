"""
Markdown → Adaptive Card converter for BrokerWorkbench Teams bot.

Converts the markdown responses from the backend into polished
Adaptive Cards that render well in Microsoft Teams.
"""

import re
from typing import Any

# Agent display metadata
_AGENT_META: dict[str, dict[str, str]] = {
    "ClaimsImpactAgent": {"icon": "\U0001f6e1\ufe0f", "color": "#0078D4", "label": "Claims Agent"},
    "QuoteComparisonAgent": {"icon": "\U0001f4b0", "color": "#107C10", "label": "Quote Agent"},
    "CrossSellAgent": {"icon": "\U0001f3af", "color": "#FFB900", "label": "Cross-Sell Agent"},
    "TriageAgent": {"icon": "\U0001f916", "color": "#5C2D91", "label": "Triage Agent"},
    "BrokerAgent": {"icon": "\U0001f916", "color": "#5C2D91", "label": "Broker Agent"},
}
_DEFAULT_META = {"icon": "\U0001f4cb", "color": "#0078D4", "label": "Agent"}


def _meta(agent_name: str) -> dict[str, str]:
    """Resolve display metadata for a given agent name."""
    # Fuzzy match on key substrings
    name_lower = agent_name.lower()
    for key, val in _AGENT_META.items():
        if key.lower() in name_lower or key.lower().replace("agent", "").strip() in name_lower:
            return val
    if "claim" in name_lower:
        return _AGENT_META["ClaimsImpactAgent"]
    if "quote" in name_lower:
        return _AGENT_META["QuoteComparisonAgent"]
    if "cross" in name_lower:
        return _AGENT_META["CrossSellAgent"]
    if "triage" in name_lower or "broker" in name_lower:
        return _AGENT_META["TriageAgent"]
    return _DEFAULT_META


class CardFormatter:
    """Converts markdown text into Adaptive Card JSON payloads."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Teams enforces a ~28 KB limit on Adaptive Card payloads.
    # Truncate input text to stay safely under that limit.
    _MAX_RESPONSE_CHARS = 12_000

    def format_response(
        self,
        response_text: str,
        agent_name: str,
        suggestions: list[str] | None = None,
    ) -> dict:
        """Build a full Adaptive Card from a markdown response."""
        # Guard against oversized cards (Teams 28KB limit)
        if len(response_text) > self._MAX_RESPONSE_CHARS:
            response_text = response_text[: self._MAX_RESPONSE_CHARS] + "\n\n*…response truncated*"

        body: list[dict] = []
        body.append(self._build_header(agent_name))
        body.extend(self._parse_markdown(response_text))

        actions: list[dict] = []
        if suggestions:
            actions = self._build_suggestions(suggestions)

        # Always add a reset button at the end
        actions.append({
            "type": "Action.Submit",
            "title": "\U0001f504 New Conversation",
            "data": {"message": "/reset"},
            "style": "default",
        })

        return self._wrap_card(body, actions)

    def format_welcome_card(self) -> dict:
        """Polished welcome card shown when the bot is added."""
        body: list[dict] = [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "\U0001f4ca",
                                "size": "Large",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "BrokerWorkbench",
                                "size": "Large",
                                "weight": "Bolder",
                                "color": "Accent",
                            },
                            {
                                "type": "TextBlock",
                                "text": "Your Insurance AI Assistant",
                                "size": "Medium",
                                "isSubtle": True,
                                "spacing": "None",
                            },
                        ],
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": (
                    "I can help you with claims analysis, carrier quotes, "
                    "cross-sell opportunities, and renewal tracking. "
                    "Ask me anything about your book of business."
                ),
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": "Try one of these to get started:",
                "weight": "Bolder",
                "spacing": "Medium",
            },
        ]

        prompts = [
            "Show upcoming renewals",
            "Analyze claims impact for CLI001",
            "Compare carrier quotes for commercial property",
            "Find cross-sell opportunities for CLI003",
        ]
        actions = [
            {
                "type": "Action.Submit",
                "title": p,
                "data": {"message": p},
                "style": "positive" if i == 0 else "default",
            }
            for i, p in enumerate(prompts)
        ]

        return self._wrap_card(body, actions)

    def format_error_card(self, error_msg: str) -> dict:
        """Error card with red accent and retry suggestion."""
        body: list[dict] = [
            {
                "type": "Container",
                "style": "attention",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "\u26a0\ufe0f Something went wrong",
                        "weight": "Bolder",
                        "size": "Medium",
                        "color": "Attention",
                    },
                    {
                        "type": "TextBlock",
                        "text": error_msg[:500],
                        "wrap": True,
                        "isSubtle": True,
                    },
                ],
            }
        ]
        actions = [
            {
                "type": "Action.Submit",
                "title": "Show upcoming renewals",
                "data": {"message": "Show upcoming renewals"},
                "style": "positive",
            }
        ]
        return self._wrap_card(body, actions)

    def format_reset_card(self) -> dict:
        """Card confirming conversation has been cleared."""
        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": "\u2705 Conversation cleared",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "TextBlock",
                "text": "Your conversation history has been reset. What would you like to explore?",
                "wrap": True,
                "isSubtle": True,
                "spacing": "Small",
            },
        ]
        prompts = [
            "Show upcoming renewals",
            "Analyze claims impact for CLI001",
            "Compare carrier quotes for commercial property",
            "Find cross-sell opportunities for CLI003",
        ]
        actions = [
            {
                "type": "Action.Submit",
                "title": p,
                "data": {"message": p},
                "style": "positive" if i == 0 else "default",
            }
            for i, p in enumerate(prompts)
        ]
        return self._wrap_card(body, actions)

    def format_routing_card(self, agent_name: str) -> dict:
        """Small card indicating routing to a specialist agent."""
        m = _meta(agent_name)
        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": f"{m['icon']} Routing to {m['label']}\u2026",
                "isSubtle": True,
                "spacing": "None",
            }
        ]
        return self._wrap_card(body)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self, agent_name: str) -> dict:
        m = _meta(agent_name)
        return {
            "type": "ColumnSet",
            "columns": [
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {"type": "TextBlock", "text": m["icon"], "size": "Medium"}
                    ],
                },
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": m["label"],
                            "weight": "Bolder",
                            "color": "Accent",
                        }
                    ],
                    "verticalContentAlignment": "Center",
                },
            ],
        }

    # ------------------------------------------------------------------
    # Markdown → Adaptive Card body elements
    # ------------------------------------------------------------------

    def _parse_markdown(self, text: str) -> list[dict]:
        """Parse markdown into a list of Adaptive Card body elements."""
        elements: list[dict] = []
        lines = text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Blank line — skip
            if not stripped:
                i += 1
                continue

            # Horizontal rule
            if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
                elements.append({"type": "TextBlock", "text": " ", "separator": True, "spacing": "Medium"})
                i += 1
                continue

            # Heading
            heading_match = re.match(r"^(#{1,4})\s+(.*)", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                size = "ExtraLarge" if level == 1 else "Large" if level == 2 else "Medium"
                elements.append(
                    {
                        "type": "TextBlock",
                        "text": heading_text,
                        "size": size,
                        "weight": "Bolder",
                        "wrap": True,
                        "spacing": "Medium",
                    }
                )
                i += 1
                continue

            # Table detection — look for header row, separator row, data rows
            if "|" in stripped and i + 1 < len(lines):
                table_lines: list[str] = []
                j = i
                while j < len(lines) and "|" in lines[j].strip():
                    table_lines.append(lines[j].strip())
                    j += 1
                if len(table_lines) >= 2 and re.match(
                    r"^\|?[\s\-:|]+\|", table_lines[1]
                ):
                    table_el = self._parse_table(table_lines)
                    if table_el:
                        elements.append(table_el)
                    i = j
                    continue

            # Unordered list item
            list_match = re.match(r"^[-*]\s+(.*)", stripped)
            if list_match:
                list_items: list[str] = []
                j = i
                while j < len(lines):
                    lm = re.match(r"^\s*[-*]\s+(.*)", lines[j])
                    if lm:
                        list_items.append(lm.group(1).strip())
                        j += 1
                    else:
                        break
                for item in list_items:
                    elements.append(
                        {
                            "type": "TextBlock",
                            "text": f"\u2022 {self._inline_format(item)}",
                            "wrap": True,
                            "spacing": "Small",
                        }
                    )
                i = j
                continue

            # Ordered list item
            ol_match = re.match(r"^\d+\.\s+(.*)", stripped)
            if ol_match:
                ol_items: list[str] = []
                j = i
                num = 1
                while j < len(lines):
                    om = re.match(r"^\s*\d+\.\s+(.*)", lines[j])
                    if om:
                        ol_items.append(om.group(1).strip())
                        j += 1
                    else:
                        break
                for idx, item in enumerate(ol_items, start=1):
                    elements.append(
                        {
                            "type": "TextBlock",
                            "text": f"{idx}. {self._inline_format(item)}",
                            "wrap": True,
                            "spacing": "Small",
                        }
                    )
                i = j
                continue

            # Plain paragraph (may contain urgency/status badges or currency)
            elements.extend(self._parse_paragraph(stripped))
            i += 1

        return elements

    # ------------------------------------------------------------------
    # Table parsing
    # ------------------------------------------------------------------

    def _parse_table(self, table_lines: list[str]) -> dict | None:
        """Convert markdown table lines into an Adaptive Card Table element."""

        def _split_row(line: str) -> list[str]:
            line = line.strip().strip("|")
            return [c.strip() for c in line.split("|")]

        if len(table_lines) < 2:
            return None

        headers = _split_row(table_lines[0])
        # Skip separator row (index 1)
        data_rows = [_split_row(l) for l in table_lines[2:]]

        # Wide tables (>5 columns) render poorly in Teams — use vertical FactSet layout
        if len(headers) > 5:
            return self._parse_table_as_facts(headers, data_rows)

        columns_def = [
            {"width": 1} for _ in headers
        ]

        # Header row
        header_cells = [
            {
                "type": "TableCell",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": h,
                        "weight": "Bolder",
                        "wrap": True,
                    }
                ],
            }
            for h in headers
        ]

        rows: list[dict] = [
            {
                "type": "TableRow",
                "style": "accent",
                "cells": header_cells,
            }
        ]

        for idx, row_data in enumerate(data_rows):
            # Pad short rows
            while len(row_data) < len(headers):
                row_data.append("")
            cells = [
                {
                    "type": "TableCell",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": self._inline_format(cell),
                            "wrap": True,
                        }
                    ],
                }
                for cell in row_data[: len(headers)]
            ]
            style = "accent" if idx % 2 == 1 else "default"
            rows.append({"type": "TableRow", "style": style, "cells": cells})

        return {
            "type": "Table",
            "gridStyle": "accent",
            "firstRowAsHeader": True,
            "showGridLines": True,
            "columns": columns_def,
            "rows": rows,
            "spacing": "Medium",
        }

    def _parse_table_as_facts(
        self, headers: list[str], data_rows: list[list[str]]
    ) -> dict:
        """Render a wide table as vertical FactSet cards (one per row)."""
        max_rows = 8
        truncated = len(data_rows) > max_rows
        visible_rows = data_rows[:max_rows]

        items: list[dict] = []
        for idx, row_data in enumerate(visible_rows):
            # Pad short rows
            while len(row_data) < len(headers):
                row_data.append("")
            facts = [
                {"title": h, "value": self._inline_format(row_data[i])}
                for i, h in enumerate(headers)
            ]
            items.append(
                {
                    "type": "FactSet",
                    "separator": idx != 0,
                    "facts": facts,
                }
            )

        if truncated:
            remaining = len(data_rows) - max_rows
            items.append(
                {
                    "type": "TextBlock",
                    "text": f"\u2026and {remaining} more",
                    "isSubtle": True,
                    "spacing": "Small",
                    "wrap": True,
                }
            )

        return {
            "type": "Container",
            "style": "default",
            "spacing": "Medium",
            "items": items,
        }

    # ------------------------------------------------------------------
    # Inline formatting helpers
    # ------------------------------------------------------------------

    def _inline_format(self, text: str) -> str:
        """Convert markdown bold/italic to Adaptive Card text weight markers.

        Adaptive Cards TextBlock supports a subset of markdown-like formatting
        when using the ``text`` property, but not full markdown.  We leave
        **bold** and *italic* markers as-is because Teams' Adaptive Card
        renderer interprets them.
        """
        return text

    def _parse_paragraph(self, text: str) -> list[dict]:
        """Return elements for a plain-text paragraph, detecting badges & currency."""
        elements: list[dict] = []

        # Status / urgency badges
        urgency_color = self._detect_urgency_color(text)
        if urgency_color:
            elements.append(
                {
                    "type": "Container",
                    "style": "emphasis",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": self._inline_format(text),
                            "wrap": True,
                            "color": urgency_color,
                            "weight": "Bolder",
                        }
                    ],
                    "spacing": "Small",
                }
            )
            return elements

        # Currency highlight
        currency_match = re.search(r"\$[\d,]+(?:\.\d{2})?", text)
        if currency_match:
            elements.append(
                {
                    "type": "TextBlock",
                    "text": self._inline_format(text),
                    "wrap": True,
                    "spacing": "Small",
                }
            )
            return elements

        # Default paragraph
        elements.append(
            {
                "type": "TextBlock",
                "text": self._inline_format(text),
                "wrap": True,
                "spacing": "Small",
            }
        )
        return elements

    @staticmethod
    def _detect_urgency_color(text: str) -> str | None:
        """Return an Adaptive Card color name if the text contains urgency markers."""
        t = text.lower()
        if any(kw in t for kw in ["\U0001f534", "critical", "urgent", "high risk"]):
            return "Attention"
        if any(kw in t for kw in ["\U0001f7e1", "warning", "medium risk"]):
            return "Warning"
        if any(kw in t for kw in ["\U0001f7e2", "low risk", "normal", "no issues"]):
            return "Good"
        return None

    # ------------------------------------------------------------------
    # Suggestion buttons
    # ------------------------------------------------------------------

    def _build_suggestions(self, suggestions: list[str]) -> list[dict]:
        actions: list[dict] = []
        for i, s in enumerate(suggestions[:4]):
            actions.append(
                {
                    "type": "Action.Submit",
                    "title": s,
                    "data": {"message": s},
                    "style": "positive" if i == 0 else "default",
                }
            )
        return actions

    # ------------------------------------------------------------------
    # Card wrapper
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_card(
        body: list[dict], actions: list[dict] | None = None
    ) -> dict:
        card: dict[str, Any] = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": body,
        }
        if actions:
            card["actions"] = actions
        return card
