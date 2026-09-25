"""Validated employee-directory use cases."""
from app.database.database import connect, transaction
from app.database.models.user import Employee, Person
from app.database.repositories.user_repository import UserRepository
from app.services.authorization_service import require_permission


class EmployeeService:
    def __init__(self, database_path=None):
        self.database_path = database_path

    def search_directory(self, query="", status=None, *, department_id=None, limit=5, offset=0):
        require_permission("employee.read")
        connection = connect(self.database_path)
        try:
            rows, total = UserRepository(connection).search_employee_directory(
                query, status, department_id=department_id, limit=limit, offset=offset
            )
            return rows, total
        finally:
            connection.close()

    def get_by_code(self, code):
        require_permission("employee.read")
        connection = connect(self.database_path)
        try:
            repo = UserRepository(connection)
            employee = repo.get_employee_by_code(code)
            if employee is None:
                return None
            person = repo.get_person(employee["person_id"])
            return {"employee": dict(employee), "person": dict(person)}
        finally:
            connection.close()

    def departments(self, *, active_only=True):
        require_permission("employee.read")
        connection = connect(self.database_path)
        try:
            return [dict(row) for row in UserRepository(connection).list_departments(active_only)]
        finally:
            connection.close()

    def save(self, person_data, employee_data, *, employee_id=None):
        require_permission("employee.write")
        person_data, employee_data = dict(person_data), dict(employee_data)
        code = (employee_data.get("employee_code") or "").strip()
        name = (person_data.get("full_name") or "").strip()
        if not code or not name:
            raise ValueError("Mã nhân viên và họ tên là bắt buộc.")
        connection = connect(self.database_path)
        try:
            repo = UserRepository(connection)
            with transaction(connection, immediate=True):
                duplicate = repo.get_employee_by_code(code)
                if duplicate is not None and int(duplicate["employee_id"]) != employee_id:
                    raise ValueError(f"Mã nhân viên {code} đã tồn tại.")
                if employee_id is None:
                    person_id, created_id = repo.create_employee_with_person(
                        Person(person_id=None, **{**person_data, "full_name": name}),
                        Employee(employee_id=None, person_id=0, **employee_data),
                    )
                    return created_id
                current = repo.get_employee(employee_id)
                if current is None:
                    raise ValueError("Không tìm thấy nhân viên cần cập nhật.")
                person_changes = {k: v for k, v in person_data.items()
                                  if k in {"full_name", "date_of_birth", "gender", "phone", "email", "is_active"}}
                person_changes["full_name"] = name
                repo.update_person(current["person_id"], person_changes)
                allowed = {k: v for k, v in employee_data.items()
                           if k in {"employee_code", "department_id", "job_title", "hire_date", "address", "employment_status"}}
                repo.update_employee(employee_id, allowed)
                return int(employee_id)
        finally:
            connection.close()

    def deactivate(self, employee_id):
        require_permission("employee.deactivate")
        connection = connect(self.database_path)
        try:
            with transaction(connection, immediate=True):
                if not UserRepository(connection).update_employee(employee_id, {"employment_status": "inactive"}):
                    raise ValueError("Không tìm thấy nhân viên cần ngừng hoạt động.")
            return True
        finally:
            connection.close()
