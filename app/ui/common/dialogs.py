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
from datetime import datetime

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit,
                               QFileDialog, QLineEdit)
from app.ui import theme as T
from app.camera.camera_manager import CameraPreviewController
from app.services.enrollment_service import (
    EnrollmentConflictError,
    EnrollmentCaptureSession,
    EnrollmentService,
    EnrollmentValidationError,
)
from app.database.database import connect
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.user_repository import UserRepository
from app.ui.common.widgets import (Card, label, CameraView, StepsBar, Bar, make_table,
                                   PrimaryPushButton, PushButton, LineEdit, ComboBox, DateEdit)

DATE, PHONE, MAIL = "dd/mm/yyyy", "09xx xxx xxx", "ten@email.com"
STAFF = [("Mã nhân viên", "text", ""), ("Họ và tên", "text", ""), ("Ngày sinh", "date", ""),
         ("Giới tính", "combo", ["Nam", "Nữ", "Khác"]), ("Số điện thoại", "text", PHONE), ("Email", "text", MAIL),
         ("Phòng ban", "combo", []), ("Chức vụ", "text", ""),
         ("Ngày vào làm", "date", ""), ("Địa chỉ", "text", "Số nhà, đường, quận…")]
STUDENT = [("Mã học viên", "text", ""), ("Họ và tên", "text", ""), ("Ngày sinh", "date", ""),
           ("Giới tính", "combo", ["Nam", "Nữ", "Khác"]), ("Số điện thoại", "text", PHONE), ("Email", "text", MAIL),
           ("Lớp", "combo", []), ("Khóa", "combo", []),
           ("Họ tên phụ huynh", "text", ""), ("SĐT phụ huynh", "text", PHONE)]


