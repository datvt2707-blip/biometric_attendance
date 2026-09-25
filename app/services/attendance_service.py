"""Serialized face-authorized check-in/check-out workflows."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import threading

from app.database.database import connect, transaction
from app.database.models.attendance import EmployeeAttendance, StudentAttendance
from app.database.repositories.attendance_repository import AttendanceRepository
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class AttendanceResult:
    status: str
    message: str
    person_id: int | None = None
    person_type: str | None = None
    record_id: int | None = None
    recorded_at: str | None = None


class AttendanceService:
    _locks_guard = threading.Lock()
    _locks = {}

    def __init__(self, database_path=None):
        self.database_path = database_path
        key = str(database_path or "<default>")
        with self._locks_guard:
            self._lock = self._locks.setdefault(key, threading.RLock())

    @staticmethod
    def _value(match, key, default=None):
        return match.get(key, default) if isinstance(match, dict) else getattr(match, key, default)

    def _validated_person(self, match):
        if self._value(match, "status") != "matched":
            return None, AttendanceResult("rejected", "Cần kết quả nhận diện thành công, không mơ hồ.")
        person_id, kind = self._value(match, "person_id"), self._value(match, "person_type")
        if not isinstance(person_id, int) or person_id <= 0 or kind not in ("employee", "student"):
            return None, AttendanceResult("rejected", "Thông tin danh tính nhận diện không hợp lệ.")
        return (person_id, kind), None

    def check_in(self, match, *, liveness_challenge=None, track_id=None):
        identity, rejection = self._validated_person(match)
        if rejection: return rejection
        person_id, kind = identity
        from app.services.authorization_service import require_permission
        require_permission("employee.attendance.record" if kind == "employee" else "student.attendance.record")
        if not self._verification_passed(match, liveness_challenge, track_id):
            return AttendanceResult("rejected", "Cần hoàn tất xác minh MediaPipe trước khi ghi attendance.", person_id, kind)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        # Persist UTC instants, but resolve the calendar attendance day in the
        # workstation's local timezone, matching the UI and enrollment dates.
        timestamp, work_date = now.strftime("%Y-%m-%dT%H:%M:%SZ"), now.astimezone().date().isoformat()
        with self._lock:
            connection = connect(self.database_path)
            try:
                users, attendance, classes = UserRepository(connection), AttendanceRepository(connection), ClassRepository(connection)
                with transaction(connection, immediate=True):
                    person = users.get_person(person_id)
                    if person is None or not bool(person["is_active"]):
                        raise _AttendanceRejected("Hồ sơ không tồn tại hoặc đã ngừng hoạt động.")
                    if kind == "employee":
                        profiles = [row for row in users.list_employees(status="active") if int(row["person_id"]) == person_id]
                        if not profiles: raise _AttendanceRejected("Nhân viên không đủ điều kiện chấm công.")
                        existing = attendance.list_employee_attendance(employee_id=profiles[0]["employee_id"], work_date=work_date)
                        if existing:
                            raise _AttendanceRejected("Đã có bản ghi chấm công hôm nay; không tạo phiên trùng.")
                        record_id = attendance.create_employee_attendance(EmployeeAttendance(
                            attendance_id=None, employee_id=int(profiles[0]["employee_id"]),
                            work_date=work_date, check_in_at=timestamp, check_in_method="face", status="present",
                        ))
                    else:
                        profiles = [row for row in users.list_students(status="active") if int(row["person_id"]) == person_id]
                        if not profiles: raise _AttendanceRejected("Học viên không đủ điều kiện điểm danh.")
                        enrollments = [row for row in classes.list_enrollments(student_id=profiles[0]["student_id"], active_only=True)
                                       if row["start_date"] <= work_date and (row["end_date"] is None or row["end_date"] >= work_date)
                                       and (classes.get_class(row["class_id"]) or {"class_status": None})["class_status"] == "active"]
                        if len(enrollments) != 1:
                            reason = "Học viên chưa có lớp đang học." if not enrollments else "Học viên có nhiều lớp đang học; cần chọn lớp trước khi điểm danh."
                            raise _AttendanceRejected(reason)
                        enrollment = enrollments[0]
                        previous = attendance.list_student_attendance(
                            class_id=enrollment["class_id"], student_id=profiles[0]["student_id"], attendance_date=work_date,
                        )
                        if previous: raise _AttendanceRejected("Học viên đã được điểm danh trong buổi này.")
                        record_id = attendance.create_student_attendance(StudentAttendance(
                            student_attendance_id=None, student_id=int(profiles[0]["student_id"]),
                            class_id=int(enrollment["class_id"]), enrollment_id=int(enrollment["enrollment_id"]),
                            attendance_date=work_date, status="present", check_in_at=timestamp, method="face",
                        ))
                return AttendanceResult("success", "Đã ghi nhận check-in bằng nhận diện khuôn mặt.", person_id, kind, record_id, timestamp)
            except _AttendanceRejected as exc:
                return AttendanceResult("rejected", str(exc), person_id, kind)
            finally: connection.close()

    def check_out(self, match, *, liveness_challenge=None, track_id=None):
        identity, rejection = self._validated_person(match)
        if rejection: return rejection
        person_id, kind = identity
        if kind != "employee":
            return AttendanceResult("rejected", "Schema điểm danh học viên không có thao tác check-out.", person_id, kind)
        from app.services.authorization_service import require_permission
        require_permission("employee.attendance.record")
        if not self._verification_passed(match, liveness_challenge, track_id):
            return AttendanceResult("rejected", "Cần hoàn tất xác minh MediaPipe trước khi ghi attendance.", person_id, kind)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        timestamp, work_date = now.strftime("%Y-%m-%dT%H:%M:%SZ"), now.astimezone().date().isoformat()
        with self._lock:
            connection = connect(self.database_path)
            try:
                users, attendance = UserRepository(connection), AttendanceRepository(connection)
                with transaction(connection, immediate=True):
                    person = users.get_person(person_id)
                    profiles = [row for row in users.list_employees(status="active") if int(row["person_id"]) == person_id]
                    if person is None or not bool(person["is_active"]) or not profiles:
                        raise _AttendanceRejected("Nhân viên không tồn tại hoặc không đủ điều kiện.")
                    open_records = [row for row in attendance.list_employee_attendance(
                        employee_id=profiles[0]["employee_id"], work_date=work_date
                    ) if row["check_in_at"] is not None and row["check_out_at"] is None]
                    if len(open_records) != 1:
                        reason = "Không có phiên check-in đang mở hôm nay." if not open_records else "Có nhiều phiên mở; cần đối soát trước khi check-out."
                        raise _AttendanceRejected(reason)
                    record = open_records[0]
                    if not attendance.update_employee_attendance(record["attendance_id"], {
                        "check_out_at": timestamp, "check_out_method": "face"
                    }):
                        raise _AttendanceRejected("Không thể cập nhật phiên chấm công.")
                return AttendanceResult("success", "Đã ghi nhận check-out bằng nhận diện khuôn mặt.", person_id, kind, int(record["attendance_id"]), timestamp)
            except _AttendanceRejected as exc:
                return AttendanceResult("rejected", str(exc), person_id, kind)
            finally: connection.close()

    @staticmethod
    def _verification_passed(match, challenge, track_id):
        from app.services.t6_mode import development_attendance_without_liveness_enabled
        if development_attendance_without_liveness_enabled():
            return True
        from app.biometric.liveness.active_liveness import ActiveLivenessChallenge
        return (isinstance(challenge, ActiveLivenessChallenge)
                and track_id is not None
                and challenge.consume(match, track_id=track_id))

    def list_history(self, kind, *, from_date=None, to_date=None, query="", status=None, class_id=None, limit=200, offset=0):
        if kind not in ("staff", "student"):
            raise ValueError("kind phải là staff hoặc student.")
        from app.services.authorization_service import require_permission
        require_permission("employee.attendance.read" if kind == "staff" else "student.attendance.read")
        parsed = {}
        for field, value in (("from_date", from_date), ("to_date", to_date)):
            if value is None:
                continue
            try:
                text = str(value)
                day = date.fromisoformat(text)
                if day.isoformat() != text:
                    raise ValueError
                parsed[field] = text
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} phải có định dạng YYYY-MM-DD và là ngày hợp lệ.") from exc
        if parsed.get("from_date") and parsed.get("to_date") and parsed["from_date"] > parsed["to_date"]:
            raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        valid_statuses = {"present", "late", "absent", "excused"}
        if kind == "staff":
            valid_statuses.add("incomplete")
        if status is not None and status not in valid_statuses:
            raise ValueError("Trạng thái attendance không hợp lệ.")
        try:
            limit, offset = int(limit), int(offset)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit và offset phải là số nguyên.") from exc
        if limit < 1 or offset < 0:
            raise ValueError("limit phải dương và offset không được âm.")
        connection = connect(self.database_path)
        try:
            return AttendanceRepository(connection).search_history(
                kind, from_date=parsed.get("from_date"), to_date=parsed.get("to_date"), query=query,
                status=status, class_id=class_id, limit=limit, offset=offset,
            )
        finally: connection.close()

    def count_history(self, kind, *, from_date=None, to_date=None, query="", status=None, class_id=None):
        """Return the exact total for the same validated filter set as list_history."""
        if kind not in ("staff", "student"):
            raise ValueError("kind phải là staff hoặc student.")
        from app.services.authorization_service import require_permission
        require_permission("employee.attendance.read" if kind == "staff" else "student.attendance.read")
        parsed = {}
        for field, value in (("from_date", from_date), ("to_date", to_date)):
            if value is None:
                continue
            try:
                text = str(value)
                day = date.fromisoformat(text)
                if day.isoformat() != text:
                    raise ValueError
                parsed[field] = text
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} phải có định dạng YYYY-MM-DD và là ngày hợp lệ.") from exc
        if parsed.get("from_date") and parsed.get("to_date") and parsed["from_date"] > parsed["to_date"]:
            raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        valid_statuses = {"present", "late", "absent", "excused"}
        if kind == "staff":
            valid_statuses.add("incomplete")
        if status is not None and status not in valid_statuses:
            raise ValueError("Trạng thái attendance không hợp lệ.")
        connection = connect(self.database_path)
        try:
            return AttendanceRepository(connection).count_history(
                kind, from_date=parsed.get("from_date"), to_date=parsed.get("to_date"),
                query=query, status=status, class_id=class_id,
            )
        finally:
            connection.close()


class _AttendanceRejected(Exception): pass
