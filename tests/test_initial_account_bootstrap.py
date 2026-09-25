"""Isolated database tests for the first three accounts and RBAC grants."""
import io
import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database.database import connect, initialize_database, transaction
from app.services import initial_account_bootstrap as bootstrap
from app.services.authentication_service import AuthenticationService, verify_password
from app.services.authorization_service import require_permission
from app.services.dashboard_service import DashboardService
from app.services.initial_account_bootstrap import (
    PASSWORD_ENVIRONMENT_VARIABLES, account_count, bootstrap_initial_accounts,
    backup_before_bootstrap, main, resolve_initial_passwords,
)
from app.ui import session


class InitialAccountBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "rbac.sqlite"
        initialize_database(self.db)
        self.passwords = {
            "ADMIN": "Strong-Admin-Pass-2026!",
            "HR": "Strong-HR-Password-2026!",
            "STUDENT_SUPPORT": "Strong-Student-2026-Pass!",
        }

    def tearDown(self):
        session.logout()
        self.temp.cleanup()

    def test_seeds_exact_accounts_roles_permissions_and_config_idempotently(self):
        first = bootstrap_initial_accounts(self.passwords, self.db)
        second_passwords = {"ADMIN": "Different-Admin-Password-2026!", "HR": "Different-HR-Password-2026!", "STUDENT_SUPPORT": "Different-Student-Password-2026!"}
        second = bootstrap_initial_accounts(second_passwords, self.db)
        self.assertEqual(sum(item["created"] for item in first.values()), 3)
        self.assertEqual(sum(item["created"] for item in second.values()), 0)
        c = connect(self.db)
        try:
            self.assertEqual(c.execute("select count(*) from accounts").fetchone()[0], 3)
            self.assertEqual(c.execute("select count(*) from roles").fetchone()[0], 3)
            self.assertEqual(c.execute("select count(*) from account_roles").fetchone()[0], 3)
            self.assertEqual(c.execute("select count(*) from system_settings where setting_key like 't6_%'").fetchone()[0], 10)
            for code, password in self.passwords.items():
                username = {"ADMIN":"admin","HR":"hr","STUDENT_SUPPORT":"student_support"}[code]
                row = c.execute("select a.*,r.role_code from accounts a join account_roles ar using(account_id) join roles r using(role_id) where a.username=?", (username,)).fetchone()
                self.assertEqual(row["role_code"], code)
                self.assertTrue(verify_password(password, row["password_hash"], row["password_scheme"]))
                self.assertFalse(verify_password("incorrect password", row["password_hash"], row["password_scheme"]))
            before = [tuple(row) for row in c.execute("select username,password_hash from accounts order by username")]
        finally:
            c.close()
        c = connect(self.db)
        try:
            after = [tuple(row) for row in c.execute("select username,password_hash from accounts order by username")]
            self.assertEqual(before, after)
        finally:
            c.close()

    def test_authentication_loads_permissions_and_logout_clears_service_context(self):
        bootstrap_initial_accounts(self.passwords, self.db)
        admin = AuthenticationService(self.db).login("admin", self.passwords["ADMIN"])
        session.establish(admin)
        self.assertEqual(len(session.role()["blocks"]), 2)
        require_permission("account.manage")
        session.logout()
        with self.assertRaises(PermissionError):
            require_permission("account.manage")

        hr = AuthenticationService(self.db).login("hr", self.passwords["HR"])
        session.establish(hr)
        self.assertEqual(session.role()["blocks"], ("staff",))
        self.assertTrue(session.has_permission("employee.read"))
        self.assertFalse(session.has_permission("account.manage"))
        with self.assertRaises(PermissionError):
            require_permission("account.manage")

    def test_role_context_exposes_every_field_the_header_chip_reads(self):
        bootstrap_initial_accounts(self.passwords, self.db)
        session.establish(AuthenticationService(self.db).login("admin", self.passwords["ADMIN"]))
        context = session.role()
        for key in ("name", "title", "username", "blocks", "accounts", "settings", "permissions"):
            self.assertIn(key, context)
        for value in (context["name"], context["title"]):
            self.assertTrue(value.strip())
            # Mis-decoded Vietnamese labels would reach the sidebar and the chip.
            self.assertNotIn("Ã", value)

    def test_unauthenticated_service_call_is_denied(self):
        with self.assertRaises(PermissionError):
            DashboardService(self.db).overview("staff")


