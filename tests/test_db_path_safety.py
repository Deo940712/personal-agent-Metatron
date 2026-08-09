"""part-020 slice-002: DB path safety boundary tests."""

from pathlib import Path

import pytest

from core import stm


def test_connect_rejects_missing_database_path(tmp_path: Path) -> None:
    """A typo path must fail closed instead of creating an empty SQLite file."""
    missing = tmp_path / "typo-state.db"
    with pytest.raises(FileNotFoundError):
        stm.connect(missing)
    assert not missing.exists()


def test_connect_opens_initialized_database(tmp_path: Path) -> None:
    """Explicit initialization remains the supported database creation path."""
    database = tmp_path / "state.db"
    stm.init(database)
    connection = stm.connect(database)
    try:
        assert "schedule" in stm.existing_tables(database)
    finally:
        connection.close()


def test_init_creates_missing_database(tmp_path: Path) -> None:
    """The explicit init command may create its requested database."""
    database = tmp_path / "nested" / "state.db"
    assert not database.exists()
    assert stm.init(database) == database
    assert database.exists()