def form(fields, cols=2):
    g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10)
    g.field_widgets = []
    r = c = 0
    for name, kind, opt in fields:
        col = QVBoxLayout(); col.setSpacing(4); col.addWidget(label(name, "muted"))
        if kind == "combo": w = ComboBox(); w.addItems(opt)
        elif kind == "area": w = QTextEdit(); w.setFixedHeight(84); w.setPlaceholderText(opt)
        elif kind == "date": w = DateEdit(opt)
        else: w = LineEdit(); w.setPlaceholderText(opt)
        col.addWidget(w); g.field_widgets.append(w)
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

    def footer(self, ok="Lưu", cancel="Hủy", danger=False, *, auto_accept=True):
        row = QHBoxLayout(); row.addStretch()
        if cancel: c = PushButton(cancel); c.clicked.connect(self.reject); row.addWidget(c)
        o = PrimaryPushButton(ok); o.setObjectName("danger" if danger else "primary")
        if auto_accept: o.clicked.connect(self.accept)
        row.addWidget(o)
        self.v.addLayout(row)
        return o


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
    SAMPLE_POSES = ("Nhìn thẳng", "Quay trái", "Quay phải", "Ngẩng lên")

    def __init__(self, d, parent=None, title="Đăng ký khuôn mặt", *, service=None):
        super().__init__(parent, title, "Nhập thông tin cá nhân và thu thập mẫu khuôn mặt", 1100)
        self.kind = "employee" if d["name"].endswith("nhân viên") else "student"
        self.service = service or EnrollmentService()
        self.capture_session = EnrollmentCaptureSession()
        self.samples = self.capture_session.samples
        self._pending_index = None
        self._saving = False
        self._model_failed = False

        h = QHBoxLayout(); h.setSpacing(16)
        left = Card()
        self.camera_preview = CameraView("Đang thu thập mẫu…")
        left.box.addWidget(self.camera_preview, 1)
        self._camera_controller = CameraPreviewController(
            self.camera_preview, parent=self, enable_face_analysis=True
        )
        self._camera_controller.sample_analysis_ready.connect(self._on_sample_analysis)
        self._camera_controller.sample_analysis_error.connect(self._on_sample_error)
        self._camera_controller.face_analysis_error.connect(self._on_model_error)
        left.box.addWidget(label("Xoay mặt theo hướng dẫn", "cardTitle"))
        self.steps = StepsBar(list(self.SAMPLE_POSES), 0)
        left.box.addWidget(self.steps)
        row = QHBoxLayout(); self.retake_button = PushButton("Chụp lại mẫu")
        self.capture_button = PrimaryPushButton("Chụp mẫu 1 / 4")
        self.retake_button.clicked.connect(self._retake_last)
        self.capture_button.clicked.connect(self._capture_next)
        row.addWidget(self.retake_button); row.addWidget(self.capture_button); left.box.addLayout(row)

        right = Card("Thông tin cá nhân")
        fields = STAFF if self.kind == "employee" else STUDENT
        self.profile_form = form(fields)
        self.field_widgets = self.profile_form.field_widgets
        self._available_classes = []
        self._missing_required_class = False
        try:
            connection = connect()
            try:
                if self.kind == "employee":
                    departments = UserRepository(connection).list_departments()
                    self.field_widgets[6].clear()
                    self.field_widgets[6].addItem("")
                    self.field_widgets[6].addItems([row["name"] for row in departments])
                else:
                    self._available_classes = [dict(row) for row in ClassRepository(connection).list_classes(status="active")]
                    self._missing_required_class = not self._available_classes
                    class_box, year_box = self.field_widgets[6], self.field_widgets[7]
                    class_box.clear(); year_box.clear()
                    names = list(dict.fromkeys(row["class_name"] for row in self._available_classes))
                    class_box.addItems(names or [""])
                    def update_years(index=0):
                        selected = class_box.currentText()
                        years = [row["academic_year"] for row in self._available_classes if row["class_name"] == selected]
                        year_box.clear(); year_box.addItems(list(dict.fromkeys(years)) or [""])
                    class_box.currentIndexChanged.connect(update_years)
                    update_years()
            finally:
                connection.close()
        except Exception as exc:
            self.status_label.setText(f"Không tải được danh mục phòng ban/lớp từ cơ sở dữ liệu: {exc}")
        right.box.addLayout(self.profile_form)
        self.progress_label = label("Đã thu 0 / 4 mẫu khuôn mặt", "muted")
        right.box.addWidget(self.progress_label)
        self.progress_bar = Bar(0, T.BRASS)
        right.box.addWidget(self.progress_bar)
        initial_status = ("Chưa có lớp đang hoạt động trong cơ sở dữ liệu; cần tạo lớp trước khi đăng ký học viên."
                          if self._missing_required_class else
                          "Đang chờ camera. Tư thế được hướng dẫn theo thứ tự, chưa xác minh tự động.")
        self.status_label = label(initial_status, "muted")
        self.status_label.setWordWrap(True)
        right.box.addWidget(self.status_label)
        self.embedding_label = label("Embedding: chưa có mẫu được chấp nhận.", "muted")
        right.box.addWidget(self.embedding_label)
        h.addWidget(left, 4); h.addWidget(right, 5); self.v.addLayout(h)
        self.save_button = self.footer("Lưu khuôn mặt", auto_accept=False)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save_enrollment)
        self._refresh_capture_controls()

    def _capture_next(self):
        if self._pending_index is not None or len(self.samples) >= 4:
            return
        index = len(self.samples)
        if not self._camera_controller.capture_sample(index):
            self.status_label.setText("Đang chờ frame camera hợp lệ…")
            return
        self._pending_index = index
        self.capture_button.setEnabled(False)
        self.status_label.setText(f"Đang kiểm tra mẫu {index + 1}: {self.SAMPLE_POSES[index]}…")

    def _on_sample_analysis(self, index, frame, result):
        if index != self._pending_index or index != len(self.samples):
            return
        self._pending_index = None
        if result.status != "face_selected" or result.face_count != 1 or result.selected is None or result.embedding is None:
            self.status_label.setText(f"Mẫu bị từ chối: {result.reason or result.status}. Hãy thử lại.")
            self._refresh_capture_controls()
            return
        try:
            sample = self.capture_session.accept(frame, result)
            vector = sample.embedding
            self.status_label.setText(f"Đã nhận mẫu {index + 1}: {self.SAMPLE_POSES[index]}. Tư thế chưa được máy xác minh.")
            self.embedding_label.setText(f"Embedding: {len(self.samples)} / 4 vector · {vector.size} chiều.")
        except (EnrollmentValidationError, ValueError) as exc:
            self.status_label.setText(f"Mẫu bị từ chối: {exc}")
        self._refresh_capture_controls()

    def _on_sample_error(self, index, message):
        if index == self._pending_index:
            self._pending_index = None
            self.status_label.setText(f"Lỗi xử lý mẫu: {message}")
            self._refresh_capture_controls()

    def _on_model_error(self, message):
        self._model_failed = True
        self._pending_index = None
        self.status_label.setText(f"Không nạp hoặc chạy được model khuôn mặt: {message}")
        self._refresh_capture_controls()

    def _retake_last(self):
        if self._pending_index is not None or self._saving or not self.samples:
            return
        self.capture_session.retake_last()
        self.status_label.setText(f"Mẫu {len(self.samples) + 1} cần được chụp lại.")
        self._refresh_capture_controls()

    def _refresh_capture_controls(self):
        count = len(self.samples)
        self.progress_label.setText(f"Đã thu {count} / 4 mẫu khuôn mặt")
        self.progress_bar.pct = count * 25
        self.progress_bar.update()
        self.steps.cur = count
        self.steps.update()
        self.capture_button.setText("Hoàn tất 4 / 4" if count == 4 else f"Chụp mẫu {count + 1} / 4")
        self.capture_button.setEnabled(count < 4 and self._pending_index is None and not self._saving and not self._model_failed and not self._missing_required_class)
        self.retake_button.setEnabled(count > 0 and self._pending_index is None and not self._saving)
        self.save_button.setEnabled(count == 4 and self._pending_index is None and not self._saving and not self._missing_required_class)

    def _field_text(self, index):
        widget = self.field_widgets[index]
        return widget.currentText().strip() if hasattr(widget, "currentText") else widget.text().strip()

    @staticmethod
    def _date_value(value, field_name):
        if not value:
            return None
        for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, pattern).date().isoformat()
            except ValueError:
                continue
        raise EnrollmentValidationError(f"{field_name} phải là một ngày hợp lệ.")

    def _form_data(self):
        gender_text = self._field_text(3)
        gender = {"Nam": "male", "Nữ": "female", "Khác": "other"}.get(gender_text, "unspecified")
        person = {
            "full_name": self._field_text(1),
            "date_of_birth": self._date_value(self._field_text(2), "Ngày sinh"),
            "gender": gender,
            "phone": self._field_text(4) or None,
            "email": self._field_text(5) or None,
        }
        if self.kind == "employee":
            profile = {
                "employee_code": self._field_text(0),
                "department_name": self._field_text(6),
                "job_title": self._field_text(7) or None,
                "hire_date": self._date_value(self._field_text(8), "Ngày vào làm"),
                "address": self._field_text(9) or None,
            }
        else:
            if not self._available_classes:
                raise EnrollmentValidationError("Chưa có lớp đang hoạt động trong cơ sở dữ liệu; không thể đăng ký học viên vào lớp giả.")
            profile = {
                "student_code": self._field_text(0),
                "class_name": self._field_text(6),
                "academic_year": self._field_text(7),
                "guardian_name": self._field_text(8) or None,
                "guardian_phone": self._field_text(9) or None,
            }
        return person, profile

    def _save_enrollment(self):
        if self._saving or len(self.samples) != 4:
            return
        self._saving = True
        self._refresh_capture_controls()
        self.status_label.setText("Đang lưu hồ sơ và bốn mẫu khuôn mặt…")
        try:
            person, profile = self._form_data()
            result = (self.service.enroll_employee(person, profile, self.samples) if self.kind == "employee"
                      else self.service.enroll_student(person, profile, self.samples))
        except (EnrollmentValidationError, EnrollmentConflictError, OSError, ValueError) as exc:
            self.status_label.setText(f"Chưa lưu được: {exc}")
            self._saving = False
            self._refresh_capture_controls()
            return
        except Exception as exc:
            self.status_label.setText(f"Lỗi cơ sở dữ liệu khi lưu: {exc}")
            self._saving = False
            self._refresh_capture_controls()
            return
        self.status_label.setText(f"Đã lưu đủ 4 mẫu, embedding {result['dimension']} chiều.")
        # done() owns camera/worker teardown for every close path.
        super().accept()

    def done(self, result):
        if hasattr(self, "_camera_controller"):
            self._camera_controller.shutdown()
        super().done(result)


