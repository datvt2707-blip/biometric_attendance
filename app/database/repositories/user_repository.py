"""CRUD for people, employee/student profiles, and departments."""
from dataclasses import asdict
from .base import BaseRepository


class UserRepository(BaseRepository):
    def create_person(self, person):
        values = asdict(person); values.pop("person_id", None)
        values["is_active"] = int(values["is_active"])
        return self._insert("people", values)

    def get_person(self, person_id): return self._get("people", "person_id", person_id)
    def find_person_by_name(self, name):
        return self.connection.execute("SELECT * FROM people WHERE full_name LIKE ? ORDER BY full_name", (f"%{name}%",)).fetchall()
    def list_people(self, active_only=False):
        return self._list("people", "is_active = 1" if active_only else "1 = 1", order="full_name")
    def update_person(self, person_id, changes):
        if "is_active" in changes: changes["is_active"] = int(changes["is_active"])
        return self._update("people", "person_id", person_id, changes,
            {"full_name", "date_of_birth", "gender", "phone", "email", "updated_at", "is_active"})
    def delete_person(self, person_id): return self._delete("people", "person_id", person_id)

    def create_employee(self, employee):
        values = asdict(employee); values.pop("employee_id", None)
        return self._insert("employees", values)
    def get_employee(self, employee_id): return self._get("employees", "employee_id", employee_id)
    def get_employee_by_code(self, employee_code): return self._get("employees", "employee_code", employee_code)
    def list_employees(self, department_id=None, status=None):
        clauses, params = [], []
        if department_id is not None: clauses.append("department_id = ?"); params.append(department_id)
        if status is not None: clauses.append("employment_status = ?"); params.append(status)
        return self._list("employees", " AND ".join(clauses) or "1 = 1", params, "employee_code")
    def search_employee_directory(self, query="", status=None, *, department_id=None, limit=5, offset=0):
        """Return display rows and total count using the same filters."""
        query = (query or "").strip()
        clauses, params = [], []
        if query:
            clauses.append("(e.employee_code LIKE ? OR p.full_name LIKE ?)")
            params.extend((f"%{query}%", f"%{query}%"))
        if status:
            if isinstance(status, (tuple, list, set)):
                statuses = tuple(status)
                if statuses:
                    clauses.append("e.employment_status IN (" + ",".join("?" for _ in statuses) + ")")
                    params.extend(statuses)
            else:
                clauses.append("e.employment_status = ?")
                params.append(status)
        if department_id is not None:
            clauses.append("e.department_id = ?")
            params.append(int(department_id))
        where = " AND ".join(clauses) or "1 = 1"
        total = self.connection.execute(
            f"SELECT count(*) FROM employees e JOIN people p USING(person_id) WHERE {where}", params
        ).fetchone()[0]
        rows = self.connection.execute(
            "SELECT e.employee_code, p.full_name, COALESCE(d.name, '—') AS department_name, "
            "e.employment_status, EXISTS(SELECT 1 FROM face_embeddings f "
            "WHERE f.person_id=p.person_id AND f.is_active=1) AS face_enrolled "
            "FROM employees e JOIN people p USING(person_id) "
            "LEFT JOIN departments d USING(department_id) "
            f"WHERE {where} ORDER BY e.employee_code LIMIT ? OFFSET ?",
            (*params, max(1, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [tuple(row) for row in rows], int(total)

    def search_student_directory(self, query="", status=None, *, class_id=None, limit=5, offset=0):
        query = (query or "").strip()
        clauses, params = [], []
        if query:
            clauses.append("(s.student_code LIKE ? OR p.full_name LIKE ?)")
            params.extend((f"%{query}%", f"%{query}%"))
        if status:
            if isinstance(status, (tuple, list, set)):
                statuses = tuple(status)
                if statuses:
                    clauses.append("s.student_status IN (" + ",".join("?" for _ in statuses) + ")")
                    params.extend(statuses)
            else:
                clauses.append("s.student_status = ?")
                params.append(status)
        if class_id is not None:
            clauses.append("EXISTS(SELECT 1 FROM enrollments en WHERE en.student_id=s.student_id AND en.class_id=? AND en.enrollment_status='active')")
            params.append(int(class_id))
        where = " AND ".join(clauses) or "1 = 1"
        join = "students s JOIN people p USING(person_id)"
        total = self.connection.execute(f"SELECT count(*) FROM {join} WHERE {where}", params).fetchone()[0]
        rows = self.connection.execute(
            "SELECT s.student_code,p.full_name,COALESCE((SELECT c.class_name FROM enrollments en "
            "JOIN classes c USING(class_id) WHERE en.student_id=s.student_id AND en.enrollment_status='active' "
            "ORDER BY en.start_date DESC LIMIT 1),'—') AS class_name,s.student_status, "
            "EXISTS(SELECT 1 FROM face_embeddings f WHERE f.person_id=p.person_id AND f.is_active=1) AS face_enrolled "
            f"FROM {join} WHERE {where} ORDER BY s.student_code LIMIT ? OFFSET ?",
            (*params, max(1, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [tuple(row) for row in rows], int(total)
    def update_employee(self, employee_id, changes):
        return self._update("employees", "employee_id", employee_id, changes,
            {"person_id", "employee_code", "department_id", "job_title", "hire_date", "address", "employment_status"})
    def delete_employee(self, employee_id): return self._delete("employees", "employee_id", employee_id)

    def create_student(self, student):
        values = asdict(student); values.pop("student_id", None)
        return self._insert("students", values)
    def get_student(self, student_id): return self._get("students", "student_id", student_id)
    def get_student_by_code(self, student_code): return self._get("students", "student_code", student_code)
    def list_students(self, status=None):
        return self._list("students", "student_status = ?" if status else "1 = 1", (status,) if status else (), "student_code")
    def update_student(self, student_id, changes):
        return self._update("students", "student_id", student_id, changes,
            {"person_id", "student_code", "guardian_name", "guardian_phone", "student_status"})
    def delete_student(self, student_id): return self._delete("students", "student_id", student_id)

    def create_department(self, name): return self._insert("departments", {"name": name})
    def list_departments(self, active_only=True):
        return self._list("departments", "is_active = 1" if active_only else "1 = 1", order="name")
    def update_department(self, department_id, changes):
        if "is_active" in changes: changes["is_active"] = int(changes["is_active"])
        return self._update("departments", "department_id", department_id, changes, {"name", "is_active"})

    def create_employee_with_person(self, person, employee):
        """Atomically insert a person and its employee profile."""
        from app.database.database import transaction
        with transaction(self.connection):
            person_id = self.create_person(person)
            values = asdict(employee); values.pop("employee_id", None); values["person_id"] = person_id
            return person_id, self._insert("employees", values)

    def create_student_with_person(self, person, student):
        """Atomically insert a person and its student profile."""
        from app.database.database import transaction
        with transaction(self.connection):
            person_id = self.create_person(person)
            values = asdict(student); values.pop("student_id", None); values["person_id"] = person_id
            return person_id, self._insert("students", values)
