"""Bot configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the BrokerWorkbench Teams bot."""

    microsoft_app_id: str
    microsoft_app_password: str
    microsoft_app_tenant_id: str = ""
    backend_url: str = "http://localhost:8000"
    bot_port: int = 3978

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