def enroll(d, parent, title="Đăng ký khuôn mặt", *, on_saved=None):
    dialog = EnrollmentDialog(d, parent, title)
    result = dialog.exec()
    if result == QDialog.DialogCode.Accepted and on_saved is not None:
        on_saved()
    return result


def edit_person(block, code, parent, *, on_saved=None):
    from app.services.employee_service import EmployeeService
    from app.services.student_service import StudentService
    staff = block == "staff"
    service = EmployeeService() if staff else StudentService()
    record = service.get_by_code(code)
    if record is None:
        confirm(parent, "Không tìm thấy hồ sơ", f"Không còn hồ sơ có mã {code}.", info=True)
        return 0
    person = record["person"]
    profile = record["employee"] if staff else record["student"]
    dialog = Dialog(parent, f"Sửa hồ sơ · {code}", "Các thay đổi chỉ cập nhật thông tin hồ sơ.", 720)
    fields = [("Họ và tên", "text", ""), ("Ngày sinh", "date", ""),
              ("Giới tính", "combo", ["unspecified", "male", "female", "other"]),
              ("Điện thoại", "text", ""), ("Email", "text", "")]
    if staff:
        fields += [("Mã nhân viên", "text", ""), ("Phòng ban", "combo", []), ("Chức vụ", "text", ""),
                   ("Ngày vào làm", "date", ""), ("Địa chỉ", "text", ""),
                   ("Trạng thái", "combo", ["active", "on_leave", "terminated", "inactive"])]
    else:
        fields += [("Mã học viên", "text", ""), ("Lớp đang học", "combo", []),
                   ("Tên người giám hộ", "text", ""), ("Điện thoại người giám hộ", "text", ""),
                   ("Trạng thái", "combo", ["active", "reserved", "graduated", "inactive"])]
    grid = form(fields); widgets = grid.field_widgets; dialog.v.addLayout(grid)
    if staff:
        departments = service.departments()
        widgets[6].addItems([row["name"] for row in departments])
        selected = next((i for i, row in enumerate(departments) if row["department_id"] == profile["department_id"]), -1)
        if selected >= 0: widgets[6].setCurrentIndex(selected)
    else:
        classes = service.classes()
        widgets[6].addItems([f"{row['class_name']} · {row['academic_year']}" for row in classes])
        selected = next((i for i, row in enumerate(classes) if row["class_id"] == record["class_id"]), -1)
        if selected >= 0: widgets[6].setCurrentIndex(selected)
    common = [person["full_name"], person["date_of_birth"] or "", person["gender"] or "unspecified", person["phone"] or "", person["email"] or ""]
    for i, value in enumerate(common):
        if i == 2:
            idx = widgets[i].findText(value)
            if idx >= 0: widgets[i].setCurrentIndex(idx)
        else: widgets[i].setText(str(value))
    if staff:
        values = [profile["employee_code"], profile["job_title"] or "", profile["hire_date"] or "", profile["address"] or "", profile["employment_status"]]
        widgets[5].setText(values[0]); widgets[7].setText(values[1]); widgets[8].setText(values[2]); widgets[9].setText(values[3])
        idx = widgets[10].findText(values[4]); widgets[10].setCurrentIndex(max(0, idx))
    else:
        values = [profile["student_code"], profile["guardian_name"] or "", profile["guardian_phone"] or "", profile["student_status"]]
        widgets[5].setText(values[0]); widgets[7].setText(values[1]); widgets[8].setText(values[2])
        idx = widgets[9].findText(values[3]); widgets[9].setCurrentIndex(max(0, idx))
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    save = dialog.footer("Lưu thay đổi", auto_accept=False)
    def persist():
        try:
            person_data = {"full_name": widgets[0].text().strip(), "date_of_birth": widgets[1].text().strip() or None,
                           "gender": widgets[2].currentText(), "phone": widgets[3].text().strip() or None,
                           "email": widgets[4].text().strip() or None}
            if staff:
                department = next((row for row in departments if row["name"] == widgets[6].currentText()), None)
                employee_data = {"employee_code": widgets[5].text().strip(), "department_id": department["department_id"] if department else None,
                                 "job_title": widgets[7].text().strip() or None, "hire_date": widgets[8].text().strip() or None,
                                 "address": widgets[9].text().strip() or None, "employment_status": widgets[10].currentText()}
                service.save(person_data, employee_data, employee_id=profile["employee_id"])
            else:
                class_row = next((row for row in classes if f"{row['class_name']} · {row['academic_year']}" == widgets[6].currentText()), None)
                student_data = {"student_code": widgets[5].text().strip(), "guardian_name": widgets[7].text().strip() or None,
                                "guardian_phone": widgets[8].text().strip() or None, "student_status": widgets[9].currentText()}
                service.save(person_data, student_data, student_id=profile["student_id"], class_id=class_row["class_id"] if class_row else None)
            dialog.accept()
        except Exception as exc: error.setText(str(exc))
    save.clicked.connect(persist)
    result = dialog.exec()
    if result and on_saved: on_saved()
    return result


