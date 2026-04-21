"""
BrokerWorkbench Teams Bot — aiohttp entry point.

Endpoints:
  POST /api/messages  — Bot Framework message handler
  GET  /health        — Health check
"""

from aiohttp import web
from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity

from config import Settings
from bot import BrokerBot

settings = Settings()

adapter_settings = BotFrameworkAdapterSettings(
    app_id=settings.microsoft_app_id,
    app_password=settings.microsoft_app_password,
)
adapter = BotFrameworkAdapter(adapter_settings)

bot = BrokerBot(settings)


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

    response = await adapter.process_activity(activity, auth_header, bot.on_turn)
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
