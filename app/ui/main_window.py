"""
main_window.py — CỬA SỔ CHÍNH + SIDEBAR
LÀM GÌ   : Dựng sidebar theo vai trò và khối. Mỗi cửa sổ chỉ chứa MỘT khối.
             Cuối sidebar có nút Đổi khối (chỉ Admin) và Đăng xuất.
CÔNG NGHỆ: Fluent Widgets (FluentWindow, FluentIcon, addSubInterface) trên nền Qt Widgets.
             Chuyển động sidebar và chuyển trang là của Fluent.
NGHIỆP VỤ: Phân quyền hiển thị menu: Tài khoản và Cài đặt chỉ Admin thấy.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from qfluentwidgets import FluentWindow, FluentIcon as FIF, NavigationItemPosition
from app.ui import theme as T, session
from app.ui.common import views as v
from app.ui.office.office_dashboard import OfficeDashboard
from app.ui.office.employee_view import EmployeeView
from app.ui.office.attendance_view import AttendanceView as OfficeAttendance
from app.ui.office.leave_view import LeaveView
from app.ui.office.settings_view import SettingsView as OfficeSettings
from app.ui.student.student_dashboard import StudentDashboard
from app.ui.student.student_view import StudentView
from app.ui.student.class_view import ClassView
from app.ui.student.leave_view import LeaveView as StudentLeave
from app.ui.student.attendance_view import AttendanceView as StudentAttendance
from app.ui.student.settings_view import SettingsView as StudentSettings


class MainWindow(FluentWindow):
    """Mỗi cửa sổ chỉ chứa MỘT khối; menu phụ thuộc vai trò đăng nhập."""
    switch_block = Signal()
    logout = Signal()

    def __init__(self, block):
        super().__init__()
        r, office = session.role(), block == "staff"
        if block not in r["blocks"]:
            raise PermissionError("Tài khoản không được phép mở khối chức năng này.")
        self.setWindowTitle("Biometric Attendance — " + ("Khối văn phòng" if office else "Khối học viên"))
        self.resize(1360, 860); self.setMinimumSize(1120, 720)
        if hasattr(self, "setCustomBackgroundColor"):
            self.setCustomBackgroundColor(QColor(T.BG), QColor(T.BG))
        nav = self.navigationInterface
        page_specs = ([
            ("dashboard.staff.read", OfficeDashboard, FIF.HOME, "T\u1ed5ng quan"),
            ("employee.read", EmployeeView, FIF.PEOPLE, "Nh\u00e2n vi\u00ean"),
            ("employee.attendance.read", OfficeAttendance, FIF.CAMERA, "Ch\u1ea5m c\u00f4ng"),
            ("employee.leave.read", LeaveView, FIF.CALENDAR, "Ngh\u1ec9 ph\u00e9p"),
        ] if office else [
            ("dashboard.student.read", StudentDashboard, FIF.HOME, "T\u1ed5ng quan"),
            ("student.read", StudentView, FIF.PEOPLE, "H\u1ecdc vi\u00ean"),
            ("class.read", ClassView, FIF.EDUCATION, "L\u1edbp h\u1ecdc"),
            ("student.attendance.read", StudentAttendance, FIF.CAMERA, "\u0110i\u1ec3m danh"),
            ("student.leave.read", StudentLeave, FIF.CALENDAR, "Ngh\u1ec9 h\u1ecdc"),
        ])
        pages = [(page_type(), icon, title) for permission, page_type, icon, title in page_specs
                 if session.has_permission(permission)]
        if r["accounts"]: pages.append((v.AccountsView(block, "acc"), FIF.TAG, "Tài khoản"))
        if r["settings"]: pages.append((OfficeSettings() if office else StudentSettings(), FIF.SETTING, "Cài đặt"))
        for page, icon, text in pages: self.addSubInterface(page, icon, text)
        bottom = NavigationItemPosition.BOTTOM
        if len(r["blocks"]) > 1:
            nav.addItem("switch", FIF.SYNC, "Đổi khối", onClick=lambda *_: self.switch_block.emit(), selectable=False, position=bottom)
        nav.addItem("logout", FIF.CLOSE, "Đăng xuất", onClick=lambda *_: self.logout.emit(), selectable=False, position=bottom)
        try:
            nav.setExpandWidth(220); nav.panel.expand(False)
        except Exception:
            pass
