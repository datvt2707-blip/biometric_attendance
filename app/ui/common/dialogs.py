"""
dialogs.py — TẤT CẢ POPUP VÀ FORM
LÀM GÌ   : Dialog (khung), form/form_dialog (form nhiều cột), confirm (hộp xác nhận), EnrollmentDialog (đăng ký
             khuôn mặt 4 mẫu), person_detail, leave_form, leave_detail, account_form, class_form, roster, export.
CÔNG NGHỆ: Qt Widgets (QDialog, QGridLayout, QTextEdit) + QSS toàn cục trong theme.py. Không vẽ bằng QPainter
             (khung camera và các bước xoay mặt lấy từ widgets.py).
NGHIỆP VỤ: Đăng ký khuôn mặt, tạo đơn nghỉ, thêm/sửa tài khoản, tạo/sửa lớp, xem sĩ số, xuất dữ liệu, duyệt/từ chối.
NỐI SAU  : Khi bấm Lưu (dialog.exec() trả về true) thì gọi service tương ứng.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit
from app.ui import theme as T
from app.ui.common.widgets import (Card, label, CameraView, StepsBar, Bar, make_table,
                                   PrimaryPushButton, PushButton, LineEdit, ComboBox)

DATE, PHONE, MAIL = "dd/mm/yyyy", "09xx xxx xxx", "ten@email.com"
STAFF = [("Mã nhân viên", "text", "NV006"), ("Họ và tên", "text", "Nguyễn Văn A"), ("Ngày sinh", "text", DATE),
         ("Giới tính", "combo", ["Nam", "Nữ", "Khác"]), ("Số điện thoại", "text", PHONE), ("Email", "text", MAIL),
         ("Phòng ban", "combo", ["Kỹ thuật", "Kinh doanh", "Nhân sự", "Vận hành", "Kế toán"]), ("Chức vụ", "text", "Nhân viên"),
         ("Ngày vào làm", "text", DATE), ("Địa chỉ", "text", "Số nhà, đường, quận…")]
STUDENT = [("Mã học viên", "text", "SV006"), ("Họ và tên", "text", "Trần Thị B"), ("Ngày sinh", "text", DATE),
           ("Giới tính", "combo", ["Nam", "Nữ", "Khác"]), ("Số điện thoại", "text", PHONE), ("Email", "text", MAIL),
           ("Lớp", "combo", ["10A", "10B", "11A", "11B", "12A"]), ("Khóa", "combo", ["2026 – 2027", "2025 – 2026"]),
           ("Họ tên phụ huynh", "text", "Nguyễn Văn C"), ("SĐT phụ huynh", "text", PHONE)]


def form(fields, cols=2):
    g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10)
    r = c = 0
    for name, kind, opt in fields:
        col = QVBoxLayout(); col.setSpacing(4); col.addWidget(label(name, "muted"))
        if kind == "combo": w = ComboBox(); w.addItems(opt)
        elif kind == "area": w = QTextEdit(); w.setFixedHeight(84); w.setPlaceholderText(opt)
        else: w = LineEdit(); w.setPlaceholderText(opt)
        col.addWidget(w)
        if kind == "area":
            if c: r, c = r + 1, 0
            g.addLayout(col, r, 0, 1, cols); r += 1
        else:
            g.addLayout(col, r, c); c += 1
            if c == cols: r, c = r + 1, 0
    for i in range(cols): g.setColumnStretch(i, 1)
    return g


def kvs(card, rows):
    for k, v in rows:
        h = QHBoxLayout(); h.addWidget(label(k, "muted")); h.addStretch(); h.addWidget(label(v)); card.box.addLayout(h)


class Dialog(QDialog):
    def __init__(self, parent, title, sub=None, width=560):
        super().__init__(parent)
        self.setWindowTitle(title); self.setMinimumWidth(width)
        self.v = QVBoxLayout(self); self.v.setContentsMargins(26, 24, 26, 20); self.v.setSpacing(14)
        self.v.addWidget(label(title, "h1"))
        if sub: self.v.addWidget(label(sub, "muted"))

    def footer(self, ok="Lưu", cancel="Hủy", danger=False):
        row = QHBoxLayout(); row.addStretch()
        if cancel: c = PushButton(cancel); c.clicked.connect(self.reject); row.addWidget(c)
        o = PrimaryPushButton(ok); o.setObjectName("danger" if danger else "primary"); o.clicked.connect(self.accept); row.addWidget(o)
        self.v.addLayout(row)


def form_dialog(parent, title, fields, ok="Lưu", sub=None, cols=2, width=640):
    d = Dialog(parent, title, sub, width); d.v.addLayout(form(fields, cols)); d.footer(ok); return d.exec()


def confirm(parent, title, msg, ok="Xác nhận", reason=False, danger=False, info=False):
    d = Dialog(parent, title, None, 460)
    m = label(msg); m.setWordWrap(True); d.v.addWidget(m)
    if reason:
        t = QTextEdit(); t.setFixedHeight(84); t.setPlaceholderText("Nhập lý do…"); d.v.addWidget(t)
    d.footer("Đóng" if info else ok, None if info else "Hủy", danger)
    return d.exec()


class EnrollmentDialog(Dialog):
    def __init__(self, d, parent=None, title="Đăng ký khuôn mặt"):
        super().__init__(parent, title, "Nhập thông tin cá nhân và thu thập mẫu khuôn mặt", 1100)
        h = QHBoxLayout(); h.setSpacing(16)
        left = Card()
        left.box.addWidget(CameraView("Đang thu thập mẫu…"), 1)
        left.box.addWidget(label("Xoay mặt theo hướng dẫn", "cardTitle"))
        left.box.addWidget(StepsBar(["Nhìn thẳng", "Quay trái", "Quay phải", "Ngẩng lên"], 3))
        row = QHBoxLayout(); rt = PushButton("Chụp lại mẫu"); cp = PrimaryPushButton("Chụp mẫu 4 / 4")
        row.addWidget(rt); row.addWidget(cp); left.box.addLayout(row)
        right = Card("Thông tin cá nhân")
        right.box.addLayout(form(STAFF if d["name"].endswith("nhân viên") else STUDENT))
        right.box.addWidget(label("Đã thu 3 / 4 mẫu khuôn mặt", "muted")); right.box.addWidget(Bar(75, T.BRASS))
        right.box.addWidget(label("Chất lượng ảnh: Tốt · Ánh sáng: Đủ", "muted", T.SAGE))
        right.box.addWidget(label("Embedding: 3 / 4 vector · 512 chiều. Mỗi mẫu được lưu thành 1 vector để so khớp khi chấm công.", "muted"))
        h.addWidget(left, 4); h.addWidget(right, 5); self.v.addLayout(h); self.footer("Lưu khuôn mặt")


def enroll(d, parent, title="Đăng ký khuôn mặt"): return EnrollmentDialog(d, parent, title).exec()


def person_detail(d, row, parent):
    dlg = Dialog(parent, f"Hồ sơ — {row[1]}", f"{row[0]} · {row[2]}", 720)
    c = Card("Thông tin")
    kvs(c, [("Mã", row[0]), ("Họ tên", row[1]), (d["ph"][2], row[2]), ("Ngày sinh", "15/03/1995"), ("Số điện thoại", "0912 345 678"),
            ("Email", "email@example.com"), ("Trạng thái", row[3]), ("Khuôn mặt", row[4]), ("Embedding", "4 vector · 512 chiều")])
    h = Card("Lịch sử gần đây"); h.box.addWidget(make_table(d["lh"], d["log"], tone_cols=(3, 4)))
    dlg.v.addWidget(c); dlg.v.addWidget(h); dlg.footer("Sửa thông tin", "Đóng")
    if dlg.exec(): enroll(d, parent, "Sửa thông tin")


def leave_form(block, parent):
    if block == "staff":
        f = [("Nhân viên", "combo", ["NV001 – Nguyễn Văn A", "NV002 – Trần Thị B"]),
             ("Loại nghỉ", "combo", ["Nghỉ phép năm", "Nghỉ ốm", "Nghỉ không lương", "Nghỉ thai sản"]),
             ("Từ ngày", "text", DATE), ("Đến ngày", "text", DATE), ("Người bàn giao", "text", "Họ tên"),
             ("Tệp đính kèm", "text", "Chọn tệp…"), ("Lý do", "area", "Nhập lý do nghỉ…")]
        return form_dialog(parent, "Tạo đơn nghỉ phép", f, "Gửi đơn")
    f = [("Học viên", "combo", ["SV001 – Trần Thị B", "SV002 – Nguyễn Minh T"]), ("Lớp", "combo", ["10A", "10B", "11A", "11B", "12A"]),
         ("Ngày nghỉ", "text", DATE), ("Số buổi nghỉ", "text", "1"), ("Người nộp đơn", "combo", ["Phụ huynh", "Học viên"]),
         ("SĐT liên hệ", "text", PHONE), ("Lý do", "area", "Nhập lý do nghỉ…"), ("Minh chứng", "text", "Chọn tệp…")]
    return form_dialog(parent, "Tạo đơn nghỉ học", f, "Gửi đơn")


def leave_detail(headers, row, parent):
    d = Dialog(parent, "Chi tiết đơn", None, 520); c = Card()
    kvs(c, list(zip(headers, row))); kvs(c, [("Người duyệt", "Admin"), ("Ngày tạo đơn", "07/09/2026")])
    d.v.addWidget(c); d.footer("Đóng", None); return d.exec()


def account_form(parent, edit=None):
    f = [("Tên đăng nhập", "text", "hr03"), ("Họ và tên", "text", "Nguyễn Thị Hương"), ("Email", "text", MAIL), ("Số điện thoại", "text", PHONE),
         ("Vai trò", "combo", ["Nhân viên HR", "Nhân viên học vụ", "Admin"]), ("Phạm vi", "combo", ["Khối văn phòng", "Khối học viên", "Toàn hệ thống"]),
         ("Mật khẩu tạm", "text", "Tự sinh mật khẩu…"), ("Trạng thái", "combo", ["Hoạt động", "Đã khóa"])]
    return form_dialog(parent, f"Sửa tài khoản — {edit}" if edit else "Thêm tài khoản", f, "Lưu tài khoản")


def class_form(parent, edit=None):
    f = [("Tên lớp", "text", "Lớp 12C"), ("Khóa", "combo", ["2026 – 2027", "2025 – 2026"]), ("Giáo viên phụ trách", "text", "Cô Lan"),
         ("Phòng học", "text", "P.301"), ("Lịch học", "combo", ["T2 – T4 – T6", "T3 – T5", "T7 – CN"]), ("Giờ học", "text", "18:00 – 19:30"),
         ("Sĩ số tối đa", "text", "35"), ("Ngày khai giảng", "text", DATE), ("Ghi chú", "area", "Ghi chú về lớp…")]
    return form_dialog(parent, f"Sửa lớp — {edit}" if edit else "Tạo lớp mới", f, "Lưu lớp")


def roster(name, si, parent):
    d = Dialog(parent, f"Sĩ số {name}", f"{si} học viên · Có mặt {si - 2} · Vắng 1 · Đi muộn 1", 760)
    rows = [("SV001", "Trần Thị B", "Có mặt", "07:32", ""), ("SV002", "Nguyễn Minh T", "Có mặt", "07:45", ""), ("SV003", "Lê Quang H", "Đi muộn", "08:12", "Kẹt xe"),
            ("SV004", "Phạm Thị L", "Vắng", "—", "Chưa có đơn"), ("SV005", "Đỗ Thảo N", "Có phép", "—", "Đơn nghỉ đã duyệt"), ("SV006", "Vũ Hải F", "Có mặt", "07:50", "")]
    c = Card(); c.box.addWidget(make_table(["Mã", "Học viên", "Trạng thái", "Giờ vào", "Ghi chú"], rows, tone_cols=(2,)))
    d.v.addWidget(c); d.footer("Xác nhận sĩ số", "Đóng"); return d.exec()


def export(parent):
    f = [("Khoảng thời gian", "combo", ["Hôm nay", "Tuần này", "Tháng này", "Tùy chọn"]), ("Định dạng", "combo", ["Excel (.xlsx)", "CSV", "PDF"]),
         ("Từ ngày", "text", DATE), ("Đến ngày", "text", DATE)]
    return form_dialog(parent, "Xuất dữ liệu", f, "Xuất file", width=520)
