from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


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

    # --- age policy --------------------------------------------------------
    # The DPDP Act 2023 treats anyone under 18 as a child and requires
    # verifiable parental consent before their data may be processed. We have
    # no consent mechanism, so the compliant position is to not hold children's
    # data at all: registration asks for a date of birth and refuses anyone
    # below this age. Configurable so that a consent flow, once built, can
    # lower it without a code change.
    MINIMUM_AGE: int = 18

    # --- storage -----------------------------------------------------------
    # Where offer letters, certificates, chapter notes and task screenshots are
    # written. There is no object store behind this: **the directory is the
    # only copy of every student document.**
    #
    # In production it must point somewhere outside the deployment directory —
    # `/srv/kls/media`, not `./media` — because a redeploy replaces the code
    # tree, and a media folder living inside it would go with it. It must also
    # be in the backup; `docs/DEPLOYMENT.md` covers both.
    MEDIA_ROOT: str = "media"

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
    def is_remote_database(self) -> bool:
        """
        True when Postgres is on another machine — Supabase, or any managed
        host. Changes how the connection pool is tuned, because a socket
        crossing the internet gets closed by things that never touch a local
        one, and it decides whether TLS is demanded at startup.

        Parsed rather than substring-matched. The first version of this asked
        whether the URL contained "@localhost", which answered *true* for
        `sqlite:///./test.db` — no host at all — and then handed psycopg's
        `connect_timeout` to SQLite, which rejects it. A driver with no network
        is not a remote database.
        """
        try:
            url = make_url(self.DATABASE_URL)
        except Exception:  # noqa: BLE001 — an unparseable URL fails later, louder
            return False

        if not url.drivername.startswith("postgresql"):
            return False

        # No host means a Unix socket on this machine.
        host = (url.host or "").lower()
        return bool(host) and host not in ("localhost", "127.0.0.1", "::1", "db")

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

            # The media directory is the only copy of every offer letter and
            # certificate. Inside the deployment tree it is one `git clean` or
            # one redeploy from being gone.
            if not Path(self.MEDIA_ROOT).is_absolute():
                problems.append(
                    f"MEDIA_ROOT ({self.MEDIA_ROOT!r}) is a relative path. In "
                    "production set an absolute path outside the code "
                    "directory, e.g. /srv/kls/media — a redeploy would "
                    "otherwise take every stored document with it"
                )

            # Supabase and every other managed Postgres require TLS. psycopg
            # will happily connect without it if the server allows, and then
            # the credentials and every row cross the internet in clear text.
            if self.is_remote_database and "sslmode=" not in self.DATABASE_URL:
                problems.append(
                    "DATABASE_URL points at a remote host but sets no sslmode. "
                    "Append ?sslmode=require"
                )

        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