class BootstrapCommandTests(unittest.TestCase):
    """The operator command: backup, random secrets, idempotency, disclosure."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "cli.sqlite"
        self.backups = Path(self.temp.name) / "backups"
        initialize_database(self.db)

    def tearDown(self):
        session.logout()
        self.temp.cleanup()

    def _run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--database", str(self.db), "--backup-directory", str(self.backups)])
        return code, out.getvalue()

    def test_generated_passwords_are_random_distinct_and_usable_for_login(self):
        with patch.dict("os.environ", {}, clear=True):
            code, output = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(account_count(self.db), 3)
        passwords = {}
        for line in output.splitlines():
            if "password=" in line and "<" not in line:
                name, secret = line.split("username=")[1].split(" password=")
                passwords[name.strip()] = secret.strip()
        self.assertEqual(set(passwords), {"admin", "hr", "student_support"})
        self.assertEqual(len(set(passwords.values())), 3)
        for secret in passwords.values():
            self.assertGreaterEqual(len(secret), 16)
        identity = AuthenticationService(self.db).login("admin", passwords["admin"])
        session.establish(identity)
        require_permission("account.manage")

    def test_rerun_creates_nothing_and_discloses_no_secret(self):
        with patch.dict("os.environ", {}, clear=True):
            self._run()
            hashes = self._password_hashes()
            code, output = self._run()
        self.assertEqual(code, 0)
        self.assertNotIn("password=", output)
        self.assertEqual(account_count(self.db), 3)
        self.assertEqual(hashes, self._password_hashes())

    def test_supplied_passwords_are_used_but_never_printed(self):
        supplied = {
            PASSWORD_ENVIRONMENT_VARIABLES["ADMIN"]: "Operator-Chosen-Admin-1!",
            PASSWORD_ENVIRONMENT_VARIABLES["HR"]: "Operator-Chosen-HR-2!",
            PASSWORD_ENVIRONMENT_VARIABLES["STUDENT_SUPPORT"]: "Operator-Chosen-Student-3!",
        }
        with patch.dict("os.environ", supplied, clear=True):
            _, output = self._run()
        for secret in supplied.values():
            self.assertNotIn(secret, output)
        AuthenticationService(self.db).login("hr", "Operator-Chosen-HR-2!")

    def test_backup_is_written_before_any_write_and_never_overwrites(self):
        with patch.dict("os.environ", {}, clear=True):
            self._run()
        copies = sorted(self.backups.glob("*.sqlite"))
        self.assertEqual(len(copies), 1)
        # The copy is the pre-write state: it has no accounts.
        self.assertEqual(account_count(copies[0]), 0)
        with patch.dict("os.environ", {}, clear=True):
            self._run()
        self.assertEqual(len(sorted(self.backups.glob("*.sqlite"))), 2)

    def test_missing_database_file_needs_no_backup(self):
        self.assertIsNone(backup_before_bootstrap(Path(self.temp.name) / "absent.sqlite"))

    def test_environment_passwords_must_differ(self):
        duplicate = {variable: "Same-Password-For-Everyone-1!"
                     for variable in PASSWORD_ENVIRONMENT_VARIABLES.values()}
        with patch.dict("os.environ", duplicate, clear=True), self.assertRaises(ValueError):
            resolve_initial_passwords()

    def _password_hashes(self):
        connection = connect(self.db)
        try:
            return [tuple(row) for row in connection.execute(
                "select username, password_hash from accounts order by username")]
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()


class SyncRolePermissionsTests(unittest.TestCase):
    """Permissions added after a bootstrap can be granted without touching accounts."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "attendance.sqlite"
        initialize_database(self.database)
        bootstrap.bootstrap_initial_accounts(
            {code: f"initial-password-{code.lower()}" for code in bootstrap.ACCOUNT_USERNAMES},
            self.database,
        )

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, query):
        connection = connect(self.database)
        try:
            return [tuple(row) for row in connection.execute(query)]
        finally:
            connection.close()

    def test_a_removed_permission_and_grant_are_restored_and_nothing_else_changes(self):
        accounts = self.snapshot("SELECT account_id,username,password_hash,account_status FROM accounts")
        connection = connect(self.database)
        with transaction(connection, immediate=True):
            connection.execute("DELETE FROM role_permissions WHERE permission_id IN "
                               "(SELECT permission_id FROM permissions WHERE permission_code=?)",
                               ("student.leave.review",))
            connection.execute("DELETE FROM permissions WHERE permission_code=?", ("student.leave.review",))
        connection.close()
        changes = bootstrap.sync_role_permissions(self.database)
        self.assertEqual(changes["permissions"], ["student.leave.review"])
        self.assertIn(("STUDENT_SUPPORT", "student.leave.review"), changes["grants"])
        self.assertIn(("ADMIN", "student.leave.review"), changes["grants"])
        self.assertNotIn(("HR", "student.leave.review"), changes["grants"])
        self.assertEqual(
            self.snapshot("SELECT account_id,username,password_hash,account_status FROM accounts"),
            accounts)

    def test_a_second_run_changes_nothing(self):
        bootstrap.sync_role_permissions(self.database)
        before = self.snapshot("SELECT * FROM role_permissions ORDER BY role_id,permission_id")
        self.assertEqual(bootstrap.sync_role_permissions(self.database),
                         {"permissions": [], "grants": []})
        self.assertEqual(
            self.snapshot("SELECT * FROM role_permissions ORDER BY role_id,permission_id"), before)

    def test_a_renamed_permission_is_reported_instead_of_rewritten(self):
        connection = connect(self.database)
        with transaction(connection, immediate=True):
            connection.execute("UPDATE permissions SET permission_name=? WHERE permission_code=?",
                               ("Tên tuỳ biến", "employee.leave.review"))
        connection.close()
        with self.assertRaises(bootstrap.BootstrapConflictError):
            bootstrap.sync_role_permissions(self.database)
