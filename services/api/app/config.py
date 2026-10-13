from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from the environment (or Docker secrets). Nothing is hard-coded."""

    model_config = SettingsConfigDict(env_prefix="FS_", env_file=".env", extra="ignore")

    # Connects as the RLS-restricted application role.
    database_url: str = "postgresql+asyncpg://fault_app:fault_app@localhost:5432/faultsigma"
    # Connects as the schema owner; used only for migrations and seeding.
    owner_database_url: str = "postgresql+asyncpg://fault_owner:fault_owner@localhost:5432/faultsigma"
    redis_url: str | None = None

    jwt_secret: SecretStr = Field(min_length=32)
    # Key for encrypting sensitive columns (TOTP secrets). Derived from jwt_secret if unset.
    data_key: SecretStr | None = None

    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_s: int = 30 * 24 * 3600
    mfa_token_ttl_s: int = 5 * 60

    max_failed_logins: int = 5
    lockout_s: int = 15 * 60
    login_rate_per_min: int = 10

    cookie_secure: bool = True
    cookie_path: str = "/api/auth"
    totp_issuer: str = "Fault Sigma"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
