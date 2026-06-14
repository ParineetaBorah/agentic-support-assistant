"""Centralized application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All environment-configured values for the acme-agent API."""

    openai_api_key: str = ""

    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "acme"
    keycloak_client_id: str = "acme-api"
    keycloak_client_secret: str = "acme-api-secret"

    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/acme"
    redis_url: str = "redis://localhost:6379"

    litellm_url: str = "http://localhost:4000"
    litellm_model: str = "gpt-4o-mini"
    litellm_api_key: str = ""

    mcp_server_url: str = "http://localhost:8001/mcp"

    langsmith_api_key: str = ""
    langsmith_tracing: bool = True
    langsmith_project: str = "acme-agent"


settings = Settings()
