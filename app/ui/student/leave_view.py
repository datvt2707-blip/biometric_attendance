"""
leave_view.py — MÀN "ĐƠN NGHỈ HỌC"
LÀM GÌ   : Lớp mỏng LeaveView kế thừa LeaveView trong common/views.py và chọn khối "student". Giao diện thật nằm ở views.py.
             Nhân viên học vụ duyệt đơn nghỉ của học viên.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: leave_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class LeaveView(v.LeaveView):
    def __init__(self):
        super().__init__("student", "s_leave")
