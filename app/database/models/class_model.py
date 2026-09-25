"""Class and student enrollment data representations."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Class:
    class_id: Optional[int]
    class_name: str
    academic_year: str
    teacher_name: Optional[str] = None
    room: Optional[str] = None
    schedule_text: Optional[str] = None
    time_text: Optional[str] = None
    capacity: Optional[int] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None
    class_status: str = "active"


@dataclass
class Enrollment:
    enrollment_id: Optional[int]
    student_id: int
    class_id: int
    start_date: str
    end_date: Optional[str] = None
    enrollment_status: str = "active"
    created_at: Optional[str] = None
