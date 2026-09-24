"""
leave_view.py — MÀN "NGHỈ PHÉP NHÂN VIÊN"
LÀM GÌ   : Lớp mỏng LeaveView kế thừa LeaveView trong common/views.py và chọn khối "office". Giao diện thật nằm ở views.py.
             Tạo, duyệt, từ chối đơn nghỉ phép.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: leave_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class LeaveView(v.LeaveView):
    def __init__(self):
        super().__init__("staff", "o_leave")
