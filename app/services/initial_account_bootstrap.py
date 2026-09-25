"""Repeatable, narrowly scoped initialization for the three first staff users."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import secrets

from app.database.database import (
    DEFAULT_DATABASE_PATH, backup_database, connect, initialize_database, transaction,
)
from app.services.authentication_service import hash_password
from app.services.authorization_service import (
    ACCOUNT_USERNAMES, PERMISSION_NAMES, ROLE_DEFINITIONS, ROLE_PERMISSION_CODES,
)


class BootstrapConflictError(RuntimeError):
    """An existing identity or RBAC record needs explicit review."""


def bootstrap_initial_accounts(passwords, database_path=None):
    """Create missing initial accounts and grants without changing existing hashes.

    `passwords` must map ADMIN, HR, and STUDENT_SUPPORT to unique 12+ character
    initial passwords. Existing accounts are left untouched so reruns cannot
    silently rotate a credential.
    """
    required = set(ACCOUNT_USERNAMES)
    if not isinstance(passwords, dict) or set(passwords) != required:
        raise ValueError("Phải cung cấp đúng ba mật khẩu cho ADMIN, HR và STUDENT_SUPPORT.")
    if len(set(passwords.values())) != len(required):
        raise ValueError("Mỗi tài khoản phải có mật khẩu riêng.")
    encoded = {code: hash_password(passwords[code]) for code in required}
    connection = connect(database_path)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        required_tables = {"accounts", "roles", "permissions", "account_roles", "role_permissions"}
        if not required_tables.issubset(tables):
            raise BootstrapConflictError("Schema không có đủ bảng accounts/RBAC cần thiết.")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(accounts)")}
        if not {"account_id", "username", "password_hash", "password_scheme", "account_status"}.issubset(columns):
            raise BootstrapConflictError("Cấu trúc bảng accounts không tương thích và được giữ nguyên.")

        with transaction(connection, immediate=True):
            account_ids, role_ids, permission_ids, created_accounts = {}, {}, {}, set()
            for role_code, username in ACCOUNT_USERNAMES.items():
                existing = connection.execute(
                    "SELECT * FROM accounts WHERE username = ? COLLATE NOCASE", (username,)
                ).fetchone()
                if existing:
                    if (existing["person_id"] is not None or existing["account_status"] != "active"
                            or existing["password_scheme"] != "scrypt"):
                        raise BootstrapConflictError(
                            f"Tài khoản {username} đã tồn tại với trạng thái hoặc liên kết khác; không tự động tái sử dụng."
                        )
                    account_ids[role_code] = int(existing["account_id"])
                else:
                    account_ids[role_code] = int(connection.execute(
                        "INSERT INTO accounts(username,password_hash,password_scheme,account_status) VALUES(?,?,?,?)",
                        (username, encoded[role_code], "scrypt", "active"),
                    ).lastrowid)
                    created_accounts.add(role_code)

            for role_code, (role_name, description) in ROLE_DEFINITIONS.items():
                row = connection.execute("SELECT * FROM roles WHERE role_code=?", (role_code,)).fetchone()
                if row and (row["role_name"] != role_name):
                    raise BootstrapConflictError(f"Role {role_code} đã tồn tại với tên khác; cần kiểm tra thủ công.")
                role_ids[role_code] = int(row["role_id"] if row else connection.execute(
                    "INSERT INTO roles(role_code,role_name,description) VALUES(?,?,?)",
                    (role_code, role_name, description),
                ).lastrowid)

            for code, name in PERMISSION_NAMES.items():
                row = connection.execute("SELECT * FROM permissions WHERE permission_code=?", (code,)).fetchone()
                if row and row["permission_name"] != name:
                    raise BootstrapConflictError(f"Permission {code} đã tồn tại với tên khác; cần kiểm tra thủ công.")
                permission_ids[code] = int(row["permission_id"] if row else connection.execute(
                    "INSERT INTO permissions(permission_code,permission_name) VALUES(?,?)", (code, name),
                ).lastrowid)

            for role_code, role_id in role_ids.items():
                account_id = account_ids[role_code]
                assigned = {int(row[0]) for row in connection.execute(
                    "SELECT role_id FROM account_roles WHERE account_id=?", (account_id,)
                )}
                if assigned and assigned != {role_id}:
                    raise BootstrapConflictError(f"Tài khoản {ACCOUNT_USERNAMES[role_code]} đang có role khác; không tự động thay đổi.")
                connection.execute("INSERT OR IGNORE INTO account_roles(account_id,role_id) VALUES(?,?)", (account_id, role_id))
                for code in ROLE_PERMISSION_CODES[role_code]:
                    connection.execute("INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)",
                                       (role_id, permission_ids[code]))
        from app.services.settings_service import SettingsService
        SettingsService(database_path).initialize_liveness_config(
            updated_by_account_id=account_ids["ADMIN"]
        )
        return {code: {"account_id": account_ids[code], "username": ACCOUNT_USERNAMES[code],
                       "role_id": role_ids[code], "created": code in created_accounts}
                for code in ACCOUNT_USERNAMES}
    finally:
        connection.close()


def sync_role_permissions(database_path=None):
    """Insert permissions and role grants added after a database was bootstrapped.

    Purely additive: accounts, passwords, existing grants and every other row are
    left untouched, and a permission whose stored name differs is reported rather
    than rewritten. Returns the codes and (role_code, permission_code) pairs added.
    """
    connection = connect(database_path)
    try:
        added_permissions, added_grants = [], []
        with transaction(connection, immediate=True):
            permission_ids = {}
            for code, name in PERMISSION_NAMES.items():
                row = connection.execute(
                    "SELECT * FROM permissions WHERE permission_code=?", (code,)
                ).fetchone()
                if row and row["permission_name"] != name:
                    raise BootstrapConflictError(
                        f"Permission {code} đã tồn tại với tên khác; cần kiểm tra thủ công.")
                if row:
                    permission_ids[code] = int(row["permission_id"])
                    continue
                permission_ids[code] = int(connection.execute(
                    "INSERT INTO permissions(permission_code,permission_name) VALUES(?,?)",
                    (code, name),
                ).lastrowid)
                added_permissions.append(code)
            for role_code, codes in ROLE_PERMISSION_CODES.items():
                role = connection.execute(
                    "SELECT role_id FROM roles WHERE role_code=?", (role_code,)
                ).fetchone()
                if role is None:
                    continue
                granted = {int(item[0]) for item in connection.execute(
                    "SELECT permission_id FROM role_permissions WHERE role_id=?", (int(role[0]),))}
                for code in codes:
                    if permission_ids[code] in granted:
                        continue
                    connection.execute(
                        "INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)",
                        (int(role[0]), permission_ids[code]))
                    added_grants.append((role_code, code))
        return {"permissions": added_permissions, "grants": added_grants}
    finally:
        connection.close()


PASSWORD_ENVIRONMENT_VARIABLES = {
    code: f"BIOMETRIC_ATTENDANCE_BOOTSTRAP_PASSWORD_{code}" for code in ACCOUNT_USERNAMES
}


def generate_initial_password() -> str:
    """Return a cryptographically random password accepted by hash_password()."""
    return secrets.token_urlsafe(24)


def resolve_initial_passwords(environ=None):
    """Read one password per role from the environment, or generate a random one.

    Returns (passwords, generated_codes). Values are never written to logs; the
    caller decides how to disclose the generated ones.
    """
    environ = os.environ if environ is None else environ
    passwords, generated = {}, set()
    for code, variable in PASSWORD_ENVIRONMENT_VARIABLES.items():
        supplied = environ.get(variable, "")
        if supplied:
            passwords[code] = supplied
        else:
            passwords[code] = generate_initial_password()
            generated.add(code)
    if len(set(passwords.values())) != len(passwords):
        raise ValueError("Mỗi tài khoản phải có mật khẩu riêng.")
    return passwords, generated


def account_count(database_path=None) -> int:
    """Number of rows in accounts; 0 means nobody can sign in yet."""
    connection = connect(database_path)
    try:
        row = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='accounts'"
        ).fetchone()
        if not row or not row[0]:
            return 0
        return int(connection.execute("SELECT count(*) FROM accounts").fetchone()[0])
    finally:
        connection.close()


def backup_before_bootstrap(database_path=None, *, backup_directory=None) -> Path | None:
    """Copy an existing database next to it before any bootstrap write."""
    source = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    if str(source) == ":memory:" or not source.exists() or source.stat().st_size == 0:
        return None
    directory = Path(backup_directory) if backup_directory is not None else source.parent / "backups"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return backup_database(directory / f"{source.stem}-pre-bootstrap-{stamp}{source.suffix}", source)


def main(argv=None) -> int:
    """One-off operator command: `python -m app.services.initial_account_bootstrap`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create the initial ADMIN/HR/STUDENT_SUPPORT accounts, their roles and "
                    "permissions, and the T6 liveness defaults. Existing rows are left untouched.")
    parser.add_argument("--database", default=None, help="SQLite file (default: data/attendance.db)")
    parser.add_argument("--backup-directory", default=None, help="Where to write the pre-write backup")
    parser.add_argument("--sync-permissions-only", action="store_true",
                        help="Only add permissions/grants introduced after bootstrap; "
                             "never touch accounts or passwords")
    arguments = parser.parse_args(argv)

    database_path = Path(arguments.database) if arguments.database else DEFAULT_DATABASE_PATH
    if arguments.sync_permissions_only:
        backup = backup_before_bootstrap(database_path, backup_directory=arguments.backup_directory)
        if backup is not None:
            print(f"Đã sao lưu cơ sở dữ liệu trước khi ghi: {backup}")
        changes = sync_role_permissions(database_path)
        print(f"Quyền được thêm: {changes['permissions'] or 'không có'}")
        print(f"Cấp quyền cho vai trò: {changes['grants'] or 'không có'}")
        return 0
    initialize_database(database_path)
    passwords, generated = resolve_initial_passwords()
    backup = backup_before_bootstrap(database_path, backup_directory=arguments.backup_directory)
    if backup is not None:
        print(f"Đã sao lưu cơ sở dữ liệu trước khi ghi: {backup}")
    result = bootstrap_initial_accounts(passwords, database_path)

    created = [code for code in ACCOUNT_USERNAMES if result[code]["created"]]
    if not created:
        print("Không có tài khoản nào được tạo; mọi tài khoản khởi tạo đã tồn tại và được giữ nguyên.")
        return 0
    print("\nĐã tạo tài khoản mới. Ghi lại các thông tin dưới đây ngay; chúng không được lưu ở dạng rõ "
          "và không được ghi vào log:")
    for code in created:
        username = ACCOUNT_USERNAMES[code]
        if code in generated:
            print(f"  {code:<16} username={username:<16} password={passwords[code]}")
        else:
            print(f"  {code:<16} username={username:<16} password=<đã cung cấp qua "
                  f"{PASSWORD_ENVIRONMENT_VARIABLES[code]}>")
    print("\nHãy đổi mật khẩu sau lần đăng nhập đầu tiên.")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
