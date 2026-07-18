from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.getenv("PAPERMORROW_DATA_DIR", str(ROOT_DIR / "data"))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


class RuntimeSettings(BaseSettings):
    database_url: str = f"sqlite:///{DATA_DIR / 'paper_radar.db'}"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    semantic_scholar_api_key: str = ""
    openalex_api_key: str = ""
    github_token: str = ""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")


runtime_settings = RuntimeSettings()
