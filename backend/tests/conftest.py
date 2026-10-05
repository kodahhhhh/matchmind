"""Integration tests use a disposable database, never the shared demo database."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from matchpulse.config import get_settings
from matchpulse.db.load import apply_schema, load_catalogue, load_events, refresh


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return get_settings().data_dir


@pytest.fixture(scope="session")
def database_url(data_dir: Path) -> Iterator[str]:
    settings = get_settings()
    name = f"matchpulse_test_{uuid4().hex}"
    url = make_conninfo(settings.database_url, dbname=name)
    with psycopg.connect(settings.database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            apply_schema(url, settings.embed_dim)
            load_catalogue(url, data_dir)
            yield url
        finally:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture(scope="session")
def final_url(database_url: str, data_dir: Path) -> str:
    load_events(database_url, data_dir, match_id="sb:3869685", workers=1)
    refresh(database_url)
    return database_url
