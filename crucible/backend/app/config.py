"""Central configuration for the Crucible backend. Groq-only."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Groq (runs every agent) ---
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # --- Per-role Groq models ---
    victim_model: str = "llama-3.3-70b-versatile"
    orchestrator_model: str = "llama-3.1-8b-instant"
    reporter_model: str = "qwen/qwen3.6-27b"
    judge_model: str = "openai/gpt-oss-120b"

    # --- UiPath Automation Cloud ---
    uipath_base_url: str = "https://staging.uipath.com"
    uipath_org: str = ""
    uipath_tenant: str = ""
    uipath_pat: str = ""
    uipath_client_id: str = ""
    uipath_client_secret: str = ""
    uipath_scopes: str = ""


settings = Settings()
