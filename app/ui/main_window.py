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
        self.setWindowTitle("Biometric Attendance — " + ("Khối văn phòng" if office else "Khối học viên"))
        self.resize(1360, 860); self.setMinimumSize(1120, 720)
        if hasattr(self, "setCustomBackgroundColor"):
            self.setCustomBackgroundColor(QColor(T.BG), QColor(T.BG))
        nav = self.navigationInterface
        pages = ([(OfficeDashboard(), FIF.HOME, "Tổng quan"), (EmployeeView(), FIF.PEOPLE, "Nhân viên"),
                  (OfficeAttendance(), FIF.CAMERA, "Chấm công"), (LeaveView(), FIF.CALENDAR, "Nghỉ phép")] if office else
                 [(StudentDashboard(), FIF.HOME, "Tổng quan"), (StudentView(), FIF.PEOPLE, "Học viên"),
                  (ClassView(), FIF.EDUCATION, "Lớp học"), (StudentAttendance(), FIF.CAMERA, "Điểm danh"),
                  (StudentLeave(), FIF.CALENDAR, "Nghỉ học")])
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