def person_detail(block, code, parent, *, on_saved=None):
    from app.services.employee_service import EmployeeService
    from app.services.student_service import StudentService
    staff = block == "staff"
    record = (EmployeeService() if staff else StudentService()).get_by_code(code)
    if record is None:
        return confirm(parent, "Hồ sơ không tồn tại", f"Không tìm thấy {code}.", info=True)
    profile = record["employee"] if staff else record["student"]
    person = record["person"]
    dialog = Dialog(parent, f"Hồ sơ · {person['full_name']}", code, 600)
    info = Card("Thông tin lưu trong cơ sở dữ liệu")
    rows = [("Mã", code), ("Họ tên", person["full_name"]), ("Ngày sinh", person["date_of_birth"] or "—"),
            ("Điện thoại", person["phone"] or "—"), ("Email", person["email"] or "—"),
            ("Trạng thái", profile["employment_status"] if staff else profile["student_status"]),
            ("Khuôn mặt", "Đã đăng ký" if _has_face(person["person_id"]) else "Chưa đăng ký")]
    kvs(info, rows); dialog.v.addWidget(info)
    edit = dialog.footer("Sửa thông tin", "Đóng", auto_accept=False)
    edit.clicked.connect(lambda: (dialog.accept(), edit_person(block, code, parent, on_saved=on_saved)))
    return dialog.exec()


