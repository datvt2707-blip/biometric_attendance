"""SQLite connection, initialization, and transaction utilities."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "attendance.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(database_path: str | Path | None = None, *, timeout: float = 5.0) -> sqlite3.Connection:
    """Open a configured SQLite connection; the caller owns and closes it."""
    path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database_path: str | Path | None = None) -> Path:
    """Create the schema once, or validate an already initialized database.

    Unversioned databases containing user tables are left untouched and rejected;
    they need an explicit migration instead of an implicit schema overlay.
    """
    path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = connect(path)
    try:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}."
            )
        if version == SCHEMA_VERSION:
            return path
        if version != 0:
            raise sqlite3.DatabaseError(f"No migration is available from schema version {version}.")

        existing = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if existing:
            names = ", ".join(sorted(row[0] for row in existing))
            raise sqlite3.DatabaseError(
                "Refusing to initialize an unversioned, non-empty database; "
                f"inspect and migrate it first. Existing tables: {names}"
            )

        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript("BEGIN IMMEDIATE;\n" + schema + "\nCOMMIT;")
        return path
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def backup_database(destination: str | Path, source_path: str | Path | None = None) -> Path:
    """Create a new consistent SQLite copy; never replace an existing file."""
    target = Path(destination)
    if target.exists():
        raise FileExistsError(f"Tệp đích đã tồn tại, không ghi đè: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomically reserve the path to avoid an exists()/connect() overwrite race.
    with target.open("xb"):
        pass
    source = None
    try:
        source = connect(source_path or DEFAULT_DATABASE_PATH)
        dest = sqlite3.connect(str(target))
        try:
            source.backup(dest)
        finally:
            dest.close()
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            source.close()
    return target


@contextmanager
def transaction(connection: sqlite3.Connection, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Transaction helper that commits on success and rolls back on failure."""
    if connection.in_transaction:
        savepoint = "db_layer_nested_transaction"
        connection.execute(f"SAVEPOINT {savepoint}")
        try:
            yield connection
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise
        return

    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def table_names(connection: sqlite3.Connection) -> list[str]:
    """Return application table names in stable order."""
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]
