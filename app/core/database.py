from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def _engine_options() -> dict:
    """
    Pool settings, which differ meaningfully for a managed Postgres.

    Against a local server the defaults are fine. Against Supabase — or any
    database reached over the internet through a pooler — three things change:

    * **`pool_recycle`.** Supavisor and most managed poolers drop connections
      that have been idle for a few minutes. SQLAlchemy does not find out until
      it tries to use one, and the symptom is an intermittent
      "server closed the connection unexpectedly" on a request that did nothing
      wrong. Recycling well inside that window means we close them first.
      `pool_pre_ping` catches the rest.

    * **A smaller pool.** Supabase's free and Pro tiers have a modest
      connection budget shared across everything that talks to the database.
      Two uvicorn workers each holding a large pool is how a deployment
      exhausts it and starts refusing connections for reasons that look
      nothing like "too many connections".

    * **A connect timeout.** Without one, a network blackhole hangs the worker
      on a socket that will never answer, and the health check keeps passing
      because the process is alive.
    """
    options: dict = {
        "pool_pre_ping": True,  # survives restarts, idle timeouts and failovers
        "echo": settings.DEBUG and settings.ENVIRONMENT == "development",
    }

    if settings.is_remote_database:
        options.update(
            pool_size=5,
            max_overflow=5,
            pool_recycle=240,
            pool_timeout=30,
            connect_args={"connect_timeout": 10},
        )

    return options


engine = create_engine(settings.DATABASE_URL, **_engine_options())

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Declarative base for every model."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
