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

    # --- payments ----------------------------------------------------------
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    CERTIFICATE_FEE_PAISE: int = 5000

    # --- email -------------------------------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "KLS Academy <noreply@klstechsolutions.in>"

    # --- public URLs -------------------------------------------------------
    ACADEMY_BASE_URL: str = "http://localhost:3000"
    ADMIN_BASE_URL: str = "http://localhost:3001"

    # --- bootstrap ---------------------------------------------------------
    FIRST_SUPERADMIN_EMAIL: str = "admin@klstechsolutions.in"
    FIRST_SUPERADMIN_PASSWORD: str = "ChangeThisNow123"

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

    @property
    def payments_configured(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
