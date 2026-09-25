"""CRUD for accounts, roles, permissions, and their associations."""
from dataclasses import asdict
from .base import BaseRepository


_HASH_PREFIXES = {
    "argon2id": ("$argon2id$",),
    "bcrypt": ("$2a$", "$2b$", "$2y$"),
    "scrypt": ("$scrypt$", "scrypt$"),
    "pbkdf2_sha256": ("pbkdf2_sha256$", "$pbkdf2-sha256$"),
}


class AccountRepository(BaseRepository):
    def list_account_directory(self):
        return self.connection.execute(
            "SELECT a.account_id,a.username,COALESCE(p.full_name,'—') AS full_name,a.account_status,"
            "COALESCE(group_concat(r.role_name, ', '),'—') AS roles "
            "FROM accounts a LEFT JOIN people p USING(person_id) "
            "LEFT JOIN account_roles ar USING(account_id) LEFT JOIN roles r USING(role_id) "
            "GROUP BY a.account_id ORDER BY a.username COLLATE NOCASE"
        ).fetchall()

    def list_role_permission_directory(self):
        return self.connection.execute(
            "SELECT r.role_name,p.permission_name FROM role_permissions rp "
            "JOIN roles r USING(role_id) JOIN permissions p USING(permission_id) "
            "ORDER BY r.role_code,p.permission_code"
        ).fetchall()

    def create_account(self, account):
        values = asdict(account); values.pop("account_id", None)
        self._validate_password_hash(values.get("password_hash", ""), values.get("password_scheme", ""))
        return self._insert("accounts", values)
    def get_account(self, account_id): return self._get("accounts", "account_id", account_id)
    def get_account_by_username(self, username):
        return self.connection.execute("SELECT * FROM accounts WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    def list_accounts(self, status=None):
        return self._list("accounts", "account_status = ?" if status else "1 = 1", (status,) if status else (), "username")
    def update_account(self, account_id, changes):
        if "password_hash" in changes or "password_scheme" in changes:
            current = self.get_account(account_id)
            if current is None:
                return False
            self._validate_password_hash(
                changes.get("password_hash", current["password_hash"]),
                changes.get("password_scheme", current["password_scheme"]),
            )
        return self._update("accounts", "account_id", account_id, changes,
            {"person_id", "username", "password_hash", "password_scheme", "account_status", "updated_at", "last_login_at"})
    def delete_account(self, account_id): return self._delete("accounts", "account_id", account_id)

    def create_role(self, role_code, role_name, description=None):
        return self._insert("roles", {"role_code": role_code, "role_name": role_name, "description": description})
    def create_permission(self, permission_code, permission_name, description=None):
        return self._insert("permissions", {"permission_code": permission_code, "permission_name": permission_name, "description": description})
    def assign_role(self, account_id, role_id):
        self.connection.execute("INSERT INTO account_roles(account_id, role_id) VALUES (?, ?)", (account_id, role_id))
    def revoke_role(self, account_id, role_id):
        return self.connection.execute("DELETE FROM account_roles WHERE account_id = ? AND role_id = ?", (account_id, role_id)).rowcount > 0
    def grant_permission(self, role_id, permission_id):
        self.connection.execute("INSERT INTO role_permissions(role_id, permission_id) VALUES (?, ?)", (role_id, permission_id))
    def list_roles(self, account_id=None):
        sql = ("SELECT r.* FROM roles r JOIN account_roles ar ON ar.role_id = r.role_id WHERE ar.account_id = ? ORDER BY r.role_code"
               if account_id is not None else "SELECT * FROM roles ORDER BY role_code")
        return self.connection.execute(sql, (account_id,) if account_id is not None else ()).fetchall()
    def list_permissions(self, role_id=None):
        sql = ("SELECT p.* FROM permissions p JOIN role_permissions rp ON rp.permission_id=p.permission_id WHERE rp.role_id=? ORDER BY p.permission_code"
               if role_id is not None else "SELECT * FROM permissions ORDER BY permission_code")
        return self.connection.execute(sql, (role_id,) if role_id is not None else ()).fetchall()

    @staticmethod
    def _validate_password_hash(encoded_hash, scheme):
        """Reject obvious plaintext; actual hashing belongs in authentication service."""
        prefixes = _HASH_PREFIXES.get(scheme)
        if not prefixes or not isinstance(encoded_hash, str) or len(encoded_hash) < 32 or not encoded_hash.startswith(prefixes):
            raise ValueError("password_hash must be an encoded Argon2id, bcrypt, scrypt, or PBKDF2-SHA256 hash")
