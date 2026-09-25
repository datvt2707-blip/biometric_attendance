"""Database initialization tests; all databases are isolated temporary files."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import database
from app.database.database import connect, initialize_database


class DatabaseBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "attendance.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def test_schema_initialization_is_idempotent_and_does_not_seed_business_data(self):
        initialize_database(self.path)
        connection = connect(self.path)
        try:
            connection.execute(
                "INSERT INTO departments(name) VALUES (?)", ("Custom Department",)
            )
            connection.execute(
                "INSERT INTO system_settings(scope,setting_key,setting_value) VALUES (?,?,?)",
                ("staff", "custom_option", "operator-value"),
            )
            connection.commit()
            before = {
                table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in database.table_names(connection)
            }
        finally:
            connection.close()

        initialize_database(self.path)
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            after = {
                table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in database.table_names(connection)
            }
            self.assertEqual(before, after)
            self.assertEqual(connection.execute(
                "SELECT setting_value FROM system_settings WHERE setting_key='custom_option'"
            ).fetchone()[0], "operator-value")
            for table in ("accounts", "roles", "permissions", "account_roles", "role_permissions",
                          "people", "employees", "students", "classes", "employee_attendance",
                          "student_attendance"):
                self.assertEqual(after[table], 0, table)
            self.assertEqual(after["departments"], 1)
            self.assertEqual(after["system_settings"], 1)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], database.SCHEMA_VERSION)
        finally:
            connection.close()

    def test_failed_schema_script_rolls_back_all_ddl(self):
        broken_schema = Path(self.temp.name) / "broken.sql"
        broken_schema.write_text(
            "CREATE TABLE partial_table(id INTEGER PRIMARY KEY);\n"
            "THIS IS NOT VALID SQL;\n",
            encoding="utf-8",
        )
        with patch.object(database, "SCHEMA_PATH", broken_schema):
            with self.assertRaises(sqlite3.DatabaseError):
                initialize_database(self.path)

        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            self.assertEqual(tables, [])
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
