"""Password authentication backed by account and access-control records."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import os
import sqlite3

from app.database.database import connect, transaction
from app.database.repositories.account_repository import AccountRepository


class AuthenticationError(ValueError):
    """Credentials are invalid or the account cannot authenticate."""


class AuthorizationConfigurationError(AuthenticationError):
    """Credentials are valid but no usable role/permission assignment exists."""


@dataclass(frozen=True)
class AuthenticatedIdentity:
    account_id: int
    username: str
    person_id: int | None
    full_name: str
    roles: tuple[dict, ...]
    permissions: tuple[dict, ...]


_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SCRYPT_SALT_BYTES = 16
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    """Create a versioned, salted scrypt hash supported by the current schema."""
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError("Mật khẩu phải có từ 12 đến 1024 ký tự.")
    salt = os.urandom(_SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N,
                            r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
                            maxmem=_SCRYPT_MAXMEM)
    enc = lambda value: base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return (f"$scrypt$v=1$n={_SCRYPT_N}$r={_SCRYPT_R}$p={_SCRYPT_P}$"
            f"{enc(salt)}${enc(digest)}")


def verify_password(password: str, encoded_hash: str, scheme: str) -> bool:
    """Verify only the self-describing scrypt format issued by this service."""
    if not isinstance(password, str) or scheme != "scrypt" or not isinstance(encoded_hash, str):
        return False
    parts = encoded_hash.split("$")
    if len(parts) != 8 or parts[0] != "" or parts[1] != "scrypt" or parts[2] != "v=1":
        return False
    if parts[3:] and parts[3:6] != [f"n={_SCRYPT_N}", f"r={_SCRYPT_R}", f"p={_SCRYPT_P}"]:
        return False
    decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    try:
        salt, expected = decode(parts[6]), decode(parts[7])
        if len(salt) != _SCRYPT_SALT_BYTES or len(expected) != _SCRYPT_DKLEN:
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N,
                                r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN,
                                maxmem=_SCRYPT_MAXMEM)
    except (ValueError, TypeError, UnicodeError, MemoryError, OSError):
        return False
    return hmac.compare_digest(actual, expected)


class AuthenticationService:
    """Verify credentials, then load roles and permissions from SQLite."""

    def __init__(self, database_path=None):
        self.database_path = database_path

    def login(self, username: str, password: str) -> AuthenticatedIdentity:
        if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
            raise AuthenticationError("Tên đăng nhập hoặc mật khẩu không chính xác.")
        connection = connect(self.database_path)
        try:
            repo = AccountRepository(connection)
            row = repo.get_account_by_username(username.strip())
            if row is None or row["account_status"] != "active" or not verify_password(
                    password, row["password_hash"], row["password_scheme"]):
                raise AuthenticationError("Tên đăng nhập hoặc mật khẩu không chính xác.")

            roles = tuple(dict(role) for role in repo.list_roles(int(row["account_id"])))
            permissions_by_code = {}
            for role in roles:
                for permission in repo.list_permissions(int(role["role_id"])):
                    item = dict(permission)
                    code = item.get("permission_code")
                    if not isinstance(code, str) or not code.strip():
                        raise AuthorizationConfigurationError("Dữ liệu quyền truy cập không hợp lệ.")
                    permissions_by_code[code] = item
            if not roles or not permissions_by_code:
                raise AuthorizationConfigurationError(
                    "Thông tin đăng nhập hợp lệ nhưng tài khoản chưa có vai trò và quyền được cấu hình.")

            with transaction(connection, immediate=True):
                changed = repo.update_account(int(row["account_id"]), {
                    "last_login_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                })
                if not changed:
                    raise sqlite3.DatabaseError("Không thể cập nhật thời điểm đăng nhập.")

            person = connection.execute("SELECT full_name FROM people WHERE person_id = ?",
                                        (row["person_id"],)).fetchone() if row["person_id"] else None
            return AuthenticatedIdentity(
                account_id=int(row["account_id"]), username=str(row["username"]),
                person_id=int(row["person_id"]) if row["person_id"] is not None else None,
                full_name=str(person["full_name"]) if person else str(row["username"]),
                roles=roles, permissions=tuple(permissions_by_code[key] for key in sorted(permissions_by_code)),
            )
        finally:
            connection.close()

    def change_password(self, username: str, current_password: str, new_password: str) -> None:
        """Change one account's password after verifying its existing credential."""
        if not isinstance(username, str) or not username.strip():
            raise AuthenticationError("Tài khoản hoặc mật khẩu hiện tại không chính xác.")
        new_hash = hash_password(new_password)
        connection = connect(self.database_path)
        try:
            repo = AccountRepository(connection)
            with transaction(connection, immediate=True):
                row = repo.get_account_by_username(username.strip())
                if (row is None or row["account_status"] != "active"
                        or not verify_password(current_password, row["password_hash"], row["password_scheme"])):
                    raise AuthenticationError("Tài khoản hoặc mật khẩu hiện tại không chính xác.")
                repo.update_account(int(row["account_id"]), {
                    "password_hash": new_hash,
                    "password_scheme": "scrypt",
                    "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                })
        finally:
            connection.close()
