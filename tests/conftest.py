import io
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

# Hard overrides, not defaults: the developer's .env is loaded by
# pydantic-settings, and a test suite that reaches real SMTP or real object
# storage is a test suite that fails on someone else's laptop.
os.environ["SMTP_HOST"] = ""
os.environ["R2_ACCESS_KEY_ID"] = ""
os.environ["R2_SECRET_ACCESS_KEY"] = ""
os.environ["ENVIRONMENT"] = "test"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.database import Base, get_db
from app.main import app as fastapi_app

# Aliased: `import app.models` binds the name `app` to the package, which would
# otherwise shadow the FastAPI instance.


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def screenshot_files():
    """Three tiny PNGs — enough to satisfy the minimum-screenshot rule."""
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return [
        ("screenshots", (f"shot{i}.png", io.BytesIO(png), "image/png"))
        for i in range(1, 4)
    ]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
