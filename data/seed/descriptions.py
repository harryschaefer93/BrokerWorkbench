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


async def _call_azure_openai(uncached_keys: List[str]) -> Dict[str, str]:
    """Make ONE batched chat completion for all uncached keys. Returns {} on any failure."""
    endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
    deployment = os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "gpt-4.1")
    api_version = os.getenv("AZURE_AI_API_VERSION", "2024-12-01-preview")

    if not endpoint:
        logger.warning("AZURE_AI_FOUNDRY_ENDPOINT not set — using fallback descriptions.")
        return {}

    try:
        # Build a ChainedTokenCredential inline so we don't trigger the full
        # backend.agents package import (which pulls in mock_data and tools).
        from azure.identity import (
            ChainedTokenCredential, EnvironmentCredential,
            ManagedIdentityCredential, AzureCliCredential,
            get_bearer_token_provider,
        )
        from openai import AsyncAzureOpenAI
    except ImportError as exc:
        logger.warning("openai/azure-identity import failed (%s) — using fallback.", exc)
        return {}

    try:
        client_id = os.getenv("AZURE_CLIENT_ID")
        credential = ChainedTokenCredential(
            EnvironmentCredential(),
            ManagedIdentityCredential(client_id=client_id),
            AzureCliCredential(),
        )
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
        prompt = (
            "For each composite key below, return ONE realistic, neutral, "
            "1-2 sentence commercial-insurance claim description. "
            "Key format: 'industry|claim_type|severity_bucket' "
            "(severity_bucket in low|medium|high). "
            "Return ONLY a JSON object mapping each composite key string to its "
            "description string. No markdown, no commentary.\n\n"
            f"Keys: {json.dumps(uncached_keys)}"
        )
        completion = await client.chat.completions.create(
            model=deployment,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You generate concise, realistic commercial insurance claim descriptions. Output JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return {k: str(v).strip() for k, v in parsed.items() if isinstance(v, str)}
    except Exception as exc:  # noqa: BLE001 — never block the seeder
        logger.warning("Azure OpenAI call failed (%s) — using fallback descriptions.", exc)
        return {}


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
        gpt_results = await _call_azure_openai(uncached_keys)
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