def _has_face(person_id):
    from app.database.database import connect
    connection = connect()
    try: return connection.execute("SELECT EXISTS(SELECT 1 FROM face_embeddings WHERE person_id=? AND is_active=1)", (person_id,)).fetchone()[0] == 1
    finally: connection.close()


def leave_form(block, parent, *, on_saved=None):
    from app.database.database import connect
    from app.database.repositories.class_repository import ClassRepository
    from app.database.repositories.user_repository import UserRepository
    from app.services.leave_service import LeaveService
    staff = block == "staff"
    connection = connect()
    try:
        users = UserRepository(connection)
        profiles = users.list_employees(status="active") if staff else users.list_students(status="active")
        people = []
        for record in profiles:
            person = users.get_person(record["person_id"])
            code = record["employee_code"] if staff else record["student_code"]
            people.append((int(record["employee_id"] if staff else record["student_id"]), f"{code} · {person['full_name']}"))
        classes = [dict(row) for row in ClassRepository(connection).list_classes(status="active")] if not staff else []
    finally:
        connection.close()
    title = "Tạo đơn nghỉ phép" if staff else "Tạo đơn nghỉ học"
    dialog = Dialog(parent, title, "Thông tin được lưu vào cơ sở dữ liệu.", 680)
    fields = [("Người nộp", "combo", [display for _id, display in people])]
    if staff:
        fields += [("Loại nghỉ", "combo", ["Nghỉ phép năm", "Nghỉ ốm", "Nghỉ không lương", "Nghỉ thai sản"]),
                   ("Từ ngày", "date", ""), ("Đến ngày", "date", ""),
                   ("Người bàn giao", "text", ""), ("Lý do", "area", "")]
    else:
        fields += [("Lớp", "combo", [f"{row['class_name']} · {row['academic_year']}" for row in classes]), ("Ngày nghỉ", "date", ""),
                   ("Số buổi nghỉ", "text", "1"), ("Người nộp đơn", "combo", ["guardian", "student"]),
                   ("SĐT liên hệ", "text", ""), ("Lý do", "area", "")]
    grid = form(fields); widgets = grid.field_widgets; dialog.v.addLayout(grid)
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    save = dialog.footer("Gửi đơn", auto_accept=False)
    saving = {"active": False}
    def persist():
        if saving["active"]:
            return
        saving["active"] = True
        save.setEnabled(False)
        try:
            if not people:
                raise ValueError("Không có hồ sơ đang hoạt động để chọn.")
            profile_id = people[widgets[0].currentIndex()][0]
            text = lambda index: widgets[index].toPlainText().strip() if hasattr(widgets[index], "toPlainText") else widgets[index].text().strip()
            if staff:
                LeaveService().create_employee_request(profile_id, {
                    "leave_type": widgets[1].currentText(), "start_date": text(2), "end_date": text(3),
                    "handover_person": text(4), "reason": text(5),
                })
            else:
                selected = widgets[1].currentText()
                class_row = next((row for row in classes if f"{row['class_name']} · {row['academic_year']}" == selected), None)
                LeaveService().create_student_request(profile_id, {
                    "class_id": class_row["class_id"] if class_row else None, "leave_date": text(2),
                    "session_count": float(text(3)) if text(3) else None,
                    "submitted_by_type": widgets[4].currentText(), "contact_phone": text(5), "reason": text(6),
                })
            dialog.accept()
        except Exception as exc:
            error.setText(str(exc))
            saving["active"] = False
            save.setEnabled(True)
    save.clicked.connect(persist)
    accepted = dialog.exec()
    if accepted and on_saved:
        on_saved()
    return accepted


