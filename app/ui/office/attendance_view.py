"""
attendance_view.py — MÀN "CHẤM CÔNG"
LÀM GÌ   : Lớp mỏng AttendanceView kế thừa AttendanceView trong common/views.py và chọn khối "office". Giao diện thật nằm ở views.py.
             Check-in / Check-out, xác thực khuôn mặt + Active Liveness.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: authentication_service, attendance_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class AttendanceView(v.AttendanceView):
    def __init__(self):
        super().__init__("staff", "o_att")
