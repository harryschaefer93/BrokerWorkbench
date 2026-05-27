"""Azure OpenAI chat client factory for the Foundry handoff workflow.

Reads endpoint / deployment / api-version from env (same vars used by the rest
of the backend) and returns an Agent Framework chat client wired with the
project's standard ``ChainedTokenCredential`` chain.

API drift note (Agent Framework 1.6.0):
    The Python SDK exposes Azure OpenAI via
    ``agent_framework.openai.OpenAIChatClient(azure_endpoint=...)`` rather than
    a dedicated ``AzureOpenAIChatClient`` class (that name exists in the .NET
    SDK only). The single ``OpenAIChatClient`` switches to Azure mode when
    ``azure_endpoint`` is provided.

Model constraint:
    The configured deployment is ``gpt-5`` (``AZURE_AI_MODEL_DEPLOYMENT``),
    which requires ``max_completion_tokens`` rather than ``max_tokens``. This
    factory does NOT pass either parameter — SDK defaults are used.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root the same way backend.agents.config does so that
# this module behaves identically whether imported as a library or run via
# `python -m backend.agents.foundry`.
_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)


def _get_credential():
    """Build the project's standard credential chain.

    Mirrors :func:`backend.agents.config.get_credential` so the handoff
    workflow authenticates exactly like the rest of the backend.
    """
    from azure.identity import (
        AzureCliCredential,
        ChainedTokenCredential,
        EnvironmentCredential,
        ManagedIdentityCredential,
    )

    client_id = os.getenv("AZURE_CLIENT_ID")
    return ChainedTokenCredential(
        EnvironmentCredential(),
        ManagedIdentityCredential(client_id=client_id),
        AzureCliCredential(),
    )


def build_chat_client():
    """Return an Agent Framework Azure OpenAI chat client.

    Environment:
        AZURE_AI_FOUNDRY_ENDPOINT  Required. Azure OpenAI endpoint
                                   (``https://<resource>.openai.azure.com``).
        AZURE_AI_MODEL_DEPLOYMENT  Deployment name. Default ``gpt-5``.
        AZURE_AI_API_VERSION       Default ``2025-03-01-preview`` (Agent
                                   Framework's OpenAIChatClient targets the
                                   ``/responses`` endpoint, which requires
                                   2025-03-01-preview or later on Azure).

    Returns:
        ``agent_framework.openai.OpenAIChatCompletionClient`` configured for Azure.
    """
    from agent_framework.openai import OpenAIChatCompletionClient

    endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
    if not endpoint:
        raise ValueError(
            "AZURE_AI_FOUNDRY_ENDPOINT is required (Azure OpenAI endpoint, "
            "shape: https://<resource>.openai.azure.com)."
        )

    deployment = os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "gpt-5")
    api_version = os.getenv("AZURE_AI_API_VERSION", "2025-03-01-preview")

    logger.info(
        "Foundry handoff chat client: endpoint=%s deployment=%s api_version=%s",
        endpoint,
        deployment,
        api_version,
    )

    return OpenAIChatCompletionClient(
        model=deployment,
        azure_endpoint=endpoint,
        api_version=api_version,
        credential=_get_credential(),
    )
