from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from the environment. Nothing is hardcoded."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- application -------------------------------------------------------
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PROJECT_NAME: str = "KLS Academy API"
    API_V1_PREFIX: str = "/api/v1"

    # --- database ----------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://kls:kls_dev_password@localhost:5432/kls_academy"

    # --- security ----------------------------------------------------------
    SECRET_KEY: str = "change-me-in-every-environment"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # --- storage (Cloudflare R2) -------------------------------------------
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = "kls-academy"
    R2_PUBLIC_BASE_URL: str = ""


    # --- email -------------------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "KLS Academy <klstechsolutions2025@gmail.com>"

    # --- public URLs -------------------------------------------------------
    ACADEMY_BASE_URL: str = "http://localhost:3000"
    ADMIN_BASE_URL: str = "http://localhost:3001"

    # --- bootstrap ---------------------------------------------------------
    FIRST_SUPERADMIN_EMAIL: str = "admin@klstechsolutions.in"
    # No default. The repository is public, so a working placeholder here
    # would be the first thing anyone tried against a fresh deployment.
    FIRST_SUPERADMIN_PASSWORD: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def storage_configured(self) -> bool:
        return bool(self.R2_ACCESS_KEY_ID and self.R2_SECRET_ACCESS_KEY)



    def validate_for_runtime(self) -> list[str]:
        """
        Configuration problems worth refusing to start over, or at least
        shouting about. Called once from `app.main` on startup.
        """
        problems: list[str] = []

        if self.SECRET_KEY == "change-me-in-every-environment":
            problems.append(
                "SECRET_KEY is still the placeholder. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        elif len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY is shorter than 32 characters")

        if self.is_production:
            if self.DEBUG:
                problems.append("DEBUG must be false in production")
            if any(o.startswith("http://") for o in self.CORS_ORIGINS):
                problems.append("CORS_ORIGINS contains a plain-http origin")
            if not self.FIRST_SUPERADMIN_PASSWORD:
                problems.append("FIRST_SUPERADMIN_PASSWORD is not set")

        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
