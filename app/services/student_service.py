"""Validated student-directory use cases."""
from datetime import date
from app.database.database import connect, transaction
from app.database.models.user import Person, Student
from app.database.models.class_model import Enrollment
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.user_repository import UserRepository
from app.services.authorization_service import require_permission


class StudentService:
    def __init__(self, database_path=None): self.database_path = database_path

    def search_directory(self, query="", status=None, *, class_id=None, limit=5, offset=0):
        require_permission("student.read")
        connection = connect(self.database_path)
        try:
            return UserRepository(connection).search_student_directory(
                query, status, class_id=class_id, limit=limit, offset=offset
            )
        finally:
            connection.close()

    def get_by_code(self, code):
        require_permission("student.read")
        connection = connect(self.database_path)
        try:
            repo = UserRepository(connection)
            student = repo.get_student_by_code(code)
            if student is None: return None
            classes = ClassRepository(connection)
            active = classes.list_enrollments(student_id=student["student_id"], active_only=True)
            active = sorted(active, key=lambda row: row["start_date"], reverse=True)
            return {"student": dict(student), "person": dict(repo.get_person(student["person_id"])),
                    "class_id": int(active[0]["class_id"]) if active else None}
        finally: connection.close()

    def classes(self):
        require_permission("class.read")
        connection = connect(self.database_path)
        try: return [dict(row) for row in ClassRepository(connection).list_classes(status="active")]
        finally: connection.close()

    def save(self, person_data, student_data, *, student_id=None, class_id=None):
        require_permission("student.write")
        person_data, student_data = dict(person_data), dict(student_data)
        code = (student_data.get("student_code") or "").strip()
        name = (person_data.get("full_name") or "").strip()
        if not code or not name: raise ValueError("Mã học viên và họ tên là bắt buộc.")
        connection = connect(self.database_path)
        try:
            users, classes = UserRepository(connection), ClassRepository(connection)
            with transaction(connection, immediate=True):
                duplicate = users.get_student_by_code(code)
                if duplicate is not None and int(duplicate["student_id"]) != student_id:
                    raise ValueError(f"Mã học viên {code} đã tồn tại.")
                if class_id is not None:
                    class_row = classes.get_class(class_id)
                    if class_row is None or class_row["class_status"] != "active":
                        raise ValueError("Lớp đã chọn không tồn tại hoặc không hoạt động.")
                if student_id is None:
                    person_id, new_id = users.create_student_with_person(
                        Person(person_id=None, **{**person_data, "full_name": name}),
                        Student(student_id=None, person_id=0, **student_data),
                    )
                    student_id = new_id
                else:
                    current = users.get_student(student_id)
                    if current is None: raise ValueError("Không tìm thấy học viên cần cập nhật.")
                    person_id = int(current["person_id"])
                    person_changes = {k: v for k, v in person_data.items()
                                      if k in {"full_name", "date_of_birth", "gender", "phone", "email", "is_active"}}
                    person_changes["full_name"] = name
                    users.update_person(person_id, person_changes)
                    users.update_student(student_id, {k: v for k, v in student_data.items()
                        if k in {"student_code", "guardian_name", "guardian_phone", "student_status"}})
                if class_id is not None:
                    active = classes.list_enrollments(student_id=student_id, active_only=True)
                    if any(int(r["class_id"]) != int(class_id) for r in active):
                        raise ValueError("Học viên đang có lớp khác còn hiệu lực; cần xác nhận quy tắc chuyển lớp trước khi thay đổi.")
                    if not active:
                        classes.create_enrollment(Enrollment(
                            enrollment_id=None, student_id=int(student_id), class_id=int(class_id),
                            start_date=date.today().isoformat(),
                        ))
                return int(student_id)
        finally: connection.close()

    def deactivate(self, student_id):
        require_permission("student.deactivate")
        connection = connect(self.database_path)
        try:
            users, classes = UserRepository(connection), ClassRepository(connection)
            with transaction(connection, immediate=True):
                if not users.update_student(student_id, {"student_status": "inactive"}):
                    raise ValueError("Không tìm thấy học viên cần ngừng hoạt động.")
                for row in classes.list_enrollments(student_id=student_id, active_only=True):
                    classes.update_enrollment(row["enrollment_id"], {"enrollment_status": "withdrawn", "end_date": date.today().isoformat()})
            return True
        finally: connection.close()