def leave_detail(headers, row, parent):
    d = Dialog(parent, "Chi tiết đơn", None, 520); c = Card()
    kvs(c, list(zip(headers, row)))
    d.v.addWidget(c); d.footer("Đóng", None); return d.exec()


def leave_review(block, request_id, decision, headers, row, parent, *, on_saved=None):
    """Approve or reject one pending request through LeaveService.review()."""
    from app.services.leave_service import LeaveService
    approving = decision == "approved"
    dialog = Dialog(parent, "Duyệt đơn" if approving else "Từ chối đơn",
                    "Quyết định được ghi kèm người duyệt và thời điểm; dữ liệu chấm công không bị thay đổi.", 520)
    card = Card(); kvs(card, list(zip(headers, row))); dialog.v.addWidget(card)
    note = QTextEdit(); note.setFixedHeight(84)
    note.setPlaceholderText("Ghi chú duyệt (tùy chọn)" if approving else "Lý do từ chối (bắt buộc)")
    dialog.v.addWidget(note)
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    submit = dialog.footer("Duyệt" if approving else "Từ chối", danger=not approving, auto_accept=False)
    def persist():
        submit.setEnabled(False)
        try:
            LeaveService().review(block, request_id, decision, note=note.toPlainText())
            dialog.accept()
        except Exception as exc:
            error.setText(str(exc))
            submit.setEnabled(True)
    submit.clicked.connect(persist)
    accepted = dialog.exec()
    if accepted and on_saved:
        on_saved()
    return accepted


def account_form(parent, *, on_saved=None):
    """Create one account from the roles stored in the database; password shown once."""
    from app.services.account_service import AccountService
    service = AccountService()
    try:
        roles = service.assignable_roles()
        people = service.linkable_people()
    except Exception as exc:
        return confirm(parent, "Không mở được form tài khoản", str(exc), info=True)
    if not roles:
        return confirm(parent, "Chưa có vai trò",
                       "Cơ sở dữ liệu chưa có vai trò nào; chạy bootstrap trước khi tạo tài khoản.", info=True)
    dialog = Dialog(parent, "Thêm tài khoản",
                    "Mật khẩu được sinh ngẫu nhiên và chỉ hiển thị một lần; hệ thống chỉ lưu bản băm.", 620)
    fields = [("Tên đăng nhập", "text", ""),
              ("Vai trò", "combo", [f"{row['role_name']} ({row['role_code']})" for row in roles]),
              ("Liên kết hồ sơ", "combo", ["— Không liên kết —"] + [row["display"] for row in people])]
    grid = form(fields, cols=1); widgets = grid.field_widgets; dialog.v.addLayout(grid)
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    save = dialog.footer("Tạo tài khoản", auto_accept=False)
    def persist():
        save.setEnabled(False)
        try:
            index = widgets[2].currentIndex()
            created = service.create_account(
                widgets[0].text().strip(),
                roles[widgets[1].currentIndex()]["role_code"],
                person_id=people[index - 1]["person_id"] if index > 0 else None,
            )
            dialog.accept()
            confirm(parent, "Đã tạo tài khoản",
                    f"Tài khoản: {created['username']}\nMật khẩu ban đầu: {created['password']}\n\n"
                    "Ghi lại ngay; mật khẩu không được lưu dạng rõ và không được ghi log.", info=True)
        except Exception as exc:
            error.setText(str(exc))
            save.setEnabled(True)
    save.clicked.connect(persist)
    accepted = dialog.exec()
    if accepted and on_saved:
        on_saved()
    return accepted


