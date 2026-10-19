"""PostgreSQL fixtures: application data is never changed by ordinary test cases."""

from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from talent_api.db import engine


@pytest.fixture(scope="module")
def migrated_connection():
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = "test_schema_" + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        try:
            yield connection, config, schema
        finally:
            transaction.rollback()


@pytest.fixture
def db(migrated_connection):
    connection, _, _ = migrated_connection
    # A test-level savepoint also contains commits made by transaction-owning services.
    savepoint = connection.begin_nested()
    try:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
    finally:
        savepoint.rollback()


@pytest.fixture
def committed_factory():
    """Only a disposable named schema is committed, so separate connections can race."""
    schema = "test_committed_" + uuid4().hex
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config.attributes["connection"] = conn
            command.upgrade(config, "head")

        @contextmanager
        def factory():
            with engine.begin() as conn:
                conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                with Session(
                    bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
                ) as session:
                    yield session

        yield factory
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
