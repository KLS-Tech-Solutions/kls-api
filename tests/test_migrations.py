"""
The migrations must produce a schema the application can actually write to.

Every other test builds tables with `Base.metadata.create_all()`, which reads
the **models**. Production builds them with `alembic upgrade head`, which reads
the **migrations**. Those are two different descriptions of the same schema and
nothing was comparing them.

That gap shipped a real bug: `learning_chapters.created_at` was created NOT NULL
with no column default, while `TimestampMixin` relies entirely on the database
to fill it. Inserts worked in every test and failed on the real database.

These tests run against a migrated database rather than a generated one.
"""

import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from alembic import command


@contextmanager
def _migrated_to(revision: str = "head"):
    """
    Runs the migration chain against a throwaway SQLite file.

    `alembic/env.py` does `from app.core.config import settings` — it binds the
    settings *object*, not the getter. Setting the environment variable is not
    enough, and neither is clearing the `lru_cache`: the module-level `settings`
    has to be replaced, or the migrations quietly run against whatever database
    the test session started with.
    """
    from app.core import config as config_module

    path = Path(tempfile.mkdtemp()) / "migrated.db"
    url = f"sqlite:///{path}"

    previous_env = os.environ.get("DATABASE_URL")
    previous_settings = config_module.settings

    os.environ["DATABASE_URL"] = url
    config_module.get_settings.cache_clear()
    config_module.settings = config_module.get_settings()
    try:
        alembic_config = Config("alembic.ini")
        command.upgrade(alembic_config, revision)
        yield Path(path), alembic_config
    finally:
        if previous_env is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_env
        config_module.get_settings.cache_clear()
        config_module.settings = previous_settings


@pytest.fixture(scope="module")
def migrated_engine():
    """A database built the way production builds it — by running migrations."""
    with _migrated_to() as (path, _):
        yield create_engine(f"sqlite:///{path}")


def test_the_migrated_schema_has_the_tables_the_models_declare(migrated_engine):
    import app.models
    from app.core.database import Base

    migrated = set(inspect(migrated_engine).get_table_names()) - {"alembic_version"}
    declared = set(Base.metadata.tables)

    assert declared - migrated == set(), (
        "the models declare tables the migrations never create: "
        f"{sorted(declared - migrated)}"
    )
    assert migrated - declared == set(), (
        "the migrations create tables no model knows about: "
        f"{sorted(migrated - declared)}"
    )


def test_every_migrated_column_matches_the_model(migrated_engine):
    """
    Names and nullability, compared table by table. Catches a migration that
    forgets a column the model added, which otherwise surfaces as a 500 on
    whichever endpoint touches it first.
    """
    import app.models
    from app.core.database import Base

    inspector = inspect(migrated_engine)
    problems: list[str] = []

    for name, table in Base.metadata.tables.items():
        migrated = {c["name"]: c for c in inspector.get_columns(name)}
        for column in table.columns:
            if column.name not in migrated:
                problems.append(f"{name}.{column.name} is missing from the migration")
                continue
            if bool(migrated[column.name]["nullable"]) != bool(column.nullable):
                problems.append(
                    f"{name}.{column.name} nullability differs: "
                    f"model={column.nullable} migration={migrated[column.name]['nullable']}"
                )

    assert not problems, "\n".join(problems)


def test_columns_the_database_must_fill_actually_have_a_default(migrated_engine):
    """
    The specific defect this file exists for.

    A NOT NULL column whose model has **no Python-side default but does have a
    `server_default`** is one SQLAlchemy never sends on insert — the database is
    expected to fill it. If the migration created that column without a default,
    every insert into the table fails.

    Columns with a Python-side `default=` are excluded: SQLAlchemy always sends
    those, so the database never needs one. That distinction is the whole point
    — checking every timestamp indiscriminately flags three tables that are
    perfectly correct.
    """
    import app.models
    from app.core.database import Base

    inspector = inspect(migrated_engine)
    missing: list[str] = []

    for name, table in Base.metadata.tables.items():
        migrated = {c["name"]: c for c in inspector.get_columns(name)}
        for column in table.columns:
            if column.nullable or column.primary_key:
                continue
            # Something client-side supplies it — the database need not.
            if column.default is not None:
                continue
            # The model says the database fills this one.
            if column.server_default is None:
                continue

            if migrated.get(column.name, {}).get("default") is None:
                missing.append(f"{name}.{column.name}")

    assert not missing, (
        "these columns are NOT NULL and rely on a database default that the "
        f"migration never created — every insert will fail: {sorted(missing)}"
    )


def test_a_chapter_can_actually_be_inserted(migrated_engine):
    """
    The end of the argument: write a row through the ORM into the migrated
    schema, supplying exactly what the application supplies and nothing more.
    """
    from app.models import Difficulty, InternshipDomain, LearningChapter, PublishStatus

    session = sessionmaker(bind=migrated_engine)()
    try:
        domain = InternshipDomain(
            slug=f"backend-{uuid.uuid4().hex[:6]}",
            title="Backend Development",
            description="Build production services.",
            duration="8 weeks",
            difficulty=Difficulty.INTERMEDIATE,
        )
        session.add(domain)
        session.flush()

        # No created_at or updated_at — exactly like the endpoint. The database
        # has to fill them.
        chapter = LearningChapter(
            domain_id=domain.id,
            title="Chapter 1 — HTTP and REST",
            summary="How the web actually talks.",
            order_number=1,
            difficulty=Difficulty.BEGINNER,
            estimated_minutes=30,
            status=PublishStatus.ACTIVE,
        )
        session.add(chapter)
        session.commit()

        stored = session.scalar(
            select(LearningChapter).where(LearningChapter.id == chapter.id)
        )
        assert stored is not None
        assert stored.created_at is not None, "the database default did not fire"
        assert stored.updated_at is not None
    finally:
        session.close()


def test_the_migration_chain_reverses():
    """A downgrade that fails is a migration you cannot back out of."""
    with _migrated_to() as (path, alembic_config):
        command.downgrade(alembic_config, "base")
        remaining = set(inspect(create_engine(f"sqlite:///{path}")).get_table_names())
        assert remaining <= {"alembic_version"}, f"left behind: {sorted(remaining)}"
