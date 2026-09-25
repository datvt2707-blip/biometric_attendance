"""Data representations for accounts and access-control records."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Account:
    account_id: Optional[int]
    username: str
    password_hash: str
    password_scheme: str
    person_id: Optional[int] = None
    account_status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None


@dataclass
class Role:
    role_id: Optional[int]
    role_code: str
    role_name: str
    description: Optional[str] = None


@dataclass
class Permission:
    permission_id: Optional[int]
    permission_code: str
    permission_name: str
    description: Optional[str] = None
