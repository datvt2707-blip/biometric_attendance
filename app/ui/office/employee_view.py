"""
employee_view.py — MÀN "DANH SÁCH NHÂN VIÊN"
LÀM GÌ   : Lớp mỏng EmployeeView kế thừa PeopleView trong common/views.py và chọn khối "office". Giao diện thật nằm ở views.py.
             Xem hồ sơ, đăng ký mặt, xuất Excel.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: employee_service, enrollment_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class EmployeeView(v.PeopleView):
    def __init__(self):
        super().__init__("staff", "o_emp")
