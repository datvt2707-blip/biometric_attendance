"""Data representations for people, employees, students, and departments."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Person:
    person_id: Optional[int]
    full_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_active: bool = True


@dataclass
class Employee:
    employee_id: Optional[int]
    person_id: int
    employee_code: str
    department_id: Optional[int] = None
    job_title: Optional[str] = None
    hire_date: Optional[str] = None
    address: Optional[str] = None
    employment_status: str = "active"


@dataclass
class Student:
    student_id: Optional[int]
    person_id: int
    student_code: str
    guardian_name: Optional[str] = None
    guardian_phone: Optional[str] = None
    student_status: str = "active"


@dataclass
class Department:
    department_id: Optional[int]
    name: str
    is_active: bool = True
