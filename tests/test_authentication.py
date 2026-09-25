"""Isolated tests for password verification and fail-closed session handling."""
import tempfile
import unittest
from pathlib import Path

from app.database.database import connect, initialize_database
from app.database.models.account import Account
from app.database.repositories.account_repository import AccountRepository
from app.services.authentication_service import (
    AuthenticationError,
    AuthenticationService,
    AuthorizationConfigurationError,
    hash_password,
    verify_password,
)
from app.ui import session


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "auth.sqlite"
        initialize_database(self.db)

    def tearDown(self):
        session.logout()
        self.temp.cleanup()

    def _add_account(self, *, username="operator", password="safe test password 43", status="active",
                     permissions=True):
        connection = connect(self.db)
        try:
            repo = AccountRepository(connection)
            account_id = repo.create_account(Account(
                None, username, hash_password(password), "scrypt", account_status=status,
            ))
            if permissions:
                row = connection.execute("SELECT role_id FROM roles WHERE role_code='TEST_ROLE'").fetchone()
                role_id = int(row["role_id"]) if row else repo.create_role("TEST_ROLE", "Test role")
                row = connection.execute("SELECT permission_id FROM permissions WHERE permission_code='test.open'").fetchone()
                permission_id = int(row["permission_id"]) if row else repo.create_permission("test.open", "Test access")
                repo.assign_role(account_id, role_id)
                if not connection.execute(
                    "SELECT 1 FROM role_permissions WHERE role_id=? AND permission_id=?", (role_id, permission_id)
                ).fetchone():
                    repo.grant_permission(role_id, permission_id)
            connection.commit()
            return account_id
        finally:
            connection.close()

    def test_scrypt_hash_is_salted_and_password_verification_is_constant_time_safe(self):
        first = hash_password("safe test password 43")
        second = hash_password("safe test password 43")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("safe test password 43", first, "scrypt"))
        self.assertFalse(verify_password("wrong password", first, "scrypt"))
        self.assertFalse(verify_password("safe test password 43", first, "bcrypt"))
        self.assertFalse(verify_password("safe test password 43", "plaintext-password-long-enough", "scrypt"))
        with self.assertRaises(ValueError):
            hash_password("short")

    def test_login_loads_actual_roles_and_permissions_and_updates_last_login(self):
        account_id = self._add_account()
        identity = AuthenticationService(self.db).login(" OPERATOR ", "safe test password 43")
        self.assertEqual(identity.account_id, account_id)
        self.assertEqual(identity.roles[0]["role_code"], "TEST_ROLE")
        self.assertEqual(identity.permissions[0]["permission_code"], "test.open")
        connection = connect(self.db)
        try:
            self.assertIsNotNone(connection.execute(
                "SELECT last_login_at FROM accounts WHERE account_id=?", (account_id,)
            ).fetchone()["last_login_at"])
        finally:
            connection.close()

    def test_wrong_password_unknown_and_inactive_accounts_are_rejected(self):
        self._add_account()
        self._add_account(username="disabled", status="disabled")
        service = AuthenticationService(self.db)
        for username, password in (("operator", "wrong password"), ("missing", "anything"),
                                   ("disabled", "safe test password 43")):
            with self.subTest(username=username), self.assertRaises(AuthenticationError):
                service.login(username, password)

    def test_password_change_requires_current_password_and_updates_hash(self):
        self._add_account()
        service = AuthenticationService(self.db)
        with self.assertRaises(AuthenticationError):
            service.change_password("operator", "wrong current password", "New-Strong-Password-2026!")
        service.change_password("operator", "safe test password 43", "New-Strong-Password-2026!")
        self.assertEqual(service.login("operator", "New-Strong-Password-2026!").username, "operator")
        with self.assertRaises(AuthenticationError):
            service.login("operator", "safe test password 43")

    def test_login_refuses_account_without_actual_permission_assignments(self):
        self._add_account(permissions=False)
        with self.assertRaises(AuthorizationConfigurationError):
            AuthenticationService(self.db).login("operator", "safe test password 43")

    def test_session_accepts_authenticated_identity_and_clears_all_claims(self):
        self._add_account()
        identity = AuthenticationService(self.db).login("operator", "safe test password 43")
        session.establish(identity)
        self.assertTrue(session.has_permission("test.open"))
        self.assertFalse(session.has_permission("admin.delete"))
        self.assertEqual(session.require_permission("test.open").account_id, identity.account_id)
        with self.assertRaises(PermissionError):
            session.require_permission("admin.delete")
        with self.assertRaises(PermissionError):
            session.role()  # no approved role-to-screen mapping exists
        session.logout()
        self.assertFalse(session.has_permission("test.open"))
        with self.assertRaises(PermissionError):
            session.identity()
        with self.assertRaises(PermissionError):
            session.establish("admin")

    def test_invalid_stored_hash_and_unsupported_scheme_fail_closed(self):
        connection = connect(self.db)
        try:
            connection.execute(
                "INSERT INTO accounts(username,password_hash,password_scheme) VALUES(?,?,?)",
                ("bad-hash", "scrypt$" + "x" * 40, "scrypt"),
            )
            connection.execute(
                "INSERT INTO accounts(username,password_hash,password_scheme) VALUES(?,?,?)",
                ("legacy", "$2b$" + "x" * 50, "bcrypt"),
            )
            connection.commit()
        finally:
            connection.close()
        for username in ("bad-hash", "legacy"):
            with self.subTest(username=username), self.assertRaises(AuthenticationError):
                AuthenticationService(self.db).login(username, "safe test password 43")


if __name__ == "__main__":
    unittest.main()
