"""
anim.py — HIỆU ỨNG CHUYỂN ĐỘNG DÙNG CHUNG
LÀM GÌ   : fade_in, slide_in, shake, mix (pha màu), GlowLine (ô nhập viền sáng dần), FadeButton (nút đổi màu mượt).
CÔNG NGHỆ: QPropertyAnimation, QVariantAnimation, QGraphicsOpacityEffect của Qt. Không cần thư viện ngoài.
NGHIỆP VỤ: Không có. Hiện chỉ màn đăng nhập dùng.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtCore import QPropertyAnimation, QVariantAnimation, QEasingCurve, QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLineEdit, QPushButton
from app.ui import theme as T


def mix(c1, c2, t):
    a, b = QColor(c1), QColor(c2)
    return QColor(*[int(x + (y - x) * t) for x, y in ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))]).name()


def fade_in(w, ms=450):
    eff = QGraphicsOpacityEffect(w); w.setGraphicsEffect(eff)
    a = QPropertyAnimation(eff, b"opacity", w); a.setDuration(ms); a.setStartValue(0.0); a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic); a.finished.connect(lambda: w.setGraphicsEffect(None)); a.start(); w._fade = a


def slide_in(w, dy=28, ms=450):
    end = w.pos(); a = QPropertyAnimation(w, b"pos", w); a.setDuration(ms)
    a.setStartValue(end + QPoint(0, dy)); a.setEndValue(end); a.setEasingCurve(QEasingCurve.OutCubic); a.start(); w._slide = a


def shake(w):
    x, y = w.x(), w.y(); a = QPropertyAnimation(w, b"pos", w); a.setDuration(380)
    for k, dx in ((0, 0), (.15, -10), (.35, 10), (.55, -8), (.75, 6), (1, 0)): a.setKeyValueAt(k, QPoint(x + dx, y))
    a.start(); w._shake = a


class GlowLine(QLineEdit):
    """Ô nhập: viền chuyển dần sang màu đồng khi được chọn."""
    def __init__(self, placeholder="", password=False):
        super().__init__(); self.setPlaceholderText(placeholder)
        if password: self.setEchoMode(QLineEdit.Password)
        self._t = 0.0; self._a = QVariantAnimation(self); self._a.setDuration(200); self._a.valueChanged.connect(self._set); self._set(0.0)

    def _set(self, t):
        self._t = float(t); c = mix(T.LINE, T.BRASS, self._t)
        self.setStyleSheet(f"QLineEdit{{background:{T.SIDE};color:{T.TX};border:1px solid {c};padding:9px 12px;selection-background-color:{T.BRASS};}}")

    def _go(self, to):
        self._a.stop(); self._a.setStartValue(self._t); self._a.setEndValue(float(to)); self._a.start()

    def focusInEvent(self, e): self._go(1.0); super().focusInEvent(e)
    def focusOutEvent(self, e): self._go(0.0); super().focusOutEvent(e)


class FadeButton(QPushButton):
    """Nút chính: đổi màu mượt khi rê chuột."""
    def __init__(self, text):
        super().__init__(text); self.setCursor(Qt.PointingHandCursor)
        self._t = 0.0; self._a = QVariantAnimation(self); self._a.setDuration(180); self._a.valueChanged.connect(self._set); self._set(0.0)

    def _set(self, t):
        self._t = float(t); c = mix(T.BRASS, "#D6BC84", self._t)
        self.setStyleSheet(f"QPushButton{{background:{c};color:#1A1509;border:1px solid {c};padding:8px 20px;font-weight:600;}}")

    def _go(self, to):
        self._a.stop(); self._a.setStartValue(self._t); self._a.setEndValue(float(to)); self._a.start()

    def enterEvent(self, e): self._go(1.0); super().enterEvent(e)
    def leaveEvent(self, e): self._go(0.0); super().leaveEvent(e)
