"""Employee time-attendance and student attendance data representations."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmployeeAttendance:
    attendance_id: Optional[int]
    employee_id: int
    work_date: str
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    check_in_method: Optional[str] = None
    check_out_method: Optional[str] = None
    status: str = "present"
    created_at: Optional[str] = None


@dataclass
class StudentAttendance:
    student_attendance_id: Optional[int]
    student_id: int
    class_id: int
    attendance_date: str
    status: str
    enrollment_id: Optional[int] = None
    check_in_at: Optional[str] = None
    method: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[str] = None
