"""
splash_view.py — INTRO KHI MỞ APP
LÀM GÌ   : Có assets/intro.mp4 thì phát video. Không có thì tự vẽ: lưới chấm 3D xoay, khung nhận diện thu lại,
             đường quét, chữ BIOMETRIC ATTENDANCE hiện dần rồi mờ đi.
CÔNG NGHỆ: QPainter (toàn bộ hình vẽ, hàm _mesh và paintEvent) + QVariantAnimation (chạy thời gian t từ 0 đến 1)
             + QtMultimedia (QMediaPlayer, chỉ khi có file video). Không dùng QML, không dùng thư viện 3D.
NGHIỆP VỤ: Không có (chỉ là hiệu ứng thương hiệu). Bấm chuột hoặc phím để bỏ qua.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
import math
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QVariantAnimation, QRectF, QPointF, QUrl
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QFont, QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout
from app.ui import theme as T

VIDEO = Path(__file__).resolve().parents[2] / "assets" / "intro.mp4"
BR = (184, 155, 98)


def seg(t, a, b): return max(0.0, min(1.0, (t - a) / (b - a)))
def ease(x): return 1 - (1 - x) ** 3


class SplashView(QWidget):
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint); self.resize(1040, 640); self.t = 0.0; self._done = False; self._video = False
        self.move(QGuiApplication.primaryScreen().availableGeometry().center() - self.rect().center())
        self.a = QVariantAnimation(self); self.a.setDuration(4200); self.a.setStartValue(0.0); self.a.setEndValue(1.0)
        self.a.valueChanged.connect(self._on); self.a.finished.connect(self._finish)
        if VIDEO.exists(): self._video = self._try_video()

    def _try_video(self):
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
            lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); vw = QVideoWidget(); lay.addWidget(vw)
            self.player = QMediaPlayer(self); self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio); self.player.setVideoOutput(vw); self.player.setSource(QUrl.fromLocalFile(str(VIDEO)))
            self.player.mediaStatusChanged.connect(lambda s: s == QMediaPlayer.MediaStatus.EndOfMedia and self._finish())
            return True
        except Exception:
            return False

    def showEvent(self, e):
        super().showEvent(e); self.player.play() if self._video else self.a.start()

    def _on(self, v): self.t = float(v); self.update()
    def _finish(self):
        if not self._done: self._done = True; self.finished.emit()
    def mousePressEvent(self, e): self._finish()                     # bấm để bỏ qua
    def keyPressEvent(self, e): self._finish()

    def _mesh(self, p, cx, cy, R, ang, alpha):                       # lưới điểm 3D xoay, chiếu phối cảnh
        p.setPen(Qt.NoPen)
        for i in range(-6, 7):
            lat = i / 7 * math.pi / 2
            for j in range(28):
                lon = j / 28 * 2 * math.pi + ang
                x, y, z = math.cos(lat) * math.sin(lon), math.sin(lat), math.cos(lat) * math.cos(lon)
                s = 1 / (1 - z * 0.28); d = (z + 1) / 2; r = 1.0 + 1.8 * d
                p.setBrush(QColor(*BR, int((30 + 190 * d) * alpha)))
                p.drawRect(QRectF(cx + x * R * 0.85 * s - r, cy - y * R * 1.15 * s - r, 2 * r, 2 * r))

    def paintEvent(self, _):
        if self._video: return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); w, h, t = self.width(), self.height(), self.t
        p.fillRect(self.rect(), QColor(T.BG)); cx, cy, R = w / 2, h / 2 - 30, 150
        ang = (1 - ease(seg(t, 0.0, 0.55))) * math.pi * 3                       # xoay nhanh rồi khóa chính diện
        self._mesh(p, cx, cy, R, ang, seg(t, 0, 0.15) * (1 - seg(t, 0.78, 0.9)))
        fa = seg(t, 0.25, 0.4) * (1 - seg(t, 0.8, 0.9)); half = R * (1.9 - 0.9 * ease(seg(t, 0.25, 0.6)))
        p.setPen(QPen(QColor(126, 163, 145, int(255 * fa)), 2))                 # khung nhận diện thu về
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x, y = cx + sx * half, cy + sy * half * 1.15
            p.drawLine(QPointF(x, y), QPointF(x - sx * 34, y)); p.drawLine(QPointF(x, y), QPointF(x, y - sy * 34))
        s = seg(t, 0.5, 0.75)
        if 0 < s < 1:                                                           # đường quét
            y = cy - R * 1.15 + s * R * 2.3; g = QLinearGradient(0, y - 46, 0, y)
            g.setColorAt(0, QColor(126, 163, 145, 0)); g.setColorAt(1, QColor(126, 163, 145, 70))
            p.fillRect(QRectF(cx - R, y - 46, 2 * R, 46), g); p.setPen(QColor(126, 163, 145, 200)); p.drawLine(QPointF(cx - R, y), QPointF(cx + R, y))
        ta = seg(t, 0.7, 0.86); f = QFont("Be Vietnam Pro, Segoe UI", 20); f.setLetterSpacing(QFont.AbsoluteSpacing, 9 - 5 * ta); p.setFont(f)
        p.setPen(QColor(216, 210, 196, int(255 * ta))); p.drawText(QRectF(0, cy + R * 1.4, w, 40), Qt.AlignCenter, "BIOMETRIC ATTENDANCE")
        p.setPen(QPen(QColor(*BR, int(255 * ta)), 2)); p.drawLine(QPointF(cx - 150 * ta, cy + R * 1.4 + 50), QPointF(cx + 150 * ta, cy + R * 1.4 + 50))
        p.fillRect(self.rect(), QColor(16, 21, 27, int(255 * seg(t, 0.93, 1.0))))
