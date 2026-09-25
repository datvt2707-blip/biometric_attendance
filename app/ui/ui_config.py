"""Static labels and presentation text for the existing UI blocks.

Business records and metrics are loaded through services from SQLite. This
module contains only screen wording and column names.
"""

UI_CONFIG = {
    "staff": {
        "name": "Khối nhân viên",
        "att": "Chấm công",
        "people": "Nhân sự",
        "chip": "Đang chờ khuôn mặt",
        "st_title": "Quy trình nhận diện",
        "st_hint": "Kết quả hiển thị từ camera và dữ liệu đã đăng ký",
        "steps": ["Nhận diện", "Xác thực chuyển động", "Chấm công"],
        "cur": 0,
        "btns": ["Check-in (Vào ca)", "Check-out (Tan ca)"],
        "lh": ["Họ tên", "Phòng ban", "Ngày", "Thời gian", "Trạng thái"],
        "ph": ["Mã", "Họ tên", "Phòng ban", "Trạng thái", "Khuôn mặt"],
    },
    "student": {
        "name": "Khối học viên",
        "att": "Điểm danh",
        "people": "Học viên",
        "chip": "Đang chờ khuôn mặt",
        "st_title": "Quy trình nhận diện",
        "st_hint": "Kết quả hiển thị từ camera và dữ liệu đã đăng ký",
        "steps": ["Nhận diện", "Xác thực chuyển động", "Điểm danh"],
        "cur": 0,
        "btns": ["Điểm danh (Check-in)"],
        "lh": ["Họ tên", "Lớp", "Ngày", "Trạng thái", "Hoạt động"],
        "ph": ["Mã", "Họ tên", "Lớp", "Trạng thái", "Khuôn mặt"],
    },
}
