"""
attendance_view.py — MÀN "ĐIỂM DANH HỌC VIÊN"
LÀM GÌ   : Lớp mỏng AttendanceView kế thừa AttendanceView trong common/views.py và chọn khối "student". Giao diện thật nằm ở views.py.
             Điểm danh bằng khuôn mặt + Passive Liveness (không thử thách).
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: authentication_service, attendance_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class AttendanceView(v.AttendanceView):
    def __init__(self):
        super().__init__("student", "s_att")
