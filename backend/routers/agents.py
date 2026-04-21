"""
Agent Router for Insurance Broker Workbench

Provides REST endpoints for interacting with AI agents:
- Quote Comparison Agent
- Cross-Sell Agent
- Claims Impact Agent
"""
import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["AI Agents"])


# =============================================================================
# Request/Response Models
# =============================================================================

class AgentType(str, Enum):
    QUOTE = "quote"
    CROSSSELL = "crosssell"
    CLAIMS = "claims"
    TRIAGE = "triage"


class ChatRequest(BaseModel):
    """Request model for agent chat endpoint."""
    message: str = Field(..., description="User's message to the agent")
    agent: AgentType = Field(..., description="Which agent to use")
    client_id: Optional[str] = Field(None, description="Optional client ID for context")
    conversation_id: Optional[str] = Field(None, description="Continue existing conversation")
    history: Optional[list[dict]] = Field(None, description="Conversation history for context")


class ChatResponse(BaseModel):
    """Response model for agent chat endpoint."""
    response: str = Field(..., description="Agent's response")
    agent: str = Field(..., description="Name of the agent that responded")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for follow-up")


# =============================================================================
# Agent Endpoints
# =============================================================================

@router.post("/chat/stream")
async def agent_chat_stream(request: ChatRequest):
    """
    Streaming version of agent chat. Returns Server-Sent Events (SSE).

    Event types:
      {"type": "status", "content": "Looking up client info..."}  — tool call in progress
      {"type": "token",  "content": "..."}                        — response token (append to UI)
      {"type": "done",   "agent": "ClaimsImpactAgent"}            — stream complete
      {"type": "error",  "content": "..."}                        — error occurred
    """
    return StreamingResponse(
        _stream_agent(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
        },
    )


def _get_contextual_suggestions(agent_type: str, message: str, response_text: str) -> list[str]:
    """Return follow-up suggestions that ADVANCE the conversation.
    
    Rules:
    - Never suggest what was just done (e.g., don't suggest 'Show claims history' after showing it)
    - Suggest the logical NEXT step a broker would take
    - Cross-agent suggestions are good (claims → quote, quote → crosssell)
    - Include client ID in suggestions when we can extract it from context
    """
    msg_lower = message.lower()
    resp_lower = response_text.lower()
    
    # Try to extract client ID from message or response for contextual pills
    import re
    client_match = re.search(r'(CLI\d{3})', message, re.IGNORECASE) or re.search(r'(CLI\d{3})', response_text, re.IGNORECASE)
    client_id = client_match.group(1).upper() if client_match else None
    
    def _with_client(suggestion: str) -> str:
        """Append client ID to suggestion if known."""
        if client_id:
            return f"{suggestion} for {client_id}"
        return suggestion
    
    if agent_type == "claims":
        if "impact" in msg_lower or "premium" in msg_lower:
            # Just showed premium impact → suggest deeper analysis or next actions
            suggestions = [
                _with_client("Show loss ratio trend"),
                _with_client("Get renewal quotes"),
                _with_client("Find coverage gaps"),
            ]
        elif "trend" in msg_lower or "ratio" in msg_lower:
            # Just showed trend → suggest actionable next steps
            suggestions = [
                _with_client("Get renewal quotes"),
                _with_client("Analyze claims impact"),
                _with_client("Check renewal urgency"),
            ]
        elif "history" in msg_lower:
            # Just showed history → suggest analysis or quotes
            suggestions = [
                _with_client("Analyze claims impact"),
                _with_client("Show loss ratio trend"),
                _with_client("Get renewal quotes"),
            ]
        elif "renewal" in msg_lower:
            suggestions = [
                _with_client("Analyze claims impact"),
                _with_client("Get renewal quotes"),
                _with_client("Find coverage gaps"),
            ]
        else:
            suggestions = [
                _with_client("Analyze claims impact"),
                _with_client("Show loss ratio trend"),
                _with_client("Check renewal urgency"),
            ]
    elif agent_type == "quote":
        if "compare" in msg_lower or "quote" in msg_lower:
            # Just compared quotes → suggest next steps
            suggestions = [
                _with_client("Find coverage gaps"),
                _with_client("Analyze claims impact"),
                _with_client("Check renewal urgency"),
            ]
        else:
            suggestions = [
                _with_client("Compare carrier quotes"),
                _with_client("Find coverage gaps"),
                _with_client("Check renewal urgency"),
            ]
    elif agent_type == "crosssell":
        if "gap" in msg_lower or "opportunity" in msg_lower or "cross" in msg_lower:
            # Just showed gaps → suggest getting quotes for them
            suggestions = [
                _with_client("Get quotes for coverage gap"),
                _with_client("Analyze claims impact"),
                _with_client("Check renewal urgency"),
            ]
        else:
            suggestions = [
                _with_client("Find cross-sell opportunities"),
                _with_client("Compare carrier quotes"),
                _with_client("Check renewal urgency"),
            ]
    else:
        # triage/general
        if "renewal" in msg_lower:
            suggestions = [
                _with_client("Analyze claims impact"),
                _with_client("Get renewal quotes"),
                _with_client("Find coverage gaps"),
            ]
        elif "policy" in msg_lower or "policies" in msg_lower:
            suggestions = [
                _with_client("Check renewal urgency"),
                _with_client("Analyze claims impact"),
                _with_client("Find cross-sell opportunities"),
            ]
        else:
            suggestions = ["Show upcoming renewals", "Analyze a client's claims", "Find cross-sell opportunities"]
    
    return suggestions


