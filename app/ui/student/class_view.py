"""
class_view.py — MÀN "QUẢN LÝ LỚP HỌC"
LÀM GÌ   : Lớp mỏng ClassView kế thừa ClassesView trong common/views.py và chọn khối "student". Giao diện thật nằm ở views.py.
             Tạo/sửa lớp, xem và xác nhận sĩ số.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: class_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class ClassView(v.ClassesView):
    def __init__(self):
        super().__init__("student", "s_cls")
