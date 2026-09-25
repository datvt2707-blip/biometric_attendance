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
from PySide6.QtWidgets import QApplication, QMessageBox
from app.database.database import initialize_database
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
        session.logout()
        w = LoginView(); w.logged_in.connect(self.after_login); self.go(w)

    def after_login(self, _untrusted_role):
        # Never derive access from a selector or caller-supplied role string.
        from app.services.authentication_service import AuthenticatedIdentity
        session.logout()
        if not isinstance(_untrusted_role, AuthenticatedIdentity):
            if isinstance(self.cur, LoginView):
                self.cur.err.setText("Thông tin đăng nhập chưa được dịch vụ xác thực xác nhận.")
            return
        try:
            session.establish(_untrusted_role)
            role = session.role()
            if len(role["blocks"]) > 1:
                self.pick()
            else:
                self.open(role["blocks"][0])
        except PermissionError as exc:
            session.logout()
            if isinstance(self.cur, LoginView):
                self.cur.err.setText(
                    f"{exc} Tài khoản đã xác thực nhưng ứng dụng chưa có ma trận quyền được duyệt; "
                    "không thể mở các màn hình được bảo vệ."
                )

    def pick(self):
        w = BlockPicker(); w.chosen.connect(self.open); w.logout.connect(self.login); self.go(w)

    def open(self, block):
        w = MainWindow(block); w.switch_block.connect(self.pick); w.logout.connect(self.login); self.go(w)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_theme(app)
    try:
        initialize_database()
    except Exception:
        import logging
        logging.exception("Application database bootstrap failed")
        QMessageBox.critical(
            None,
            "Lỗi cơ sở dữ liệu",
            "Không thể khởi tạo hoặc mở cơ sở dữ liệu. Dữ liệu hiện có được giữ nguyên; hãy kiểm tra tệp dữ liệu và quyền truy cập.",
        )
        raise SystemExit(1)
    try:
        from app.services.initial_account_bootstrap import account_count
        if account_count() == 0:
            QMessageBox.warning(
                None,
                "Chưa có tài khoản đăng nhập",
                "Cơ sở dữ liệu chưa có tài khoản nào nên không thể đăng nhập.\n\n"
                "Chạy một lần lệnh sau (cùng thư mục dự án) để tạo tài khoản khởi tạo, "
                "vai trò, quyền và ngưỡng liveness mặc định:\n\n"
                "    python -m app.services.initial_account_bootstrap\n\n"
                "Lệnh sẽ sao lưu cơ sở dữ liệu trước khi ghi và in mật khẩu được sinh ngẫu nhiên đúng một lần.",
            )
    except Exception:
        import logging
        logging.exception("Initial account check failed")
    flow = Flow(); flow.start()
    sys.exit(app.exec())
