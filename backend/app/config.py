"""Application configuration via pydantic-settings + YAML overrides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TESTHUB_",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_name: str = "AgentMate"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── Server ───────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ── Database ─────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/agenteval.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Storage ──────────────────────────────────────────
    data_dir: str = "./data"
    upload_dir: str = "./data/uploads"
    export_dir: str = "./data/exports"
    max_upload_size_mb: int = 5

    # ── Encryption ───────────────────────────────────────
    encryption_key_file: str = "./data/encryption_key.bin"

    # ── Engine ───────────────────────────────────────────
    engine_max_concurrency: int = 50
    engine_default_concurrency: int = 10
    engine_default_timeout_ms: int = 30_000
    engine_default_max_retries: int = 3
    engine_retry_base_delay_ms: int = 1_000
    engine_retry_max_delay_ms: int = 60_000

    # ── AI Judge ─────────────────────────────────────────
    ai_judge_default_temperature: float = 0.0
    ai_judge_default_max_tokens: int = 2048
    ai_judge_scoring_timeout_ms: int = 30_000
    ai_judge_max_retries: int = 2

    # ── Logging ──────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    log_file: str = "./data/logs/agentmate.log"

    # ── JWT ──────────────────────────────────────────────
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120  # 2 hours

    # ── Metrics ──────────────────────────────────────────
    metrics_enabled: bool = True
    metrics_port: int = 9090

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def resolve_jwt_secret(cls, v: str) -> str:
        """Fallback chain: env var → key file → auto-generate + persist."""
        if v and v.strip():
            return v.strip()

        key_file = Path("./data/jwt_secret.key")
        if key_file.exists():
            key = key_file.read_text().strip()
            if key:
                return key

        # Auto-generate a 64-char hex key and persist it
        import secrets
        key = secrets.token_hex(32)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key)
        # Restrict permissions on Unix-like systems
        try:
            key_file.chmod(0o600)
        except Exception:
            pass
        return key

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def export_path(self) -> Path:
        return Path(self.export_dir)

    def ensure_dirs(self):
        for d in [self.data_path, self.upload_path, self.export_path,
                  self.data_path / "logs"]:
            d.mkdir(parents=True, exist_ok=True)

    def model_dump_json_safe(self) -> str:
        """Dump settings as JSON, masking sensitive fields."""
        d = self.model_dump()
        for key in list(d.keys()):
            if "key" in key.lower() or "credential" in key.lower() or "secret" in key.lower():
                d[key] = "***"
        return json.dumps(d, indent=2, default=str)


settings = Settings()
settings.ensure_dirs()
