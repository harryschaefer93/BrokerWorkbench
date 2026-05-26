"""
GPT-backed claim description generator with on-disk JSON cache.

A single batched Azure OpenAI call covers every uncached (industry, claim_type,
severity_bucket) tuple per seeder run. Results are cached so subsequent runs are
free. If Entra / endpoint / OpenAI is unavailable, falls back to a deterministic
template so the seeder never blocks the demo.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Cache file lives next to this module under .cache/
_CACHE_DIR = Path(__file__).resolve().parent / ".cache"
_CACHE_FILE = _CACHE_DIR / "claim_descriptions.json"


def _key(industry: str, claim_type: str, severity_bucket: str) -> str:
    return f"{industry}|{claim_type}|{severity_bucket}"


def _load_cache() -> Dict[str, str]:
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read description cache (%s) — starting empty.", exc)
        return {}


def _write_cache(cache: Dict[str, str]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _fallback(industry: str, claim_type: str, severity_bucket: str) -> str:
    pretty_claim = claim_type.replace("_", " ")
    return f"{industry} {pretty_claim} incident, {severity_bucket} severity"


async def _call_azure_inference(uncached_keys: List[str]) -> Dict[str, str]:
    """Make ONE batched chat completion for all uncached keys.

    Uses the Azure AI Inference SDK (`azure-ai-inference`) so it works against
    any chat-completion model deployed on the AI Foundry resource — MaaS
    (Kimi, Mistral, Llama, DeepSeek, etc.) or Azure OpenAI (gpt-4.x).
    Returns {} on any failure; the caller falls back to deterministic templates.
    """
    endpoint = os.getenv("AZURE_AI_INFERENCE_ENDPOINT") or os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
    deployment = os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "Kimi-K2.6")
    api_version = os.getenv("AZURE_AI_API_VERSION", "2024-05-01-preview")

    if not endpoint:
        logger.warning(
            "Neither AZURE_AI_INFERENCE_ENDPOINT nor AZURE_AI_FOUNDRY_ENDPOINT "
            "is set — using fallback descriptions."
        )
        return {}

    try:
        from azure.ai.inference.aio import ChatCompletionsClient
        from azure.ai.inference.models import SystemMessage, UserMessage
        from azure.identity.aio import (
            ChainedTokenCredential,
            EnvironmentCredential,
            ManagedIdentityCredential,
            AzureCliCredential,
        )
    except ImportError as exc:
        logger.warning(
            "azure-ai-inference / azure-identity import failed (%s) — using fallback.", exc
        )
        return {}

    client_id = os.getenv("AZURE_CLIENT_ID")
    credential = ChainedTokenCredential(
        EnvironmentCredential(),
        ManagedIdentityCredential(client_id=client_id),
        AzureCliCredential(),
    )
    try:
        async with ChatCompletionsClient(
            endpoint=endpoint,
            credential=credential,
            credential_scopes=["https://cognitiveservices.azure.com/.default"],
            api_version=api_version,
        ) as client:
            prompt = (
                "For each composite key below, return ONE realistic, neutral, "
                "1-2 sentence commercial-insurance claim description. "
                "Key format: 'industry|claim_type|severity_bucket' "
                "(severity_bucket in low|medium|high). "
                "Return ONLY a JSON object mapping each composite key string to its "
                "description string. No markdown, no commentary.\n\n"
                f"Keys: {json.dumps(uncached_keys)}"
            )
            response = await client.complete(
                model=deployment,
                messages=[
                    SystemMessage(
                        content=(
                            "You generate concise, realistic commercial insurance "
                            "claim descriptions. Output JSON only."
                        )
                    ),
                    UserMessage(content=prompt),
                ],
                temperature=0.7,
                response_format="json_object",
            )
        raw = (response.choices[0].message.content or "{}").strip()
        # Some MaaS models still wrap JSON in markdown fences even when
        # response_format=json_object is requested. Strip them defensively.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        return {k: str(v).strip() for k, v in parsed.items() if isinstance(v, str)}
    except Exception as exc:  # noqa: BLE001 — never block the seeder
        logger.warning("Azure AI Inference call failed (%s) — using fallback descriptions.", exc)
        return {}
    finally:
        try:
            await credential.close()
        except Exception:  # noqa: BLE001
            pass


async def get_claim_descriptions(
    specs: List[Tuple[str, str, str]],
) -> Dict[Tuple[str, str, str], str]:
    """Return a lookup dict for every spec tuple. Uses cache + 1 batched GPT call."""
    cache = _load_cache()
    unique_specs = list({tuple(s) for s in specs})
    uncached: List[Tuple[str, str, str]] = [
        s for s in unique_specs if _key(*s) not in cache
    ]

    if uncached:
        uncached_keys = [_key(*s) for s in uncached]
        gpt_results = await _call_azure_inference(uncached_keys)
        for spec in uncached:
            k = _key(*spec)
            cache[k] = gpt_results.get(k) or _fallback(*spec)
        try:
            _write_cache(cache)
        except OSError as exc:
            logger.warning("Could not write description cache: %s", exc)

    return {spec: cache[_key(*spec)] for spec in unique_specs}


def cache_path() -> Path:
    """Expose the cache file path for verification output."""
    return _CACHE_FILE
