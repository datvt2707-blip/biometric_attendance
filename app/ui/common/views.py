"""
views.py — CÁC MÀN HÌNH CHÍNH (dùng chung cho 2 khối)
LÀM GÌ   : BasePage (khung trang: tiêu đề, nút góc phải, thông tin người dùng) và 6 màn:
             DashboardView, AttendanceView, PeopleView, LeaveView, ClassesView, SettingsView, AccountsView.
             Các file trong office/ và student/ chỉ kế thừa lại và chọn khối.
CÔNG NGHỆ: Qt Widgets (layout, bảng, nút, ô tìm kiếm) + Fluent SwitchButton (công tắc Telegram).
NGHIỆP VỤ: Mỗi nút gọi một popup trong dialogs.py. Bảng ở docs/UI_GUIDE.md phần Phụ lục nói rõ nút nào ứng với nghiệp vụ nào.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QFrame, QDialog
from qfluentwidgets import SwitchButton
from app.ui import theme as T
from app.ui.mock_data import DATA
from app.ui.common import dialogs as D
from app.ui.common.widgets import (Card, label, stat_card, bar_row, activity_row, LineChart, StepsBar,
                                   CameraView, make_table, tag, Pill, user_chip, Bar, PrimaryPushButton, PushButton, SearchLineEdit, ComboBox, LineEdit)


def kv(card, k, v, color=None):
    r = QHBoxLayout(); r.addWidget(label(k, "muted")); r.addStretch(); r.addWidget(label(v, color=color)); card.box.addLayout(r)


def switch_row(card, k, on):
    r = QHBoxLayout(); r.addWidget(label(k, "muted")); r.addStretch()
    s = SwitchButton(); s.setChecked(on); r.addWidget(s); card.box.addLayout(r)


class BasePage(QWidget):
    TITLE = ""

    def __init__(self, block, key):
        super().__init__()
        self.setObjectName(key); self.block = block; self.d = DATA[block]
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea(); sc.setWidgetResizable(True); outer.addWidget(sc)
        inner = QWidget(); sc.setWidget(inner)
        root = QVBoxLayout(inner); root.setContentsMargins(28, 22, 28, 26); root.setSpacing(16)
        self.head = QHBoxLayout(); self.head.setSpacing(12)
        col = QVBoxLayout(); col.setSpacing(0)
        col.addWidget(label(self.heading(), "h1")); col.addWidget(label(f"{self.d['name']} • Thứ Hai, 08/09/2026", "muted"))
        self.head.addLayout(col); self.head.addStretch(); root.addLayout(self.head)
        self.body = QVBoxLayout(); self.body.setSpacing(14); root.addLayout(self.body)
        self.build(self.d); self.head.addWidget(user_chip()); root.addStretch()

    def heading(self): return self.TITLE

    def row(self, *cards, stretch=None):
        h = QHBoxLayout(); h.setSpacing(14)
        for i, c in enumerate(cards): h.addWidget(c, stretch[i] if stretch else 1)
        self.body.addLayout(h); return h


class DashboardView(BasePage):
    TITLE = "Tổng quan"

    def build(self, d):
        self.row(*[stat_card(*s) for s in d["stats"]])
        c1 = Card(f"Xu hướng — {d['trend_t']} (7 ngày qua)"); c1.box.addWidget(LineChart(d["trend"]))
        c2 = Card(d["bars_t"])
        for b in d["bars"]: c2.box.addWidget(bar_row(*b))
        c2.box.addStretch()
        c3 = Card("Hoạt động gần đây")
        for a in d["acts"]: c3.box.addWidget(activity_row(*a))
        c3.box.addStretch()
        self.row(c1, c2, c3, stretch=[3, 2, 2])
        self.row(stat_card("Lượt xác thực hôm nay", "412", "Face + Liveness", "info"),
                 stat_card("Chặn giả mạo (FAKE)", "3", "MiniFASNet phát hiện", "late"),
                 stat_card("Độ khớp trung bình", "96.8%", "Ngưỡng cosine 0.60", "ok"))


class AttendanceView(BasePage):
    def heading(self): return self.d["att"]

    def build(self, d):
        left = Card()
        left.box.addWidget(CameraView(d["chip"]), 1)
        left.box.addWidget(label(d["st_title"], "cardTitle")); left.box.addWidget(label(d["st_hint"], "muted"))
        left.box.addWidget(StepsBar(d["steps"], d["cur"]))
        right = Card("Kết quả xác thực")
        right.box.addWidget(label(f"{d['who'][0]}\n{d['who'][1]}"))
        for k, v in [("Phát hiện khuôn mặt", "✓"), ("Chống giả mạo (MiniFASNet)", "REAL"), ("Nhận diện khuôn mặt", d["match"]), (d["live"], "PASS")]:
            kv(right, k, v, T.SAGE)
        for i, b in enumerate(d["btns"]):
            x = PrimaryPushButton(b) if i == 0 else PushButton(b)
            x.clicked.connect(lambda _=False, b=b: D.confirm(self.window(), b.split(" (")[0] + " thành công", f"{d['who'][0]} · {d['who'][1]}\n{d['match']} · REAL · 08:12", info=True))
            right.box.addWidget(x)
        right.box.addStretch()
        self.row(left, right, stretch=[3, 2])
        log = Card(f"Nhật ký {d['att'].lower()} hôm nay"); log.box.addWidget(make_table(d["lh"], d["log"], tone_cols=(3, 4)))
        self.body.addWidget(log)


class PeopleView(BasePage):
    def heading(self): return self.d["people"]

    def build(self, d):
        add = PrimaryPushButton("+ Đăng ký mới"); add.clicked.connect(lambda: D.enroll(d, self.window()))
        self.head.addWidget(add)
        tools = QHBoxLayout(); tools.setSpacing(10)
        s = SearchLineEdit(); s.setPlaceholderText("Tìm theo tên, mã…"); s.setFixedWidth(280)
        cb = ComboBox(); cb.addItems(["Tất cả trạng thái", "Đang hoạt động", "Nghỉ"]); cb.setFixedWidth(190)
        tools.addWidget(s); tools.addWidget(cb); tools.addStretch(); ex = PushButton("Xuất Excel"); ex.clicked.connect(lambda: D.export(self.window())); tools.addWidget(ex)
        self.body.addLayout(tools)
        c = Card()
        c.box.addWidget(make_table(d["ph"], d["rows"], tone_cols=(3, 4),
                        actions=lambda r: [("Xem", "brass", lambda: D.person_detail(d, r, self.window()))] + ([("Đăng ký mặt", "info", lambda: D.enroll(d, self.window()))] if "Chưa" in r[4] else [])))
        c.box.addWidget(label(f"Hiển thị {len(d['rows'])} / {d['stats'][0][1]}", "muted"))
        self.body.addWidget(c)


class LeaveView(BasePage):
    HS = ["Mã", "Nhân viên", "Loại nghỉ", "Từ ngày", "Đến ngày", "Lý do", "Trạng thái"]
    HT = ["Mã", "Học viên", "Lớp", "Ngày nghỉ", "Người nộp", "Lý do", "Trạng thái"]
    RS = [("NV001", "Nguyễn Văn A", "Nghỉ phép năm", "10/09/2026", "12/09/2026", "Du lịch gia đình", "Chờ duyệt"),
          ("NV002", "Trần Thị B", "Nghỉ ốm", "08/09/2026", "09/09/2026", "Cảm cúm", "Đã duyệt"),
          ("NV003", "Lê Văn C", "Nghỉ phép năm", "15/09/2026", "16/09/2026", "Việc cá nhân", "Chờ duyệt"),
          ("NV006", "Vũ Hải F", "Nghỉ không lương", "20/09/2026", "25/09/2026", "Về quê", "Từ chối"),
          ("NV004", "Phạm Thị D", "Nghỉ thai sản", "01/10/2026", "01/04/2027", "Thai sản", "Đã duyệt")]
    RT = [("SV001", "Trần Thị B", "11A", "08/09/2026", "Phụ huynh", "Sốt cao", "Đã duyệt"),
          ("SV002", "Nguyễn Minh T", "10B", "10/09/2026", "Học viên", "Việc gia đình", "Chờ duyệt"),
          ("SV003", "Lê Quang H", "12A", "09/09/2026", "Phụ huynh", "Đi khám bệnh", "Chờ duyệt"),
          ("SV004", "Phạm Thị L", "11B", "05/09/2026", "Phụ huynh", "Đi du lịch", "Từ chối"),
          ("SV005", "Đỗ Thảo N", "10A", "12/09/2026", "Phụ huynh", "Thi chứng chỉ", "Đã duyệt")]

    def heading(self): return "Nghỉ phép" if self.block == "staff" else "Đơn nghỉ học"

    def build(self, d):
        st = self.block == "staff"
        hd, rows = (self.HS, self.RS) if st else (self.HT, self.RT)
        add = PrimaryPushButton("+ Tạo đơn nghỉ phép" if st else "+ Tạo đơn nghỉ học")
        add.clicked.connect(lambda: D.leave_form(self.block, self.window())); self.head.addWidget(add)
        self.row(stat_card("Chờ duyệt", "2", "Cần xử lý", "wait"),
                 stat_card("Đã duyệt tháng này" if st else "Đã duyệt tuần này", "12" if st else "5", "+3 so với kỳ trước", "ok"),
                 stat_card("Từ chối", "1", "Kỳ này", "late"),
                 stat_card("Đang nghỉ hôm nay" if st else "Vắng hôm nay", "4" if st else "18", "4% quân số" if st else "6% sĩ số", "info"))
        self.body.addWidget(Pill(["Tất cả", "Chờ duyệt", "Đã duyệt", "Từ chối"]), 0, Qt.AlignLeft)

        def acts(r):
            if r[6] == "Chờ duyệt":
                return [("Duyệt", "ok", lambda: D.confirm(self.window(), "Duyệt đơn", f"Duyệt đơn nghỉ của {r[1]}?", "Duyệt")),
                        ("Từ chối", "late", lambda: D.confirm(self.window(), "Từ chối đơn", f"Từ chối đơn của {r[1]}. Vui lòng nhập lý do.", "Từ chối", reason=True, danger=True))]
            return [("Xem", "brass", lambda: D.leave_detail(hd, r, self.window()))]
        c = Card(); c.box.addWidget(make_table(hd, rows, tone_cols=(6,), actions=acts)); self.body.addWidget(c)


class ClassesView(BasePage):
    TITLE = "Lớp học"
    CLS = [("Lớp 10A", "Cô Lan", 32, "T2-T4-T6 · 18:00", 95, "ok"), ("Lớp 10B", "Thầy Minh", 30, "T3-T5 · 18:00", 92, "info"),
           ("Lớp 11A", "Cô Hoa", 28, "T2-T4-T6 · 19:30", 90, "brass"), ("Lớp 11B", "Thầy Nam", 34, "T3-T5 · 19:30", 88, "wait"),
           ("Lớp 12A", "Cô Thu", 26, "T7-CN · 08:00", 94, "ok"), ("Lớp 12B", "Thầy Đức", 24, "T7-CN · 14:00", 91, "info")]

    def build(self, d):
        nb = PrimaryPushButton("+ Tạo lớp"); nb.clicked.connect(lambda: D.class_form(self.window())); self.head.addWidget(nb)
        g = QGridLayout(); g.setSpacing(14)
        for i, (n, gv, si, lich, pct, tone) in enumerate(self.CLS):
            c = Card()
            top = QHBoxLayout(); top.addWidget(label(n, "cardTitle")); top.addStretch(); top.addWidget(tag("Đang học", "ok")); c.box.addLayout(top)
            c.box.addWidget(label(f"GV phụ trách: {gv}", "muted")); c.box.addWidget(label(f"Sĩ số {si} · {lich}", "muted"))
            c.box.addWidget(bar_row("Chuyên cần", pct, tone))
            b = QHBoxLayout(); l1 = PushButton("Danh sách"); l2 = PushButton("Sửa lớp")
            l1.clicked.connect(lambda _=False, n=n, si=si: D.roster(n, si, self.window()))
            l2.clicked.connect(lambda _=False, n=n: D.class_form(self.window(), n))
            b.addWidget(l1); b.addWidget(l2); c.box.addLayout(b)
            g.addWidget(c, i // 3, i % 3)
        self.body.addLayout(g)


class SettingsView(BasePage):
    TITLE = "Cài đặt hệ thống"

    def db_btns(self):
        h = QHBoxLayout(); a, b = PushButton("Sao lưu ngay"), PushButton("Khôi phục")
        a.clicked.connect(lambda: D.confirm(self.window(), "Sao lưu dữ liệu", "Đã sao lưu data/attendance.db thành công.", info=True))
        b.clicked.connect(lambda: D.confirm(self.window(), "Khôi phục dữ liệu", "Khôi phục sẽ ghi đè dữ liệu hiện tại. Tiếp tục?", "Khôi phục", danger=True))
        h.addWidget(a); h.addWidget(b); return h

    def build(self, d):
        sv = PrimaryPushButton("Lưu thay đổi")
        sv.clicked.connect(lambda: D.confirm(self.window(), "Cài đặt", "Đã lưu cài đặt hệ thống.", info=True)); self.head.addWidget(sv)
        extra = ("Ca làm việc", [("Giờ vào ca", "08:00"), ("Giờ tan ca", "17:00"), ("Cho phép đi muộn", "15 phút")]) if self.block == "staff" \
            else ("Lịch điểm danh", [("Mở điểm danh trước giờ học", "15 phút"), ("Tính muộn sau", "10 phút"), ("Báo phụ huynh khi vắng", "Bật")])
        groups = [extra, ("Nhận diện & chống giả mạo", [("Face Recognition", "InsightFace (ArcFace)"), ("Anti-spoofing", "MiniFASNetV2"),
                  ("Ngưỡng cosine", "0.60"), ("Active liveness", "MediaPipe · EAR / Head Pose" if self.block == "staff" else "Không áp dụng")]),
                  ("Camera", [("Thiết bị", "Webcam 1"), ("Độ phân giải", "1280 × 720"), ("FPS", "30")]),
                  ("Database & sao lưu", [("Trạng thái", "Đã kết nối"), ("Tệp dữ liệu", "data/attendance.db"), ("Sao lưu gần nhất", "08/09/2026 10:24")])]
        g = QGridLayout(); g.setSpacing(14)
        for i, (t, rows) in enumerate(groups):
            c = Card(t)
            for k, v in rows: kv(c, k, v, T.SAGE if v.startswith("Đã") else None)
            if t.startswith("Database"): c.box.addLayout(self.db_btns())
            c.box.addStretch(); g.addWidget(c, i // 2, i % 2)
        n = Card("Thông báo Telegram")
        for k, on in [("Bật Telegram Bot", True), ("Báo khi đi muộn", True), ("Báo khi vắng", False), ("Báo cáo cuối ngày", True)]: switch_row(n, k, on)
        g.addWidget(n, 2, 0, 1, 2)
        self.body.addLayout(g)





class AccountsView(BasePage):
    TITLE = "Tài khoản & phân quyền"
    ACC = [("admin", "Quản trị viên", "Admin", "Toàn hệ thống", "Hoạt động"),
           ("hr01", "Nguyễn Thị Hương", "Nhân viên HR", "Khối văn phòng", "Hoạt động"),
           ("hr02", "Lê Thu Trang", "Nhân viên HR", "Khối văn phòng", "Đã khóa"),
           ("hv01", "Trần Văn Nam", "Nhân viên học vụ", "Khối học viên", "Hoạt động")]
    MATRIX = [("Khối văn phòng", "✓", "✓", "—"), ("Khối học viên", "✓", "—", "✓"), ("Duyệt nghỉ phép", "✓", "✓", "—"),
              ("Quản lý lớp học", "✓", "—", "✓"), ("Tài khoản & phân quyền", "✓", "—", "—"), ("Cài đặt hệ thống", "✓", "—", "—")]

    def build(self, d):
        add = PrimaryPushButton("+ Thêm tài khoản"); add.clicked.connect(lambda: D.account_form(self.window())); self.head.addWidget(add)
        a = Card("Danh sách tài khoản")
        a.box.addWidget(make_table(["Tài khoản", "Họ tên", "Vai trò", "Phạm vi", "Trạng thái"], self.ACC, tone_cols=(4,),
                        actions=lambda r: [("Sửa", "brass", lambda: D.account_form(self.window(), r[0])),
                                           ("Mở khóa" if r[4] == "Đã khóa" else "Khóa", "late",
                                            lambda: D.confirm(self.window(), "Khóa tài khoản" if r[4] != "Đã khóa" else "Mở khóa tài khoản", f"Xác nhận thay đổi trạng thái tài khoản {r[0]}?", danger=True))]))
        m = Card("Ma trận phân quyền"); m.box.addWidget(make_table(["Chức năng", "Admin", "Nhân viên HR", "Nhân viên học vụ"], self.MATRIX))
        self.body.addWidget(a); self.body.addWidget(m)
