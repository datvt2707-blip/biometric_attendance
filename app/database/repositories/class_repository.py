"""CRUD and lookups for classes and student enrollments."""
from dataclasses import asdict
from .base import BaseRepository


class ClassRepository(BaseRepository):
    def create_class(self, class_record):
        values = asdict(class_record); values.pop("class_id", None)
        return self._insert("classes", values)
    def get_class(self, class_id): return self._get("classes", "class_id", class_id)
    def list_classes(self, status=None):
        return self._list("classes", "class_status = ?" if status else "1 = 1", (status,) if status else (), "academic_year DESC, class_name")
    def update_class(self, class_id, changes):
        return self._update("classes", "class_id", class_id, changes,
            {"class_name", "academic_year", "teacher_name", "room", "schedule_text", "time_text", "capacity", "start_date", "notes", "class_status"})
    def delete_class(self, class_id): return self._delete("classes", "class_id", class_id)
    def create_enrollment(self, enrollment):
        values = asdict(enrollment); values.pop("enrollment_id", None); values.pop("created_at", None)
        return self._insert("enrollments", values)
    def get_enrollment(self, enrollment_id): return self._get("enrollments", "enrollment_id", enrollment_id)
    def list_enrollments(self, *, class_id=None, student_id=None, active_only=False):
        clauses, params = [], []
        if class_id is not None: clauses.append("class_id = ?"); params.append(class_id)
        if student_id is not None: clauses.append("student_id = ?"); params.append(student_id)
        if active_only: clauses.append("enrollment_status = 'active'")
        return self._list("enrollments", " AND ".join(clauses) or "1 = 1", params, "start_date DESC")
    def update_enrollment(self, enrollment_id, changes):
        return self._update("enrollments", "enrollment_id", enrollment_id, changes,
            {"student_id", "class_id", "start_date", "end_date", "enrollment_status"})
