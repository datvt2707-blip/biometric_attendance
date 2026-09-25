"""Employee and student leave request data representations."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmployeeLeaveRequest:
    leave_request_id: Optional[int]
    employee_id: int
    leave_type: str
    start_date: str
    end_date: str
    reason: str
    handover_person: Optional[str] = None
    attachment_path: Optional[str] = None
    status: str = "pending"
    reviewed_by_account_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class StudentLeaveRequest:
    student_leave_request_id: Optional[int]
    student_id: int
    leave_date: str
    submitted_by_type: str
    reason: str
    class_id: Optional[int] = None
    session_count: Optional[float] = None
    contact_phone: Optional[str] = None
    attachment_path: Optional[str] = None
    status: str = "pending"
    reviewed_by_account_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    review_note: Optional[str] = None
    created_at: Optional[str] = None
