"""
office_dashboard.py — MÀN "TỔNG QUAN KHỐI VĂN PHÒNG"
LÀM GÌ   : Lớp mỏng OfficeDashboard kế thừa DashboardView trong common/views.py và chọn khối "office". Giao diện thật nằm ở views.py.
             Thống kê quân số, đi muộn, vắng, xu hướng 7 ngày.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: attendance_service, employee_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class OfficeDashboard(v.DashboardView):
    def __init__(self):
        super().__init__("staff", "o_dash")
