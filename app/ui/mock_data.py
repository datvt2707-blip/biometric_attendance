"""
mock_data.py — DỮ LIỆU MẪU ĐỂ DỰNG GIAO DIỆN
LÀM GÌ   : Số liệu giả cho Tổng quan, Chấm công, danh sách nhân viên/học viên của 2 khối.
CÔNG NGHỆ: Python thuần (dict).
NỐI SAU  : Xóa file này, thay bằng dữ liệu từ services/*.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
DATA = {
"staff": dict(name="Khối nhân viên", att="Chấm công", people="Nhân sự",
 stats=[("Tổng nhân viên","94","+2 so với tuần trước","ok"),("Có mặt hôm nay","79","84% · tăng","ok"),
        ("Đi muộn","7","7% quân số","wait"),("Vắng","8","9% quân số","late")],
 trend=[80,84,79,86,88,91,84], trend_t="Tỷ lệ nhân viên check-in đúng giờ",
 bars_t="Tỷ lệ theo phòng ban",
 bars=[("Kỹ thuật",94,"ok"),("Kinh doanh",88,"info"),("Nhân sự",97,"brass"),("Vận hành",81,"wait")],
 acts=[("NA","Nguyễn Văn A","Check-in · 08:12","Có mặt"),("TB","Trần Thị B","Check-in · 08:06","Có mặt"),
       ("LC","Lê Văn C","Check-out · 17:02","Hoàn thành"),("PD","Phạm Thị D","Check-in · 08:20","Đi muộn")],
 who=("Nguyễn Văn A","NV001 · Phòng Kỹ thuật","NA"),
 steps=["Nhìn thẳng","Chớp mắt","Quay trái","Quay phải"], cur=1,
 st_title="Yêu cầu hành động (Active Liveness)", st_hint="Vui lòng nhìn thẳng và chớp mắt",
 live="Liveness (Active)", match="MATCH (98%)", chip="Nhận diện thành công",
 btns=["Check-in (Vào ca)","Check-out (Tan ca)"],
 lh=["Họ tên","Phòng ban","Thời gian","Hoạt động","Trạng thái"],
 log=[("Nguyễn Văn A","Kỹ thuật","07:58","Check-in","Thành công"),("Trần Thị B","Kinh doanh","08:12","Check-in","Thành công"),
      ("Lê Văn C","Nhân sự","08:45","Check-in","Đi muộn")],
 ph=["Mã","Họ tên","Phòng ban","Trạng thái","Khuôn mặt"],
 rows=[("NV001","Nguyễn Văn A","Kỹ thuật","Đang làm","Đã đăng ký"),("NV002","Trần Thị B","Kinh doanh","Nghỉ phép","Đã đăng ký"),
       ("NV003","Lê Văn C","Nhân sự","Đang làm","Đã đăng ký"),("NV004","Phạm Thị D","Kế toán","Đã nghỉ việc","Đã đăng ký"),
       ("NV005","Hoàng Minh E","Kỹ thuật","Đang làm","Chưa đăng ký")]),
"student": dict(name="Khối học viên", att="Điểm danh", people="Học viên",
 stats=[("Tổng học viên","312","+14 học viên mới","ok"),("Đã điểm danh","286","92% sĩ số","ok"),
        ("Chưa điểm danh","18","6% sĩ số","wait"),("Đi muộn","8","3% sĩ số","late")],
 trend=[88,90,86,92,91,94,92], trend_t="Tỷ lệ học viên được điểm danh",
 bars_t="Theo lớp / khóa",
 bars=[("Lớp 10A",95,"ok"),("Lớp 10B",92,"info"),("Lớp 11A",90,"brass"),("Lớp 11B",88,"wait"),("Lớp 12A",94,"ok")],
 acts=[("MT","Nguyễn Minh T","Điểm danh · 08:03","Có mặt"),("TN","Đỗ Thảo N","Điểm danh · 07:56","Có mặt"),
       ("QH","Lê Quang H","Chưa điểm danh","Chưa"),("TL","Phạm Thị L","Điểm danh · 07:48","Có mặt")],
 who=("Trần Thị B","SV001 · Lớp 11A","TB"),
 steps=["Phát hiện","Nhận diện","Chống giả mạo","Liveness","Điểm danh"], cur=3,
 st_title="Trạng thái hiện tại", st_hint="Đang nhận diện khuôn mặt",
 live="Liveness (Passive)", match="MATCH (96%)", chip="Đang nhận diện…",
 btns=["Điểm danh (Check-in)"],
 lh=["Họ tên","Lớp","Thời gian","Trạng thái","Hoạt động"],
 log=[("Trần Thị B","11A","07:32","Có mặt","Check-in"),("Nguyễn Minh T","10B","07:45","Có mặt","Check-in"),
      ("Lê Quang H","12A","07:58","Có mặt","Check-in")],
 ph=["Mã","Họ tên","Lớp","Trạng thái","Khuôn mặt"],
 rows=[("SV001","Trần Thị B","11A","Đang học","Đã đăng ký"),("SV002","Nguyễn Minh T","10B","Đang học","Đã đăng ký"),
       ("SV003","Lê Quang H","12A","Bảo lưu","Đã đăng ký"),("SV004","Phạm Thị L","11B","Đang học","Đã đăng ký"),
       ("SV005","Đỗ Thảo N","10A","Đang học","Chưa đăng ký")]),
}
