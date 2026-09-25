"""Read account directory and perform explicit status changes."""
from app.database.database import connect, transaction
from app.database.repositories.account_repository import AccountRepository


class AccountService:
    def __init__(self, database_path=None): self.database_path = database_path

    def directory(self):
        from app.services.authorization_service import require_permission
        require_permission("account.read")
        connection = connect(self.database_path)
        try:
            repo = AccountRepository(connection)
            accounts = [dict(row) for row in repo.list_account_directory()]
            roles = [dict(row) for row in repo.list_roles()]
            permissions = [dict(row) for row in repo.list_permissions()]
            assignments = [tuple(row) for row in repo.list_role_permission_directory()]
            return accounts, roles, permissions, assignments
        finally:
            connection.close()

    def assignable_roles(self):
        """Roles stored in the database; the UI never hardcodes role names."""
        from app.services.authorization_service import require_permission
        require_permission("account.read")
        connection = connect(self.database_path)
        try:
            return [dict(row) for row in AccountRepository(connection).list_roles()]
        finally:
            connection.close()

    def linkable_people(self):
        """Active people who do not already own an account."""
        from app.services.authorization_service import require_permission
        require_permission("account.read")
        connection = connect(self.database_path)
        try:
            rows = connection.execute(
                "SELECT person_id, full_name FROM people WHERE is_active = 1 "
                "AND person_id NOT IN (SELECT person_id FROM accounts WHERE person_id IS NOT NULL) "
                "ORDER BY full_name COLLATE NOCASE"
            ).fetchall()
            return [{"person_id": int(row["person_id"]),
                     "display": f"{row['full_name']} (#{int(row['person_id'])})"} for row in rows]
        finally:
            connection.close()

    def create_account(self, username, role_code, *, person_id=None, password=None):
        """Create one active account with a generated password returned exactly once."""
        from app.services.authentication_service import hash_password
        from app.services.authorization_service import require_permission
        from app.services.initial_account_bootstrap import generate_initial_password
        require_permission("account.manage")
        username = str(username or "").strip()
        if not 3 <= len(username) <= 64 or not username.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Tên đăng nhập phải dài 3-64 ký tự, chỉ gồm chữ, số, dấu chấm hoặc gạch dưới.")
        if not isinstance(role_code, str) or not role_code.strip():
            raise ValueError("Phải chọn một vai trò đã có trong cơ sở dữ liệu.")
        password = password or generate_initial_password()
        encoded = hash_password(password)
        connection = connect(self.database_path)
        try:
            repo = AccountRepository(connection)
            with transaction(connection, immediate=True):
                if repo.get_account_by_username(username) is not None:
                    raise ValueError("Tên đăng nhập đã tồn tại.")
                role = next((row for row in repo.list_roles() if row["role_code"] == role_code), None)
                if role is None:
                    raise ValueError("Vai trò không tồn tại trong cơ sở dữ liệu.")
                if person_id is not None:
                    person = connection.execute(
                        "SELECT is_active FROM people WHERE person_id = ?", (int(person_id),)).fetchone()
                    if person is None or not bool(person["is_active"]):
                        raise ValueError("Hồ sơ được liên kết không tồn tại hoặc đã ngừng hoạt động.")
                    if connection.execute("SELECT 1 FROM accounts WHERE person_id = ?", (int(person_id),)).fetchone():
                        raise ValueError("Hồ sơ này đã có tài khoản.")
                account_id = int(connection.execute(
                    "INSERT INTO accounts(person_id,username,password_hash,password_scheme,account_status) "
                    "VALUES(?,?,?,?,?)",
                    (int(person_id) if person_id is not None else None, username, encoded, "scrypt", "active"),
                ).lastrowid)
                repo.assign_role(account_id, int(role["role_id"]))
            return {"account_id": account_id, "username": username,
                    "role_code": role_code, "password": password}
        finally:
            connection.close()

    def set_status(self, account_id, status):
        from app.services.authorization_service import require_permission
        require_permission("account.manage")
        if status not in ("active", "locked", "disabled"):
            raise ValueError("Trạng thái tài khoản không hợp lệ.")
        connection = connect(self.database_path)
        try:
            with transaction(connection, immediate=True):
                if not AccountRepository(connection).update_account(account_id, {"account_status": status}):
                    raise ValueError("Không tìm thấy tài khoản cần cập nhật.")
            return True
        finally:
            connection.close()
