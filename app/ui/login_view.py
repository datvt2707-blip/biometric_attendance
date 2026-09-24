"""
login_view.py — MÀN ĐĂNG NHẬP
LÀM GÌ   : Form tên đăng nhập, mật khẩu, chọn vai trò. Bên trái là panel giới thiệu, bên phải là form.
CÔNG NGHỆ: Qt Widgets (bố cục, ô nhập) + QPainter (nền lưới chấm và đường quét trong paintEvent)
             + QSS (logo, dòng tính năng) + animation (form hiện dần, rung khi sai, logo nhịp thở).
NGHIỆP VỤ: Nút "Đăng nhập" phát tín hiệu logged_in(vai trò). Bỏ trống ô nào thì form rung.
NỐI SAU  : authentication_service.login(username, password).
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
import math
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QLinearGradient
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFrame
from app.ui import theme as T
from app.ui.common.widgets import Card, label, ComboBox, CheckBox
from app.ui.common.anim import GlowLine, FadeButton, fade_in, slide_in, shake, mix

KEYS = ["admin", "hr", "hocvu"]
FEATS = ("Nhận diện khuôn mặt ArcFace", "Chống giả mạo MiniFASNet", "Quản lý nhân sự & học viên", "Thông báo Telegram")
SIDE_W = 430


class LoginView(QWidget):
    logged_in = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("login")
        self.setWindowTitle("Đăng nhập – Biometric Attendance"); self.resize(1040, 640)
        self.tick, self.t = 0, 0.0
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        side = QFrame(); side.setObjectName("side"); side.setFixedWidth(SIDE_W)
        s = QVBoxLayout(side); s.setContentsMargins(48, 56, 48, 48); s.setSpacing(12)
        self.logo = label("◉"); s.addWidget(self.logo); s.addWidget(label("Biometric\nAttendance", "h1"))
        s.addWidget(label("Chấm công & điểm danh bằng nhận diện khuôn mặt", "muted")); s.addSpacing(28)
        self.feats = [label("■  " + f) for f in FEATS]
        for lb in self.feats: s.addWidget(lb)
        s.addStretch(); s.addWidget(label("v1.0.0 · Desktop Application", "muted"))
        right = QVBoxLayout(); right.setAlignment(Qt.AlignCenter)
        self.card = Card(); self.card.setFixedWidth(400); self.card.box.setSpacing(14); self.card.box.setContentsMargins(30, 30, 30, 30)
        self.card.box.addWidget(label("Đăng nhập", "h1")); self.card.box.addWidget(label("Chọn vai trò và đăng nhập để tiếp tục", "muted"))
        self.u = GlowLine("Tên đăng nhập"); self.p = GlowLine("Mật khẩu", True)
        self.role = ComboBox(); self.role.addItems(["Quản trị viên (Admin)", "Nhân viên HR – Khối văn phòng", "Nhân viên học vụ – Khối học viên"])
        for w in (self.u, self.p, self.role): self.card.box.addWidget(w)
        self.card.box.addWidget(CheckBox("Ghi nhớ đăng nhập"))
        self.err = label("", None, T.ROSE); self.err.setWordWrap(True); self.card.box.addWidget(self.err)
        btn = FadeButton("Đăng nhập"); btn.setFixedHeight(40); btn.clicked.connect(self._submit); self.card.box.addWidget(btn)
        self.u.returnPressed.connect(self._submit); self.p.returnPressed.connect(self._submit)
        right.addWidget(self.card); root.addWidget(side); root.addLayout(right, 1)
        self._highlight(0)
        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(33)

    def _highlight(self, hi):
        for i, lb in enumerate(self.feats): lb.setStyleSheet(f"color:{T.BRASS if i == hi else T.MUT};")

    def _tick(self):
        self.tick += 1; self.t = (self.t + 0.003) % 1
        b = (math.sin(self.tick / 14) + 1) / 2                      # logo nhịp thở
        self.logo.setStyleSheet(f"color:{mix('#6E5F3F', T.BRASS, b)}; font-size:44px;")
        if self.tick % 40 == 0: self._highlight((self.tick // 40) % len(self.feats))   # 4 dòng lần lượt sáng
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, lambda: (fade_in(self.card, 600), slide_in(self.card, 30, 600)))   # form hiện dần + trượt vào

    def closeEvent(self, e):
        self.timer.stop(); super().closeEvent(e)

    def paintEvent(self, _):                                        # nền lưới chấm + đường quét
        p = QPainter(self); w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(T.BG)); p.setPen(Qt.NoPen); p.setBrush(QColor(184, 155, 98, 26))
        for x in range(SIDE_W + 24, w, 36):
            for y in range(18, h, 36): p.drawRect(x, y, 2, 2)
        y = int(self.t * h); g = QLinearGradient(0, y - 70, 0, y)
        g.setColorAt(0, QColor(184, 155, 98, 0)); g.setColorAt(1, QColor(184, 155, 98, 38))
        p.fillRect(SIDE_W, y - 70, w - SIDE_W, 70, g); p.setPen(QColor(184, 155, 98, 90)); p.drawLine(SIDE_W, y, w, y)

    def _submit(self):
        if not self.u.text().strip() or not self.p.text():
            self.err.setText("Vui lòng nhập tên đăng nhập và mật khẩu."); shake(self.card); return   # rung khi sai
        self.err.setText(""); self.logged_in.emit(KEYS[self.role.currentIndex()])
