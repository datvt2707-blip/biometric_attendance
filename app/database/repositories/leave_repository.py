"""CRUD and status filtering for employee and student leave requests."""
from dataclasses import asdict
from .base import BaseRepository


class LeaveRepository(BaseRepository):
    def create_employee_request(self, request):
        values = asdict(request); values.pop("leave_request_id", None); values.pop("created_at", None)
        return self._insert("employee_leave_requests", values)
    def get_employee_request(self, request_id): return self._get("employee_leave_requests", "leave_request_id", request_id)
    def list_employee_requests(self, *, employee_id=None, status=None):
        clauses, params = [], []
        if employee_id is not None: clauses.append("employee_id = ?"); params.append(employee_id)
        if status is not None: clauses.append("status = ?"); params.append(status)
        return self._list("employee_leave_requests", " AND ".join(clauses) or "1 = 1", params, "created_at DESC")
    def update_employee_request(self, request_id, changes):
        return self._update("employee_leave_requests", "leave_request_id", request_id, changes,
            {"employee_id", "leave_type", "start_date", "end_date", "handover_person", "attachment_path", "reason", "status", "reviewed_by_account_id", "reviewed_at", "review_note"})
    def delete_employee_request(self, request_id): return self._delete("employee_leave_requests", "leave_request_id", request_id)

    def create_student_request(self, request):
        values = asdict(request); values.pop("student_leave_request_id", None); values.pop("created_at", None)
        return self._insert("student_leave_requests", values)
    def get_student_request(self, request_id): return self._get("student_leave_requests", "student_leave_request_id", request_id)
    def list_student_requests(self, *, student_id=None, class_id=None, status=None):
        clauses, params = [], []
        for col, val in (("student_id", student_id), ("class_id", class_id), ("status", status)):
            if val is not None: clauses.append(f"{col} = ?"); params.append(val)
        return self._list("student_leave_requests", " AND ".join(clauses) or "1 = 1", params, "created_at DESC")
    def update_student_request(self, request_id, changes):
        return self._update("student_leave_requests", "student_leave_request_id", request_id, changes,
            {"student_id", "class_id", "leave_date", "session_count", "submitted_by_type", "contact_phone", "reason", "attachment_path", "status", "reviewed_by_account_id", "reviewed_at", "review_note"})
    def delete_student_request(self, request_id): return self._delete("student_leave_requests", "student_leave_request_id", request_id)
