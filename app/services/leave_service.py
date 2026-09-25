"""Validated leave-request creation and filtering."""
from datetime import date, datetime, timezone
import math
from app.database.database import connect, transaction
from app.database.models.leave import EmployeeLeaveRequest, StudentLeaveRequest
from app.database.repositories.leave_repository import LeaveRepository
from app.database.repositories.user_repository import UserRepository
from app.database.repositories.class_repository import ClassRepository

class LeaveService:
    def __init__(self, database_path=None): self.database_path = database_path

    @staticmethod
    def _date(value, field):
        try:
            text = str(value)
            parsed = date.fromisoformat(text)
            if parsed.isoformat() != text:
                raise ValueError
            return parsed
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} phải có định dạng YYYY-MM-DD và là ngày hợp lệ.") from exc

    def list_requests(self, kind, *, status=None, query=""):
        from app.services.authorization_service import require_permission
        require_permission("employee.leave.read" if kind == "staff" else "student.leave.read")
        if kind not in ("staff", "student"):
            raise ValueError("kind phải là staff hoặc student.")
        if status is not None and status not in ("pending", "approved", "rejected"):
            raise ValueError("Trạng thái đơn nghỉ không hợp lệ.")
        connection = connect(self.database_path)
        try:
            leaves, users, classes = LeaveRepository(connection), UserRepository(connection), ClassRepository(connection)
            found=[]
            records = (leaves.list_employee_requests(status=status) if kind == "staff"
                       else leaves.list_student_requests(status=status))
            for record in records:
                record = dict(record)
                profile_id = record["employee_id"] if kind == "staff" else record["student_id"]
                profile = users.get_employee(profile_id) if kind == "staff" else users.get_student(profile_id)
                person = users.get_person(profile["person_id"]) if profile else None
                if person is None: continue
                code = profile["employee_code"] if kind == "staff" else profile["student_code"]
                cls = classes.get_class(record["class_id"]) if kind == "student" and record.get("class_id") else None
                name = person["full_name"]
                if query and query.casefold() not in (code + " " + name).casefold(): continue
                if kind == "staff":
                    found.append((record["leave_request_id"], code, name, record["leave_type"], record["start_date"], record["end_date"], record["reason"], record["status"]))
                else:
                    found.append((record["student_leave_request_id"], code, name, cls["class_name"] if cls else "?", record["leave_date"], record["submitted_by_type"], record["reason"], record["status"]))
            return found
        finally: connection.close()

    def create_employee_request(self, employee_id, values):
        from app.services.authorization_service import require_permission
        require_permission("employee.leave.submit")
        return self._create("staff", employee_id, values)

    def create_student_request(self, student_id, values):
        from app.services.authorization_service import require_permission
        require_permission("student.leave.submit")
        return self._create("student", student_id, values)

    def _create(self, kind, profile_id, values):
        values = dict(values); reason = str(values.get("reason") or "").strip()
        if not reason: raise ValueError("Lý do nghỉ là bắt buộc.")
        if kind not in ("staff", "student"):
            raise ValueError("kind phải là staff hoặc student.")
        connection = connect(self.database_path)
        try:
            users, repo = UserRepository(connection), LeaveRepository(connection)
            with transaction(connection, immediate=True):
                profile = users.get_employee(profile_id) if kind == "staff" else users.get_student(profile_id)
                if profile is None: raise ValueError("Không tìm thấy hồ sơ người nộp đơn.")
                person = users.get_person(profile["person_id"])
                if person is None or not bool(person["is_active"]):
                    raise ValueError("Hồ sơ cá nhân không hoạt động.")
                if kind == "staff":
                    start, end = values.get("start_date"), values.get("end_date")
                    start_day, end_day = self._date(start, "Ngày bắt đầu"), self._date(end, "Ngày kết thúc")
                    if end_day < start_day: raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi.")
                    leave_type = str(values.get("leave_type") or "").strip()
                    handover = str(values.get("handover_person") or "").strip() or None
                    if not leave_type: raise ValueError("Loại nghỉ là bắt buộc.")
                    if profile["employment_status"] != "active":
                        raise ValueError("Chỉ nhân viên đang hoạt động mới có thể gửi đơn.")
                    duplicate = next((row for row in repo.list_employee_requests(employee_id=profile_id, status="pending")
                        if row["leave_type"] == leave_type and row["start_date"] == start_day.isoformat()
                        and row["end_date"] == end_day.isoformat() and row["reason"] == reason
                        and row["handover_person"] == handover), None)
                    if duplicate:
                        return int(duplicate["leave_request_id"])
                    return repo.create_employee_request(EmployeeLeaveRequest(
                        leave_request_id=None, employee_id=int(profile_id), leave_type=values["leave_type"],
                        start_date=start_day.isoformat(), end_date=end_day.isoformat(), reason=reason,
                        handover_person=handover,
                        attachment_path=values.get("attachment_path") or None,
                    ))
                leave_date = values.get("leave_date")
                leave_day = self._date(leave_date, "Ngày nghỉ")
                if profile["student_status"] != "active":
                    raise ValueError("Chỉ học viên đang hoạt động mới có thể gửi đơn.")
                submitter = values.get("submitted_by_type")
                if submitter not in ("guardian", "student"):
                    raise ValueError("Người nộp đơn phải là guardian hoặc student.")
                session_count = values.get("session_count")
                if session_count is not None:
                    try: session_count = float(session_count)
                    except (TypeError, ValueError) as exc: raise ValueError("Số buổi nghỉ phải là số dương.") from exc
                    if not math.isfinite(session_count) or session_count <= 0:
                        raise ValueError("Số buổi nghỉ phải là số dương.")
                class_id = values.get("class_id")
                if class_id is not None:
                    try: class_id = int(class_id)
                    except (TypeError, ValueError) as exc: raise ValueError("Lớp được chọn không hợp lệ.") from exc
                    if class_id <= 0: raise ValueError("Lớp được chọn không hợp lệ.")
                if class_id is not None and ClassRepository(connection).get_class(class_id) is None:
                    raise ValueError("Lớp được chọn không tồn tại.")
                contact_phone = str(values.get("contact_phone") or "").strip() or None
                duplicate = next((row for row in repo.list_student_requests(student_id=profile_id, status="pending")
                    if row["class_id"] == class_id and row["leave_date"] == leave_day.isoformat()
                    and row["session_count"] == session_count and row["submitted_by_type"] == submitter
                    and row["contact_phone"] == contact_phone and row["reason"] == reason), None)
                if duplicate:
                    return int(duplicate["student_leave_request_id"])
                return repo.create_student_request(StudentLeaveRequest(
                    student_leave_request_id=None, student_id=int(profile_id),
                    class_id=class_id, leave_date=leave_day.isoformat(),
                    session_count=session_count,
                    submitted_by_type=submitter,
                    contact_phone=contact_phone,
                    reason=reason, attachment_path=values.get("attachment_path") or None,
                ))
        finally: connection.close()

    def review(self, kind, request_id, decision, reviewer_account_id=None, note=None):
        """Approve or reject one pending request; attendance rows are never touched."""
        from app.services.authorization_service import require_permission
        if kind not in ("staff", "student"):
            raise ValueError("kind phải là staff hoặc student.")
        if decision not in ("approved", "rejected"):
            raise ValueError("Quyết định phải là approved hoặc rejected.")
        identity = require_permission(
            "employee.leave.review" if kind == "staff" else "student.leave.review")
        reviewer = int(identity.account_id if reviewer_account_id is None else reviewer_account_id)
        note = str(note or "").strip() or None
        if decision == "rejected" and not note:
            raise ValueError("Cần nhập lý do khi từ chối đơn.")
        try:
            request_id = int(request_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Mã đơn không hợp lệ.") from exc
        connection = connect(self.database_path)
        try:
            repo = LeaveRepository(connection)
            with transaction(connection, immediate=True):
                if connection.execute("SELECT 1 FROM accounts WHERE account_id = ?", (reviewer,)).fetchone() is None:
                    raise ValueError("Tài khoản duyệt đơn không tồn tại.")
                record = (repo.get_employee_request(request_id) if kind == "staff"
                          else repo.get_student_request(request_id))
                if record is None:
                    raise ValueError("Không tìm thấy đơn nghỉ cần duyệt.")
                if record["status"] != "pending":
                    raise ValueError("Đơn đã được xử lý trước đó và không thể duyệt lại.")
                changes = {
                    "status": decision,
                    "reviewed_by_account_id": reviewer,
                    "reviewed_at": datetime.now(timezone.utc).replace(microsecond=0)
                        .isoformat().replace("+00:00", "Z"),
                    "review_note": note,
                }
                updated = (repo.update_employee_request(request_id, changes) if kind == "staff"
                           else repo.update_student_request(request_id, changes))
                if not updated:
                    raise ValueError("Không cập nhật được trạng thái đơn.")
            return decision
        finally:
            connection.close()