def change_password(parent, username):
    """Change the signed-in account's own password through AuthenticationService."""
    from app.services.authentication_service import AuthenticationService
    dialog = Dialog(parent, "Đổi mật khẩu", f"Tài khoản: {username}", 480)
    fields = [("Mật khẩu hiện tại", "text", ""), ("Mật khẩu mới (≥ 12 ký tự)", "text", ""),
              ("Nhập lại mật khẩu mới", "text", "")]
    grid = form(fields, cols=1); widgets = grid.field_widgets; dialog.v.addLayout(grid)
    for widget in widgets:
        widget.setEchoMode(QLineEdit.EchoMode.Password)
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    save = dialog.footer("Đổi mật khẩu", auto_accept=False)
    def persist():
        current, new, again = (widget.text() for widget in widgets)
        if not current or not new:
            error.setText("Cần nhập mật khẩu hiện tại và mật khẩu mới.")
            return
        if len(new) < 12:
            error.setText("Mật khẩu mới phải có ít nhất 12 ký tự.")
            return
        if new != again:
            error.setText("Hai lần nhập mật khẩu mới không khớp.")
            return
        if new == current:
            error.setText("Mật khẩu mới phải khác mật khẩu hiện tại.")
            return
        save.setEnabled(False)
        try:
            AuthenticationService().change_password(username, current, new)
            dialog.accept()
            confirm(parent, "Đã đổi mật khẩu", "Lần đăng nhập sau hãy dùng mật khẩu mới.", info=True)
        except Exception as exc:
            error.setText(str(exc))
            save.setEnabled(True)
    save.clicked.connect(persist)
    return dialog.exec()


def class_form(parent, edit=None, *, on_saved=None):
    fields = [("Tên lớp", "text", ""), ("Năm học", "text", "VD: 2026-2027"), ("Giáo viên phụ trách", "text", ""),
              ("Phòng học", "text", ""), ("Lịch học", "text", ""), ("Giờ học", "text", ""),
              ("Sĩ số tối đa", "text", ""), ("Ngày khai giảng", "date", ""), ("Ghi chú", "area", "")]
    dialog = Dialog(parent, "Sửa lớp" if edit else "Tạo lớp mới", "Thông tin được lưu vào cơ sở dữ liệu.", 720)
    grid = form(fields); widgets = grid.field_widgets; dialog.v.addLayout(grid)
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    if isinstance(edit, dict):
        vals = [edit.get("class_name"), edit.get("academic_year"), edit.get("teacher_name"), edit.get("room"),
                edit.get("schedule_text"), edit.get("time_text"), edit.get("capacity"), edit.get("start_date"), edit.get("notes")]
        for widget, value in zip(widgets, vals):
            if value is not None:
                widget.setText(str(value)) if hasattr(widget, "setText") else widget.setPlainText(str(value))
    save = dialog.footer("Lưu lớp", auto_accept=False)
    def persist():
        try:
            from app.services.class_service import ClassService
            values = [w.toPlainText().strip() if hasattr(w, "toPlainText") else w.text().strip() for w in widgets]
            data = dict(zip(("class_name", "academic_year", "teacher_name", "room", "schedule_text", "time_text", "capacity", "start_date", "notes"), values))
            data["capacity"] = int(data["capacity"]) if data["capacity"] else None
            data["class_status"] = edit.get("class_status", "active") if isinstance(edit, dict) else "active"
            ClassService().save(data, edit.get("class_id") if isinstance(edit, dict) else None)
            dialog.accept()
        except Exception as exc:
            error.setText(str(exc))
    save.clicked.connect(persist)
    accepted = dialog.exec()
    if accepted and on_saved:
        on_saved()
    return accepted


