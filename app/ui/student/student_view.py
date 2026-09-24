"""
student_view.py — MÀN "DANH SÁCH HỌC VIÊN"
LÀM GÌ   : Lớp mỏng StudentView kế thừa PeopleView trong common/views.py và chọn khối "student". Giao diện thật nằm ở views.py.
             Xem hồ sơ, đăng ký mặt, xuất Excel.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: student_service, enrollment_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class StudentView(v.PeopleView):
    def __init__(self):
        super().__init__("student", "s_stu")
