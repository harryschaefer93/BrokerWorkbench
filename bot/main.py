"""
BrokerWorkbench Teams Bot — aiohttp entry point.

Endpoints:
  POST /api/messages  — Bot Framework message handler
  GET  /health        — Health check
"""

from aiohttp import web
from botbuilder.core import TurnContext
from botbuilder.core.cloud_adapter_base import CloudAdapterBase
from botbuilder.schema import Activity
from botframework.connector.auth import (
    AuthenticationConfiguration,
    AuthenticationConstants,
    BotFrameworkAuthenticationFactory,
    PasswordServiceClientCredentialFactory,
)

from config import Settings
from bot import BrokerBot

settings = Settings()
_tenant_id = (settings.microsoft_app_tenant_id or "").strip()

_credential_factory = PasswordServiceClientCredentialFactory(
    app_id=settings.microsoft_app_id,
    password=settings.microsoft_app_password,
    tenant_id=_tenant_id or None,
)

if _tenant_id:
    # SingleTenant bot: parameterize auth with tenant-specific login URL so the
    # bot can both (a) validate inbound JWTs from ABS and (b) acquire outbound
    # tokens against the customer tenant authority.
    _auth = BotFrameworkAuthenticationFactory.create(
        validate_authority=True,
        to_channel_from_bot_login_url=(
            f"https://login.microsoftonline.com/{_tenant_id}"
        ),
        to_channel_from_bot_oauth_scope=(
            AuthenticationConstants.TO_CHANNEL_FROM_BOT_OAUTH_SCOPE
        ),
        to_bot_from_channel_token_issuer=(
            AuthenticationConstants.TO_BOT_FROM_CHANNEL_TOKEN_ISSUER
        ),
        oauth_url=AuthenticationConstants.OAUTH_URL,
        to_bot_from_channel_open_id_metadata_url=(
            AuthenticationConstants.TO_BOT_FROM_CHANNEL_OPENID_METADATA_URL
        ),
        to_bot_from_emulator_open_id_metadata_url=(
            AuthenticationConstants.TO_BOT_FROM_EMULATOR_OPENID_METADATA_URL
        ),
        caller_id="urn:botframework:azure",
        credential_factory=_credential_factory,
        auth_configuration=AuthenticationConfiguration(tenant_id=_tenant_id),
    )
else:
    _auth = BotFrameworkAuthenticationFactory.create(
        credential_factory=_credential_factory,
    )

adapter = CloudAdapterBase(_auth)

bot = BrokerBot(settings, adapter=adapter)


async def on_error(context: TurnContext, error: Exception):
    """Global error handler for the adapter."""
    print(f"[on_turn_error] unhandled error: {error}", flush=True)
    await context.send_activity("Sorry, something went wrong. Please try again.")


adapter.on_turn_error = on_error


async def messages(req: web.Request) -> web.Response:
    """Bot Framework message endpoint."""
    if req.content_type != "application/json":
        return web.Response(status=415)

    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    # CloudAdapterBase.process_activity signature is
    # (auth_header_or_authenticate_request_result, activity, logic) — auth FIRST.
    response = await adapter.process_activity(auth_header, activity, bot.on_turn)
    if response:
        return web.json_response(data=response.body, status=response.status)
    return web.Response(status=201)


async def health(req: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "healthy", "service": "broker-bot"})


def init_app(argv=None):
    """Create and return the aiohttp Application (used by CMD)."""
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)
    return app


if __name__ == "__main__":
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=settings.bot_port)