def roster(class_record, parent):
    from datetime import date
    from app.services.class_service import ClassService
    from app.ui import session
    service = ClassService()
    class_id = class_record["class_id"]
    name = class_record["class_name"]
    day = date.today().isoformat()
    may_write = session.has_permission("class.write")
    dialog = Dialog(parent, f"Sĩ số {name}", f"Danh sách và điểm danh ngày {day}", 760)
    card = Card()
    dialog.v.addWidget(card)
    error = label(""); error.setWordWrap(True); dialog.v.addWidget(error)
    states = {"present": "Có mặt", "late": "Đi muộn", "absent": "Vắng", "excused": "Có phép", "not_recorded": "Chưa ghi nhận"}

    def reload():
        while card.box.count():
            item = card.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            rows = service.roster(class_id, day)
            enrolled = {row["student_code"]: row["student_id"] for row in service.enrolled_students(class_id)}
        except Exception as exc:
            card.box.addWidget(label(f"Không tải được sĩ số: {exc}"))
            return
        display = [(code, student, states.get(status, status), checkin or "—", note or "")
                   for code, student, status, checkin, note in rows]

        def row_actions(shown):
            student_id = enrolled.get(shown[0])
            if not may_write or student_id is None:
                return []
            return [("Rút khỏi lớp", "late", lambda sid=student_id: withdraw(sid))]

        card.box.addWidget(make_table(["Mã", "Học viên", "Trạng thái", "Giờ vào", "Ghi chú"], display,
                                      tone_cols=(2,), actions=row_actions if may_write else None))
        if not display:
            card.box.addWidget(label("Lớp chưa có học viên đang theo học."))

    def withdraw(student_id):
        if not confirm(parent, "Rút học viên khỏi lớp",
                       "Đăng ký hiện tại sẽ được đóng lại (withdrawn); dữ liệu điểm danh cũ được giữ nguyên.",
                       danger=True):
            return
        try:
            service.withdraw_student(class_id, student_id)
            error.setText("")
        except Exception as exc:
            error.setText(str(exc))
        reload()

    def add_student():
        try:
            candidates = service.enrollable_students(class_id)
        except Exception as exc:
            error.setText(str(exc)); return
        if not candidates:
            error.setText("Không còn học viên đang hoạt động nào để thêm vào lớp.")
            return
        picker = Dialog(dialog, "Thêm học viên vào lớp", f"Lớp {name}", 520)
        grid = form([("Học viên", "combo", [row["display"] for row in candidates]),
                     ("Ngày bắt đầu", "date", day)], cols=1)
        widgets = grid.field_widgets; picker.v.addLayout(grid)
        picker_error = label(""); picker_error.setWordWrap(True); picker.v.addWidget(picker_error)
        save = picker.footer("Thêm vào lớp", auto_accept=False)
        def persist():
            save.setEnabled(False)
            try:
                service.enroll_student(class_id, candidates[widgets[0].currentIndex()]["student_id"],
                                       widgets[1].text().strip() or None)
                picker.accept()
            except Exception as exc:
                picker_error.setText(str(exc))
                save.setEnabled(True)
        save.clicked.connect(persist)
        if picker.exec():
            error.setText("")
            reload()

    reload()
    if may_write:
        add = dialog.footer("Thêm học viên", "Đóng", auto_accept=False)
        add.clicked.connect(add_student)
    else:
        dialog.footer("Đóng", None)
    return dialog.exec()


def export(parent):
    f = [("Khoảng thời gian", "combo", ["Hôm nay", "Tuần này", "Tháng này", "Tùy chọn"]), ("Định dạng", "combo", ["Excel (.xlsx)", "CSV", "PDF"]),
         ("Từ ngày", "date", ""), ("Đến ngày", "date", "")]
    return form_dialog(parent, "Xuất dữ liệu", f, "Xuất file", width=520)


def export_rows(parent, headers, rows, suggested_name="export.csv"):
    import csv
    from pathlib import Path
    path, _ = QFileDialog.getSaveFileName(parent, "Xuất dữ liệu CSV", suggested_name, "CSV UTF-8 (*.csv)")
    if not path:
        return False
    target = Path(path)
    if target.exists():
        confirm(parent, "Tệp đã tồn tại", "Không ghi đè tệp hiện có. Hãy chọn tên tệp khác.", info=True)
        return False
    created = False
    try:
        with target.open("x", encoding="utf-8-sig", newline="") as stream:
            created = True
            writer = csv.writer(stream)
            writer.writerow(headers)
            written = 0
            for row in rows:
                writer.writerow(row)
                written += 1
    except Exception as exc:
        if created:
            target.unlink(missing_ok=True)
        confirm(parent, "Không xuất được dữ liệu", str(exc), info=True)
        return False
    confirm(parent, "Xuất dữ liệu hoàn tất", f"Đã lưu {written} dòng tại {target}.", info=True)
    return True
