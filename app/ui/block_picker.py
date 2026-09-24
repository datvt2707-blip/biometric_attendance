"""
block_picker.py — MÀN CHỌN KHỐI LÀM VIỆC (chỉ Admin thấy)
LÀM GÌ   : Hai thẻ lớn: Khối văn phòng và Khối học viên. Có nút Đăng xuất.
CÔNG NGHỆ: Qt Widgets + QSS (kiểu thẻ #blockcard trong theme.py).
NGHIỆP VỤ: Admin quản lý cả hai khối nên phải chọn. HR và học vụ chỉ có 1 khối nên bỏ qua màn này.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from app.ui import session
from app.ui.common.widgets import label, PushButton


class BlockPicker(QWidget):
    """Admin chọn khối làm việc sau khi đăng nhập."""
    chosen = Signal(str); logout = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("login"); self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("Chọn khối làm việc"); self.resize(1040, 640)
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignCenter); v.setSpacing(14)
        t = label("Chọn khối làm việc", "h1"); t.setAlignment(Qt.AlignCenter)
        s = label(f"Xin chào, {session.role()['name']}. Bạn muốn quản lý khối nào?", "muted"); s.setAlignment(Qt.AlignCenter)
        v.addWidget(t); v.addWidget(s); v.addSpacing(18)
        row = QHBoxLayout(); row.setSpacing(18); row.setAlignment(Qt.AlignCenter)
        from PySide6.QtWidgets import QPushButton
        for key, txt in (("staff", "Khối văn phòng\n\nChấm công · Nhân viên · Nghỉ phép"),
                         ("student", "Khối học viên\n\nĐiểm danh · Học viên · Lớp học")):
            b = QPushButton(txt); b.setObjectName("blockcard"); b.setFixedSize(340, 170); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.chosen.emit(k)); row.addWidget(b)
        v.addLayout(row); v.addSpacing(18)
        out = PushButton("Đăng xuất"); out.setFixedWidth(160); out.clicked.connect(self.logout.emit)
        v.addWidget(out, 0, Qt.AlignCenter)
