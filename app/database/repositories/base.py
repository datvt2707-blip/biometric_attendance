"""Small SQL CRUD helpers. Table/column names are repository constants only."""
import sqlite3
from typing import Any, Iterable


class BaseRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _insert(self, table: str, values: dict[str, Any]) -> int:
        # Omit unspecified values so SQLite defaults (timestamps/statuses) apply.
        values = {key: value for key, value in values.items() if value is not None}
        columns = tuple(values)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
        cursor = self.connection.execute(sql, tuple(values[c] for c in columns))
        return int(cursor.lastrowid)

    def _get(self, table: str, key: str, value: Any) -> sqlite3.Row | None:
        return self.connection.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,)).fetchone()

    def _list(self, table: str, where: str = "1 = 1", params: Iterable[Any] = (), order: str = "") -> list[sqlite3.Row]:
        suffix = f" ORDER BY {order}" if order else ""
        return self.connection.execute(f"SELECT * FROM {table} WHERE {where}{suffix}", tuple(params)).fetchall()

    def _update(self, table: str, key: str, value: Any, changes: dict[str, Any], allowed: set[str]) -> bool:
        if not changes:
            return False
        invalid = set(changes) - allowed
        if invalid:
            raise ValueError(f"Unsupported columns for {table}: {', '.join(sorted(invalid))}")
        columns = tuple(changes)
        cursor = self.connection.execute(
            f"UPDATE {table} SET {', '.join(c + ' = ?' for c in columns)} WHERE {key} = ?",
            tuple(changes[c] for c in columns) + (value,),
        )
        return cursor.rowcount > 0

    def _delete(self, table: str, key: str, value: Any) -> bool:
        cursor = self.connection.execute(f"DELETE FROM {table} WHERE {key} = ?", (value,))
        return cursor.rowcount > 0
