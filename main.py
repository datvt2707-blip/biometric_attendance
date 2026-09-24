"""
main.py — ĐIỂM KHỞI ĐỘNG ỨNG DỤNG
LÀM GÌ   : Tạo QApplication, áp theme, rồi chạy Flow: Splash -> Đăng nhập -> (Admin: Chọn khối) -> Cửa sổ chính.
             Mỗi lần đổi cửa sổ có hiệu ứng mờ dần (windowOpacity).
CÔNG NGHỆ: Qt Widgets (QApplication) + QPropertyAnimation (animation của Qt).
NGHIỆP VỤ: Điều hướng theo vai trò đăng nhập (xem app/ui/session.py).
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
import sys
from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QApplication
from app.ui import session
from app.ui.theme import apply_theme
from app.ui.splash_view import SplashView
from app.ui.login_view import LoginView
from app.ui.block_picker import BlockPicker
from app.ui.main_window import MainWindow


def fade(w, a, b, ms, done=None):
    an = QPropertyAnimation(w, b"windowOpacity", w); an.setDuration(ms); an.setStartValue(a); an.setEndValue(b)
    if done: an.finished.connect(done)
    an.start(); w._fx = an


class Flow:
    """Splash -> Đăng nhập -> (Admin: chọn khối) -> cửa sổ chính; chuyển cảnh bằng fade."""
    cur = None

    def go(self, w, animate=True):
        old, self.cur = self.cur, w
        if animate: w.setWindowOpacity(0.0)
        w.show()
        if animate: fade(w, 0.0, 1.0, 350)
        if old: fade(old, 1.0, 0.0, 250, old.close)

    def start(self):
        s = SplashView(); s.finished.connect(self.login); self.go(s, animate=False)

    def login(self):
        w = LoginView(); w.logged_in.connect(self.after_login); self.go(w)

    def after_login(self, key):
        session.current["role"] = key
        blocks = session.role()["blocks"]
        self.pick() if len(blocks) > 1 else self.open(blocks[0])

    def pick(self):
        w = BlockPicker(); w.chosen.connect(self.open); w.logout.connect(self.login); self.go(w)

    def open(self, block):
        w = MainWindow(block); w.switch_block.connect(self.pick); w.logout.connect(self.login); self.go(w)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_theme(app)
    flow = Flow(); flow.start()
    sys.exit(app.exec())
