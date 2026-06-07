from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


CONFIG_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CONFIG_DIR.parent.parent
WORKSPACE_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "BALATravel API"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./balatravel.db"
    secret_key: str = "change-me-in-production-at-least-32"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 60 * 24 * 7
    algorithm: str = "HS256"
    # Accepts a comma-separated string from the env (e.g. CORS_ORIGINS="https://app.netlify.app,http://localhost:3000")
    # or a real list in code. Useful so the deployed frontend domain can be allowed without a code change.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    storage_dir: Path = Path("storage/exports")
    serpapi_api_key: str | None = None
    serpapi_base_url: str = "https://serpapi.com/search.json"
    serpapi_max_results: int = 5
    place_catalog_max_results: int = 24
    opentripmap_api_key: str | None = None
    opentripmap_base_url: str = "https://api.opentripmap.com/0.1/en/places"
    opentripmap_radius_meters: int = 25000
    google_routes_api_key: str | None = None
    google_routes_http_referer: str | None = None
    openweather_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/auto"
    openrouter_site_url: str | None = None
    openrouter_app_name: str = "BALATravel"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"
    agent_max_steps_reactive: int = 30
    agent_max_steps_autonomous: int = 120
    agent_max_token_budget: int = 800000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env"), str(WORKSPACE_DIR / ".env"), ".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
