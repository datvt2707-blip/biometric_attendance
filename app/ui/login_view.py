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

FEATS = ("Nh\u1eadn di\u1ec7n khu\u00f4n m\u1eb7t", "Qu\u1ea3n l\u00fd h\u1ed3 s\u01a1 nh\u00e2n s\u1ef1 & h\u1ecdc vi\u00ean")
SIDE_W = 430


class LoginView(QWidget):
    logged_in = Signal(object)

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
        self.card.box.addWidget(label("\u0110\u0103ng nh\u1eadp", "h1")); self.card.box.addWidget(label("Quy\u1ec1n truy c\u1eadp \u0111\u01b0\u1ee3c x\u00e1c \u0111\u1ecbnh t\u1eeb t\u00e0i kho\u1ea3n \u0111\u00e3 x\u00e1c th\u1ef1c", "muted"))
        self.u = GlowLine("Tên đăng nhập"); self.p = GlowLine("Mật khẩu", True)
        self.role = ComboBox(); self.role.addItems(["Vai tr\u00f2 \u0111\u01b0\u1ee3c x\u00e1c \u0111\u1ecbnh sau khi x\u00e1c th\u1ef1c"])
        self.role.setEnabled(False)
        self.role.setToolTip("Vai tr\u00f2 ph\u1ea3i đ\u01b0\u1ee3c x\u00e1c đ\u1ecbnh t\u1eeb t\u00e0i kho\u1ea3n sau khi x\u00e1c th\u1ef1c.")
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
        from app.services.authentication_service import (
            AuthenticationError, AuthenticationService, AuthorizationConfigurationError,
        )
        password = self.p.text()
        try:
            identity = AuthenticationService().login(self.u.text(), password)
        except AuthorizationConfigurationError as exc:
            self.p.clear()
            self.err.setText(str(exc))
            return
        except AuthenticationError:
            self.p.clear()
            self.err.setText("Tên đăng nhập hoặc mật khẩu không chính xác.")
            shake(self.card)
            return
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Authentication database operation failed")
            self.p.clear()
            self.err.setText("Không thể xác thực do lỗi cơ sở dữ liệu. Hãy thử lại sau.")
            return
        self.p.clear()
        self.logged_in.emit(identity)
