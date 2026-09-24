"""
student_dashboard.py — MÀN "TỔNG QUAN KHỐI HỌC VIÊN"
LÀM GÌ   : Lớp mỏng StudentDashboard kế thừa DashboardView trong common/views.py và chọn khối "student". Giao diện thật nằm ở views.py.
             Thống kê sĩ số, đã/chưa điểm danh, theo lớp.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: attendance_service, class_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class StudentDashboard(v.DashboardView):
    def __init__(self):
        super().__init__("student", "s_dash")
