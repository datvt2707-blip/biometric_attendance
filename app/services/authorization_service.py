"""Central permission codes and authenticated service-boundary checks."""
from __future__ import annotations

from contextvars import ContextVar


_identity = ContextVar("biometric_attendance_identity", default=None)


class AuthorizationService:
    """Holds the current authenticated identity and checks database-loaded claims."""

    @staticmethod
    def set_identity(identity):
        _identity.set(identity)

    @staticmethod
    def clear():
        _identity.set(None)

    @staticmethod
    def identity():
        value = _identity.get()
        if value is None:
            raise PermissionError("Cần đăng nhập để thực hiện thao tác này.")
        return value

    @classmethod
    def has_permission(cls, permission_code):
        value = _identity.get()
        return bool(value is not None and any(
            item.get("permission_code") == permission_code for item in value.permissions
        ))

    @classmethod
    def require(cls, permission_code):
        identity = cls.identity()
        if not cls.has_permission(permission_code):
            raise PermissionError(f"Tài khoản không có quyền: {permission_code}.")
        return identity


def require_permission(permission_code):
    return AuthorizationService.require(permission_code)


# Stable codes map only to screens/actions verified in the current source tree.
PERMISSION_NAMES = {
    "dashboard.staff.read": "Xem tổng quan khối văn phòng",
    "dashboard.student.read": "Xem tổng quan khối học viên",
    "employee.read": "Tra cứu nhân viên",
    "employee.write": "Tạo và cập nhật hồ sơ nhân viên",
    "employee.deactivate": "Ngừng hoạt động nhân viên",
    "employee.face.enroll": "Đăng ký dữ liệu khuôn mặt nhân viên",
    "employee.attendance.read": "Tra cứu chấm công nhân viên",
    "employee.attendance.record": "Ghi nhận check-in/check-out nhân viên",
    "employee.attendance.export": "Xuất CSV chấm công nhân viên",
    "employee.leave.read": "Tra cứu đơn nghỉ phép nhân viên",
    "employee.leave.submit": "Tạo đơn nghỉ phép nhân viên",
    "employee.leave.review": "Duyệt hoặc từ chối đơn nghỉ phép nhân viên",
    "student.read": "Tra cứu học viên",
    "student.write": "Tạo và cập nhật hồ sơ học viên",
    "student.deactivate": "Ngừng hoạt động học viên",
    "student.face.enroll": "Đăng ký dữ liệu khuôn mặt học viên",
    "student.attendance.read": "Tra cứu điểm danh học viên",
    "student.attendance.record": "Ghi nhận điểm danh học viên",
    "student.attendance.export": "Xuất CSV điểm danh học viên",
    "class.read": "Tra cứu lớp học và roster",
    "class.write": "Tạo và cập nhật lớp học",
    "student.leave.read": "Tra cứu đơn nghỉ học",
    "student.leave.submit": "Tạo đơn nghỉ học",
    "student.leave.review": "Duyệt hoặc từ chối đơn nghỉ học",
    "account.read": "Tra cứu tài khoản và phân quyền",
    "account.manage": "Quản lý trạng thái tài khoản",
    "settings.write": "Quản lý cài đặt hệ thống",
    "settings.read": "Xem cài đặt hệ thống",
}


ROLE_PERMISSION_CODES = {
    "ADMIN": frozenset(PERMISSION_NAMES),
    "HR": frozenset({
        "dashboard.staff.read", "employee.read", "employee.write", "employee.deactivate",
        "employee.attendance.read", "employee.attendance.record", "employee.attendance.export",
        "employee.leave.read", "employee.leave.submit", "employee.leave.review",
    }),
    "STUDENT_SUPPORT": frozenset({
        "dashboard.student.read", "student.read", "student.write", "student.deactivate",
        "student.attendance.read", "student.attendance.record", "student.attendance.export",
        "class.read", "class.write", "student.leave.read", "student.leave.submit",
        "student.leave.review",
    }),
}

ROLE_DEFINITIONS = {
    "ADMIN": ("Admin", "Quản trị viên hệ thống"),
    "HR": ("HR", "Nhân sự; không có quyền quản trị hệ thống"),
    "STUDENT_SUPPORT": ("Cán bộ hỗ trợ học tập", "Nhân viên hỗ trợ học tập"),
}

ACCOUNT_USERNAMES = {
    "ADMIN": "admin",
    "HR": "hr",
    "STUDENT_SUPPORT": "student_support",
}


def role_context(identity):
    """Translate loaded permission codes to the existing two-block UI navigation."""
    codes = {item.get("permission_code") for item in identity.permissions}
    blocks = []
    if "dashboard.staff.read" in codes:
        blocks.append("staff")
    if "dashboard.student.read" in codes:
        blocks.append("student")
    if not blocks:
        raise PermissionError("Tài khoản không được gắn quyền mở màn hình.")
    roles = [role for role in identity.roles
             if role.get("role_code") in ROLE_DEFINITIONS]
    role_name = roles[0].get("role_name") if len(roles) == 1 else " / ".join(
        role.get("role_name", role.get("role_code", "")) for role in roles
    )
    title = " / ".join(
        ROLE_DEFINITIONS[role["role_code"]][1] for role in roles
    ) or identity.username
    return {
        "name": role_name or identity.username,
        "title": title,
        "username": identity.username,
        "blocks": tuple(blocks),
        "accounts": "account.read" in codes,
        "settings": "settings.read" in codes,
        "permissions": frozenset(codes),
    }
