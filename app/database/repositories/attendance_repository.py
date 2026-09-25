"""CRUD and date/class lookups for attendance records."""
from dataclasses import asdict
from .base import BaseRepository


class AttendanceRepository(BaseRepository):
    def count_history(self, kind, *, from_date=None, to_date=None, query="", status=None, class_id=None):
        query = (query or "").strip()
        if kind == "staff":
            clauses, params = [], []
            if from_date is not None: clauses.append("a.work_date >= ?"); params.append(from_date)
            if to_date is not None: clauses.append("a.work_date <= ?"); params.append(to_date)
            if status: clauses.append("a.status = ?"); params.append(status)
            if query:
                clauses.append("(e.employee_code LIKE ? OR p.full_name LIKE ?)")
                params.extend((f"%{query}%", f"%{query}%"))
            where = " AND ".join(clauses) or "1 = 1"
            sql = ("SELECT count(*) FROM employee_attendance a "
                   "JOIN employees e USING(employee_id) JOIN people p USING(person_id) "
                   f"WHERE {where}")
        elif kind == "student":
            clauses, params = [], []
            if from_date is not None: clauses.append("a.attendance_date >= ?"); params.append(from_date)
            if to_date is not None: clauses.append("a.attendance_date <= ?"); params.append(to_date)
            if status: clauses.append("a.status = ?"); params.append(status)
            if class_id is not None: clauses.append("a.class_id = ?"); params.append(int(class_id))
            if query:
                clauses.append("(s.student_code LIKE ? OR p.full_name LIKE ?)")
                params.extend((f"%{query}%", f"%{query}%"))
            where = " AND ".join(clauses) or "1 = 1"
            sql = ("SELECT count(*) FROM student_attendance a "
                   "JOIN students s USING(student_id) JOIN people p USING(person_id) "
                   f"WHERE {where}")
        else:
            raise ValueError("kind must be staff or student")
        return int(self.connection.execute(sql, params).fetchone()[0])

    def search_history(self, kind, *, from_date=None, to_date=None, query="", status=None, class_id=None, limit=200, offset=0):
        query = (query or "").strip()
        if kind == "staff":
            clauses, params = [], []
            if from_date is not None: clauses.append("a.work_date >= ?"); params.append(from_date)
            if to_date is not None: clauses.append("a.work_date <= ?"); params.append(to_date)
            if status: clauses.append("a.status = ?"); params.append(status)
            if query:
                clauses.append("(e.employee_code LIKE ? OR p.full_name LIKE ?)")
                params.extend((f"%{query}%", f"%{query}%"))
            where = " AND ".join(clauses) or "1 = 1"
            rows = self.connection.execute(
                "SELECT e.employee_code,p.full_name,COALESCE(d.name,'—'),a.work_date,"
                "a.check_in_at,a.check_out_at,a.status FROM employee_attendance a "
                "JOIN employees e USING(employee_id) JOIN people p USING(person_id) "
                "LEFT JOIN departments d USING(department_id) "
                f"WHERE {where} ORDER BY a.work_date DESC,a.check_in_at DESC,a.attendance_id DESC LIMIT ? OFFSET ?",
                (*params, max(1, int(limit)), max(0, int(offset))),
            ).fetchall()
        elif kind == "student":
            clauses, params = [], []
            if from_date is not None: clauses.append("a.attendance_date >= ?"); params.append(from_date)
            if to_date is not None: clauses.append("a.attendance_date <= ?"); params.append(to_date)
            if status: clauses.append("a.status = ?"); params.append(status)
            if class_id is not None: clauses.append("a.class_id = ?"); params.append(int(class_id))
            if query:
                clauses.append("(s.student_code LIKE ? OR p.full_name LIKE ?)")
                params.extend((f"%{query}%", f"%{query}%"))
            where = " AND ".join(clauses) or "1 = 1"
            rows = self.connection.execute(
                "SELECT s.student_code,p.full_name,c.class_name,a.attendance_date,"
                "a.check_in_at,NULL,a.status FROM student_attendance a "
                "JOIN students s USING(student_id) JOIN people p USING(person_id) "
                "JOIN classes c USING(class_id) "
                f"WHERE {where} ORDER BY a.attendance_date DESC,a.check_in_at DESC,a.student_attendance_id DESC LIMIT ? OFFSET ?",
                (*params, max(1, int(limit)), max(0, int(offset))),
            ).fetchall()
        else:
            raise ValueError("kind must be staff or student")
        return [tuple(row) for row in rows]

    def create_employee_attendance(self, record):
        values = asdict(record); values.pop("attendance_id", None); values.pop("created_at", None)
        return self._insert("employee_attendance", values)
    def get_employee_attendance(self, attendance_id): return self._get("employee_attendance", "attendance_id", attendance_id)
    def list_employee_attendance(self, *, employee_id=None, work_date=None, from_date=None, to_date=None):
        clauses, params = [], []
        for col, val in (("employee_id", employee_id), ("work_date", work_date)):
            if val is not None: clauses.append(f"{col} = ?"); params.append(val)
        if from_date is not None: clauses.append("work_date >= ?"); params.append(from_date)
        if to_date is not None: clauses.append("work_date <= ?"); params.append(to_date)
        return self._list("employee_attendance", " AND ".join(clauses) or "1 = 1", params, "work_date DESC, check_in_at DESC")
    def update_employee_attendance(self, attendance_id, changes):
        return self._update("employee_attendance", "attendance_id", attendance_id, changes,
            {"employee_id", "work_date", "check_in_at", "check_out_at", "check_in_method", "check_out_method", "status"})
    def delete_employee_attendance(self, attendance_id): return self._delete("employee_attendance", "attendance_id", attendance_id)

    def create_student_attendance(self, record):
        values = asdict(record); values.pop("student_attendance_id", None); values.pop("created_at", None)
        return self._insert("student_attendance", values)
    def get_student_attendance(self, record_id): return self._get("student_attendance", "student_attendance_id", record_id)
    def get_student_attendance_for_day(self, student_id, class_id, attendance_date):
        return self.connection.execute(
            "SELECT * FROM student_attendance WHERE student_id = ? AND class_id = ? AND attendance_date = ?",
            (student_id, class_id, attendance_date),
        ).fetchone()
    def list_student_attendance(self, *, class_id=None, student_id=None, attendance_date=None):
        clauses, params = [], []
        for col, val in (("class_id", class_id), ("student_id", student_id), ("attendance_date", attendance_date)):
            if val is not None: clauses.append(f"{col} = ?"); params.append(val)
        return self._list("student_attendance", " AND ".join(clauses) or "1 = 1", params, "attendance_date DESC, student_id")
    def update_student_attendance(self, record_id, changes):
        return self._update("student_attendance", "student_attendance_id", record_id, changes,
            {"student_id", "class_id", "enrollment_id", "attendance_date", "status", "check_in_at", "method", "note"})
    def delete_student_attendance(self, record_id): return self._delete("student_attendance", "student_attendance_id", record_id)
