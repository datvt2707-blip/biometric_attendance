"""
theme.py — BẢNG MÀU + QSS DÙNG CHUNG
LÀM GÌ   : Khai báo màu (BG, CARD, BRASS, SAGE...) và chuỗi QSS tạo kiểu cho nút, ô nhập, thẻ, bảng, popup.
             Hàm apply_theme() bật chủ đề tối của Fluent và đặt màu nhấn.
CÔNG NGHỆ: QSS (giống CSS của Qt) + 2 hàm của Fluent Widgets (setTheme, setThemeColor).
NGHIỆP VỤ: Không có. Đổi màu cả app chỉ cần sửa file này.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtGui import QFont
from qfluentwidgets import setTheme, Theme, setThemeColor

BG, SIDE, CARD, CARD2, LINE = "#10151B", "#0C1116", "#172029", "#1D2833", "#2A3745"
TX, MUT = "#D8D2C4", "#8C97A3"
BRASS, SAGE, ROSE, AMBER, STEEL = "#B89B62", "#7EA391", "#B46A63", "#C8A05A", "#7F98B5"
TONE = {"ok": SAGE, "late": ROSE, "wait": AMBER, "info": STEEL}

QSS = f"""
QLabel {{ color:{TX}; background:transparent; }}
QLabel#h1 {{ font-size:22px; font-weight:600; }}
QLabel#muted {{ color:{MUT}; font-size:12px; }}
QLabel#cardTitle {{ font-size:13px; font-weight:600; }}
QLabel#big {{ font-size:30px; font-weight:600; }}
QLabel#avatar {{ background:{CARD2}; border:1px solid {LINE}; border-radius:0px; color:{BRASS}; font-size:11px; }}
QFrame#card {{ background:{CARD}; border:1px solid {LINE}; border-radius:0px; }}
QFrame#line {{ background:{LINE}; max-height:1px; }}
QTableWidget {{ background:transparent; border:none; color:{TX}; gridline-color:transparent; }}
QTableWidget::item {{ border-bottom:1px solid {LINE}; padding-left:8px; }}
QHeaderView::section {{ background:transparent; color:{MUT}; border:none;
    border-bottom:1px solid {LINE}; padding:8px; font-weight:500; }}
QScrollArea {{ background:transparent; border:none; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}
QFrame#pill {{ background:{SIDE}; border:1px solid {LINE}; border-radius:0px; }}
QFrame#pill QPushButton {{ border:none; border-radius:0px; padding:6px 18px; color:{MUT}; background:transparent; }}
QFrame#pill QPushButton:hover {{ color:{TX}; }}
QFrame#pill QPushButton:checked {{ background:{BRASS}; color:#1A1509; font-weight:600; }}
QFrame#side {{ background:{SIDE}; border-right:1px solid {LINE}; }}
QWidget#login {{ background:{BG}; }}
QPushButton#primary {{ background:{BRASS}; color:#1A1509; border:1px solid {BRASS}; padding:8px 20px; font-weight:600; }}
QPushButton#primary:hover {{ background:#C9AE78; }}
QPushButton#ghost {{ background:transparent; color:{TX}; border:1px solid {LINE}; padding:8px 20px; }}
QPushButton#ghost:hover {{ border-color:{BRASS}; color:{BRASS}; }}
QPushButton#blockcard {{ background:{CARD}; color:{TX}; border:1px solid {LINE}; padding:26px; text-align:left; font-size:15px; }}
QPushButton#blockcard:hover {{ border-color:{BRASS}; background:{CARD2}; }}
QLineEdit, QComboBox {{ background:{SIDE}; color:{TX}; border:1px solid {LINE}; padding:8px 12px; selection-background-color:{BRASS}; }}
QLineEdit:focus, QComboBox:focus {{ border-color:{BRASS}; }}
QComboBox::drop-down {{ border:none; width:26px; }}
QComboBox QAbstractItemView {{ background:{CARD}; color:{TX}; border:1px solid {LINE}; selection-background-color:{CARD2}; outline:0; }}
QCheckBox {{ color:{TX}; spacing:8px; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {LINE}; background:{SIDE}; }}
QCheckBox::indicator:checked {{ background:{BRASS}; border-color:{BRASS}; }}
QDialog {{ background:{BG}; }}
QTextEdit {{ background:{SIDE}; color:{TX}; border:1px solid {LINE}; padding:6px 10px; }}
QTextEdit:focus {{ border-color:{BRASS}; }}
QPushButton#danger {{ background:{ROSE}; color:#FFF; border:1px solid {ROSE}; padding:8px 20px; font-weight:600; }}
"""

def apply_theme(app):
    setTheme(Theme.DARK)
    setThemeColor(BRASS)
    app.setFont(QFont("Be Vietnam Pro, Segoe UI", 10))
    app.setStyleSheet(QSS)
