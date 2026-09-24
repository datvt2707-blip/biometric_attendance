"""
session.py — PHIÊN ĐĂNG NHẬP + PHÂN QUYỀN (mới ở mức giao diện)
LÀM GÌ   : Lưu vai trò đang đăng nhập và bảng ROLES (khối nào được vào, có Cài đặt/Tài khoản không).
CÔNG NGHỆ: Python thuần, không dùng Qt.
NGHIỆP VỤ: Phân quyền Admin / Nhân viên HR / Nhân viên học vụ.
NỐI SAU  : authentication_service + account_repository sẽ ghi vai trò thật vào đây.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
ROLES = {
    "admin":  dict(name="Admin", title="Quản trị viên", blocks=["staff", "student"], settings=True, accounts=True),
    "hr":     dict(name="Nhân viên HR", title="Khối văn phòng", blocks=["staff"], settings=False, accounts=False),
    "hocvu":  dict(name="Nhân viên học vụ", title="Khối học viên", blocks=["student"], settings=False, accounts=False),
}
current = {"role": "admin"}


def role():
    return ROLES[current["role"]]