async def _stream_agent(request: ChatRequest):
    """Async generator yielding SSE events for a streaming agent response."""
    from agents.quote_agent import QuoteComparisonAgent
    from agents.crosssell_agent import CrossSellAgent
    from agents.claims_agent import ClaimsImpactAgent
    from agents.triage_agent import TriageAgent
    from openai import AsyncAzureOpenAI
    from azure.identity import get_bearer_token_provider
    from agents.config import get_credential

    message = request.message
    if request.client_id:
        message = f"[Context: Working with client ID {request.client_id}] {request.message}"

    try:
        resolved_agent = request.agent.value

        # ── Triage routing ──────────────────────────────────────────────
        if request.agent == AgentType.TRIAGE:
            triage = TriageAgent()
            classification = await triage.classify(message)
            intent = classification["intent"]
            logger.info("Triage routed to: %s (confidence=%s)", intent, classification.get("confidence"))

            specialists = {
                "claims": ClaimsImpactAgent,
                "crosssell": CrossSellAgent,
                "quote": QuoteComparisonAgent,
            }

            if intent in specialists:
                agent = specialists[intent]()
                resolved_agent = intent
                yield f"data: {json.dumps({'type': 'routing', 'agent': agent.name, 'content': f'Routing to {agent.name}…'})}\n\n"
            else:
                # general — triage agent answers directly
                agent = triage
                resolved_agent = "triage"
        elif request.agent == AgentType.QUOTE:
            agent = QuoteComparisonAgent()
        elif request.agent == AgentType.CROSSSELL:
            agent = CrossSellAgent()
        elif request.agent == AgentType.CLAIMS:
            agent = ClaimsImpactAgent()
        else:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Unknown agent: {request.agent}'})}\n\n"
            return

        config = agent.config
        token_provider = get_bearer_token_provider(
            get_credential(), "https://cognitiveservices.azure.com/.default"
        )
        client = AsyncAzureOpenAI(
            azure_endpoint=config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=config.api_version,
        )

        messages = [{"role": "system", "content": agent.instructions}]
        # Include conversation history for multi-turn context
        history = request.history
        if history:
            for h in history[-10:]:
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})
        tools = agent.get_tool_definitions()

        # ── Tool-calling phase (non-streamed; emit status events per call) ──
        max_tool_rounds = 3
        tool_round = 0
        while tool_round < max_tool_rounds:
            tool_round += 1
            response = await client.chat.completions.create(
                model=config.model_deployment,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            assistant_msg = response.choices[0].message

            if not assistant_msg.tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in assistant_msg.tool_calls
                ],
            })

            for tc in assistant_msg.tool_calls:
                readable = tc.function.name.replace("_", " ")
                yield f"data: {json.dumps({'type': 'status', 'content': f'Looking up {readable}…'})}\n\n"
                import json as _json
                func_args = _json.loads(tc.function.arguments)
                logger.info("Tool call: %s(%s)", tc.function.name, func_args)
                result = agent.handle_tool_call(tc.function.name, func_args)
                logger.info("Tool result (first 200 chars): %s", result[:200])
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # ── Streaming response phase ──
        stream = await client.chat.completions.create(
            model=config.model_deployment,
            messages=messages,
            stream=True,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

        full_response = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
                yield f"data: {json.dumps({'type': 'token', 'content': chunk.choices[0].delta.content})}\n\n"
                await asyncio.sleep(0.03)  # Smooth typewriter effect for demos

        suggestions = _get_contextual_suggestions(resolved_agent, message, full_response)
        yield f"data: {json.dumps({'type': 'done', 'agent': agent.name, 'suggestions': suggestions})}\n\n"

    except Exception as e:
        logger.error("Streaming agent error: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


@router.get("/chat", response_model=ChatResponse)
async def agent_chat_get(
    message: str,
    agent: AgentType = AgentType.CLAIMS,
    client_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
):
    """
    GET alias for agent chat — accepts query params instead of a JSON body.

    Useful when a corporate proxy (e.g. Zscaler) blocks POST requests to localhost.
    Identical behaviour to POST /api/agent/chat.

    Example:
        /api/agent/chat?message=Analyze+claims+for+CLI001&agent=claims
    """
    req = ChatRequest(
        message=message,
        agent=agent,
        client_id=client_id,
        conversation_id=conversation_id,
    )
    return await _run_agent(req)


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(request: ChatRequest):
    """
    Chat with an AI agent.
    
    Send a message to one of the specialized agents:
    - **quote**: Compare insurance quotes across carriers
    - **crosssell**: Identify coverage gaps and opportunities
    - **claims**: Analyze claims impact on renewals
    
    Include a client_id in your message for client-specific analysis.
    """
    return await _run_agent(request)


async def _run_agent(request: ChatRequest) -> ChatResponse:
    from agents.quote_agent import QuoteComparisonAgent
    from agents.crosssell_agent import CrossSellAgent
    from agents.claims_agent import ClaimsImpactAgent
    from agents.triage_agent import TriageAgent
    from openai import AsyncAzureOpenAI
    from azure.identity import get_bearer_token_provider
    from agents.config import get_credential

    # Build message with context if client_id provided
    message = request.message
    if request.client_id:
        message = f"[Context: Working with client ID {request.client_id}] {request.message}"

    # Select agent (with triage routing)
    try:
        if request.agent == AgentType.TRIAGE:
            triage = TriageAgent()
            classification = await triage.classify(message)
            intent = classification["intent"]
            logger.info("Triage routed to: %s (confidence=%s)", intent, classification.get("confidence"))

            specialists = {
                "claims": ClaimsImpactAgent,
                "crosssell": CrossSellAgent,
                "quote": QuoteComparisonAgent,
            }
            if intent in specialists:
                agent = specialists[intent]()
            else:
                agent = triage
        elif request.agent == AgentType.QUOTE:
            agent = QuoteComparisonAgent()
        elif request.agent == AgentType.CROSSSELL:
            agent = CrossSellAgent()
        elif request.agent == AgentType.CLAIMS:
            agent = ClaimsImpactAgent()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown agent: {request.agent}")

        config = agent.config
        token_provider = get_bearer_token_provider(
            get_credential(), "https://cognitiveservices.azure.com/.default"
        )
        client = AsyncAzureOpenAI(
            azure_endpoint=config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=config.api_version,
        )

        # Build messages with conversation history for multi-turn support
        messages = [{"role": "system", "content": agent.instructions}]
        history = request.history
        if history:
            for h in history[-10:]:
                if h.get("role") in ("user", "assistant") and h.get("content"):
                    messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})
        tools = agent.get_tool_definitions()

        # Tool-calling loop (max 3 rounds)
        max_tool_rounds = 3
        tool_round = 0
        while tool_round < max_tool_rounds:
            tool_round += 1
            response = await client.chat.completions.create(
                model=config.model_deployment,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            assistant_msg = response.choices[0].message

            if not assistant_msg.tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in assistant_msg.tool_calls
                ],
            })

            for tc in assistant_msg.tool_calls:
                func_args = json.loads(tc.function.arguments)
                logger.info("Tool call: %s(%s)", tc.function.name, func_args)
                result = agent.handle_tool_call(tc.function.name, func_args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # Final response (if last round ended with tool calls, do one more non-tool call)
        if assistant_msg.tool_calls:
            response = await client.chat.completions.create(
                model=config.model_deployment,
                messages=messages,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            assistant_msg = response.choices[0].message

        return ChatResponse(
            response=assistant_msg.content or "I couldn't generate a response.",
            agent=agent.name,
            conversation_id=request.conversation_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {str(e)}. Please set AZURE_AI_FOUNDRY_ENDPOINT in .env"
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_agent_http_error(e)


# =============================================================================
# Auth / diagnostic helpers
# =============================================================================

def _raise_agent_http_error(exc: Exception) -> None:
    """
    Translate common Azure / OpenAI exceptions into meaningful HTTP errors.

    - ClientAuthenticationError → 401  (no valid credential)
    - PermissionDeniedError / 403      → 403  (missing RBAC role)
    - ResourceNotFoundError / 404      → 404  (bad deployment name)
    - Everything else                  → 500  (raw message for debugging)
    """
    err_cls = type(exc).__name__
    msg = str(exc)

    # Azure Identity auth failure
    try:
        from azure.core.exceptions import ClientAuthenticationError, ResourceNotFoundError
        if isinstance(exc, ClientAuthenticationError):
            logger.error("Entra auth failure: %s", msg)
            raise HTTPException(
                status_code=401,
                detail=(
                    "Azure Entra authentication failed. "
                    "Local fix options:\n"
                    "  (A) Azure CLI path: run 'az login' on the host then restart the container. "
                    "Verify the ~/.azure volume mount and AZURE_CONFIG_DIR=/home/appuser/.azure in compose.\n"
                    "  (B) Service principal path: set AZURE_CLIENT_ID, AZURE_TENANT_ID, "
                    "AZURE_CLIENT_SECRET in .env and restart. "
                    "The SP must have 'Cognitive Services OpenAI User' role on the endpoint.\n"
                    f"Raw error: {msg}"
                ),
            )
        if isinstance(exc, ResourceNotFoundError):
            logger.error("Endpoint/deployment not found: %s", msg)
            raise HTTPException(
                status_code=404,
                detail=(
                    "Endpoint or model deployment not found. "
                    f"Current AZURE_AI_FOUNDRY_ENDPOINT={os.getenv('AZURE_AI_FOUNDRY_ENDPOINT', '(not set)')} "
                    f"AZURE_AI_MODEL_DEPLOYMENT={os.getenv('AZURE_AI_MODEL_DEPLOYMENT', '(not set)')}. "
                    "Confirm the deployment name in Azure AI Foundry / Azure OpenAI Studio. "
                    f"Raw error: {msg}"
                ),
            )
    except HTTPException:
        raise
    except ImportError:
        pass

    # OpenAI SDK HTTP auth errors
    if "401" in msg or "AuthenticationError" in err_cls or "Unauthorized" in msg:
        logger.error("OpenAI auth error (%s): %s", err_cls, msg)
        raise HTTPException(
            status_code=401,
            detail=(
                f"OpenAI auth error ({err_cls}): token was acquired but the endpoint rejected it. "
                "Check that the credential's principal has 'Cognitive Services OpenAI User' RBAC "
                f"on {os.getenv('AZURE_AI_FOUNDRY_ENDPOINT', '(endpoint not set)')}. "
                f"Raw error: {msg}"
            ),
        )
    if "403" in msg or "PermissionDenied" in err_cls or "Forbidden" in msg:
        logger.error("OpenAI permission error (%s): %s", err_cls, msg)
        raise HTTPException(
            status_code=403,
            detail=(
                f"Permission denied ({err_cls}). "
                "See: https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control "
                f"Raw error: {msg}"
            ),
        )
    if "404" in msg or "DeploymentNotFound" in msg or "NotFound" in err_cls:
        logger.error("Deployment not found (%s): %s", err_cls, msg)
        raise HTTPException(
            status_code=404,
            detail=(
                f"Model deployment not found ({err_cls}). "
                f"AZURE_AI_MODEL_DEPLOYMENT={os.getenv('AZURE_AI_MODEL_DEPLOYMENT', '(not set)')}. "
                f"Raw error: {msg}"
            ),
        )

    logger.error("Unhandled agent error (%s): %s", err_cls, msg)
    raise HTTPException(status_code=500, detail=f"Agent error ({err_cls}): {msg}")


@router.get("/health")
async def agent_auth_health():
    """
    Diagnostic endpoint — checks Entra credential resolution and endpoint reachability.

    Run this to triage auth failures before calling /api/agent/chat:
    - Validates AZURE_AI_FOUNDRY_ENDPOINT is configured
    - Attempts to acquire an Entra token for cognitiveservices.azure.com
    - Lists available OpenAI deployments on the endpoint (lightweight GET, no model call)

    Returns a structured status so you can see exactly which step failed.
    """
    import httpx
    from agents.config import get_credential, AgentConfig
    from azure.identity import get_bearer_token_provider

    results: dict = {
        "config": {},
        "credential": {},
        "endpoint": {},
    }

    # --- 1. Config check ---
    endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT", "")
    model = os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "")
    azure_config_dir = os.getenv("AZURE_CONFIG_DIR", "")
    results["config"] = {
        "AZURE_AI_FOUNDRY_ENDPOINT": endpoint or "(not set — required)",
        "AZURE_AI_MODEL_DEPLOYMENT": model or "(not set — defaults to gpt-4o)",
        "AZURE_CONFIG_DIR": azure_config_dir or "(not set — Azure CLI will use ~/.azure)",
        "AZURE_CLIENT_ID": "(set)" if os.getenv("AZURE_CLIENT_ID") else "(not set)",
        "AZURE_TENANT_ID": "(set)" if os.getenv("AZURE_TENANT_ID") else "(not set)",
        "AZURE_CLIENT_SECRET": "(set)" if os.getenv("AZURE_CLIENT_SECRET") else "(not set)",
        "status": "ok" if endpoint else "error",
    }

    if not endpoint:
        return {"status": "error", "message": "AZURE_AI_FOUNDRY_ENDPOINT is not set", **results}

    # --- 2. Credential / token check ---
    try:
        cred = get_credential()
        token = cred.get_token("https://cognitiveservices.azure.com/.default")
        results["credential"] = {
            "status": "ok",
            "token_acquired": True,
            "expires_on": str(token.expires_on),
        }
    except Exception as exc:
        results["credential"] = {
            "status": "error",
            "token_acquired": False,
            "error": str(exc),
            "hint": (
                "Run 'az login' on the host and restart the container (CLI path), "
                "or set AZURE_CLIENT_ID + AZURE_TENANT_ID + AZURE_CLIENT_SECRET in .env (SP path)."
            ),
        }
        results["endpoint"] = {"status": "skipped", "reason": "credential failed"}
        return {"status": "error", **results}

    # --- 3. Endpoint reachability — probe the configured deployment ---
    try:
        token_provider = get_bearer_token_provider(get_credential(), "https://cognitiveservices.azure.com/.default")
        base = endpoint.rstrip("/")
        if not model:
            results["endpoint"] = {
                "status": "warn",
                "hint": "AZURE_AI_MODEL_DEPLOYMENT is not set — cannot probe deployment.",
            }
        else:
            # GET /openai/deployments/{name} is a valid data-plane call that returns
            # deployment metadata without making a model invocation.
            api_url = f"{base}/openai/deployments/{model}?api-version=2024-12-01-preview"
            async with httpx.AsyncClient(timeout=10) as http:
                resp = await http.get(api_url, headers={"Authorization": f"Bearer {token_provider()}"})
            if resp.status_code == 200:
                data = resp.json()
                results["endpoint"] = {
                    "status": "ok",
                    "http_status": resp.status_code,
                    "deployment": data.get("id") or model,
                    "model": data.get("model"),
                    "status_detail": data.get("status"),
                }
            elif resp.status_code == 404:
                results["endpoint"] = {
                    "status": "error",
                    "http_status": 404,
                    "hint": (
                        f"Deployment '{model}' not found on this endpoint. "
                        "Check the name in Azure OpenAI Studio → Deployments and update "
                        "AZURE_AI_MODEL_DEPLOYMENT in .env."
                    ),
                    "body_preview": resp.text[:400],
                }
            elif resp.status_code in (401, 403):
                results["endpoint"] = {
                    "status": "error",
                    "http_status": resp.status_code,
                    "hint": (
                        "Token was acquired but the endpoint rejected it. "
                        "Assign 'Cognitive Services OpenAI User' role to your principal on the resource."
                    ),
                    "body_preview": resp.text[:400],
                }
            else:
                results["endpoint"] = {
                    "status": "warn",
                    "http_status": resp.status_code,
                    "body_preview": resp.text[:400],
                }
    except Exception as exc:
        results["endpoint"] = {"status": "error", "error": str(exc)}

    overall = "ok" if all(r.get("status") == "ok" for r in results.values()) else "warn"
    return {"status": overall, **results}


@router.get("/agents")
async def list_agents():
    """
    List available AI agents and their capabilities.
    """
    from agents.config import AGENT_CONFIGS
    
    agents = []
    for key, config in AGENT_CONFIGS.items():
        agents.append({
            "id": key,
            "name": config["name"],
            "description": config["description"],
        })
    
    return {
        "agents": agents,
        "usage": {
            "endpoint": "POST /api/agent/chat",
            "body": {
                "message": "Your question or request",
                "agent": "quote | crosssell | claims",
                "client_id": "(optional) Client ID for context",
                "conversation_id": "(optional) Continue a conversation"
            }
        },
        "examples": [
            {
                "description": "Compare cyber liability quotes",
                "request": {
                    "message": "Compare cyber liability quotes for a technology company with $5M revenue",
                    "agent": "quote"
                }
            },
            {
                "description": "Analyze coverage gaps for a client",
                "request": {
                    "message": "What coverage gaps does this client have?",
                    "agent": "crosssell",
                    "client_id": "CLI001"
                }
            },
            {
                "description": "Check claims impact on renewal",
                "request": {
                    "message": "How will this client's claims history affect their renewal?",
                    "agent": "claims",
                    "client_id": "CLI004"
                }
            }
        ]
    }
