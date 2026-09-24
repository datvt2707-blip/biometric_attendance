"""
settings_view.py — MÀN "CÀI ĐẶT KHỐI HỌC VIÊN (CHỈ ADMIN)"
LÀM GÌ   : Lớp mỏng SettingsView kế thừa SettingsView trong common/views.py và chọn khối "student". Giao diện thật nằm ở views.py.
             Lịch điểm danh, ngưỡng nhận diện, sao lưu, Telegram.
CÔNG NGHỆ: Qt Widgets (kế thừa).
NGHIỆP VỤ NỐI SAU: config/settings, notification_service.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from app.ui.common import views as v


class SettingsView(v.SettingsView):
    def __init__(self):
        super().__init__("student", "s_set")
