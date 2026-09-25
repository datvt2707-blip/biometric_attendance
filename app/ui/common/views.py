"""
views.py — CÁC MÀN HÌNH CHÍNH (dùng chung cho 2 khối)
LÀM GÌ   : BasePage (khung trang: tiêu đề, nút góc phải, thông tin người dùng) và 6 màn:
             DashboardView, AttendanceView, PeopleView, LeaveView, ClassesView, SettingsView, AccountsView.
             Các file trong office/ và student/ chỉ kế thừa lại và chọn khối.
CÔNG NGHỆ: Qt Widgets (layout, bảng, nút, ô tìm kiếm) + Fluent SwitchButton (công tắc Telegram).
NGHIỆP VỤ: Mỗi nút gọi một popup trong dialogs.py. Bảng ở docs/UI_GUIDE.md phần Phụ lục nói rõ nút nào ứng với nghiệp vụ nào.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from datetime import date
from dataclasses import replace
import logging
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QFrame, QDialog, QFileDialog
from qfluentwidgets import SwitchButton
from app.camera.camera_manager import CameraPreviewController
from app.biometric.liveness.active_liveness import ActiveLivenessChallenge
from app.ui import theme as T
from app.ui.ui_config import UI_CONFIG
from app.ui.common import dialogs as D
from app.ui.common.widgets import (Card, label, stat_card, bar_row, activity_row, LineChart, StepsBar,
                                   CameraView, make_table, tag, Pill, user_chip, Bar, PrimaryPushButton, PushButton, SearchLineEdit, ComboBox, LineEdit,
                                   DateEdit, date_text, ResponsiveRow)

logger = logging.getLogger(__name__)


def kv(card, k, v, color=None):
    r = QHBoxLayout(); r.addWidget(label(k, "muted")); r.addStretch(); r.addWidget(label(v, color=color)); card.box.addLayout(r)


def switch_row(card, k, on, *, scope=None, supported=True):
    r = QHBoxLayout(); r.addWidget(label(k, "muted")); r.addStretch()
    key = "notify_" + "_".join(part.lower() for part in k.split())
    s = SwitchButton()
    if not supported:
        on = False
    elif scope:
        from app.services.settings_service import SettingsService
        try:
            saved = SettingsService().get_scope(scope).get(key)
            on = saved.lower() in ("1", "true", "yes", "on") if saved is not None else on
        except Exception:
            pass
    s.setChecked(on)
    if not supported:
        s.setEnabled(False)
        s.setToolTip("Chưa có dịch vụ gửi thông báo; tùy chọn này chưa được hỗ trợ.")
    elif scope:
        def persist(value):
            from app.services.settings_service import SettingsService
            try:
                SettingsService().set_values(scope, {key: "true" if value else "false"})
                s.setToolTip("Đã lưu cài đặt")
            except Exception as exc: s.setToolTip(f"Không lưu được cài đặt: {exc}")
        s.checkedChanged.connect(persist)
    r.addWidget(s); card.box.addLayout(r)


class BasePage(QWidget):
    TITLE = ""

    def __init__(self, block, key):
        super().__init__()
        self.setObjectName(key); self.block = block; self.d = UI_CONFIG[block]
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea(); sc.setWidgetResizable(True); outer.addWidget(sc)
        inner = QWidget(); sc.setWidget(inner)
        root = QVBoxLayout(inner); root.setContentsMargins(28, 22, 28, 26); root.setSpacing(16)
        self.head = QHBoxLayout(); self.head.setSpacing(12)
        col = QVBoxLayout(); col.setSpacing(0)
        col.addWidget(label(self.heading(), "h1")); col.addWidget(label(f"{self.d['name']} • {date.today().strftime('%d/%m/%Y')}", "muted"))
        self.head.addLayout(col); self.head.addStretch(); root.addLayout(self.head)
        self.body = QVBoxLayout(); self.body.setSpacing(14); root.addLayout(self.body)
        self.build(self.d); self.head.addWidget(user_chip()); root.addStretch()

    def heading(self): return self.TITLE

    def row(self, *cards, stretch=None, threshold=980):
        """Lay cards out side by side, stacking them when the window is narrow."""
        container = ResponsiveRow(cards, stretch, threshold=threshold)
        self.body.addWidget(container)
        return container


class DashboardView(BasePage):
    TITLE = "T\u1ed5ng quan"

    def showEvent(self, event):
        super().showEvent(event)
        while self.body.count():
            item = self.body.takeAt(0)
            layout = item.layout()
            if layout:
                self._clear_layout(layout)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.build(self.d)

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            nested = item.layout()
            if nested:
                DashboardView._clear_layout(nested)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def build(self, d):
        from app.services.dashboard_service import DashboardService
        try:
            values = DashboardService().overview(self.block)
        except Exception:
            logger.exception("Dashboard query failed")
            error = Card("Không tải được số liệu tổng quan")
            error.box.addWidget(label("Không thể truy cập dữ liệu tổng quan. Hãy kiểm tra cơ sở dữ liệu rồi thử lại.", "muted"))
            self.body.addWidget(error)
            return
        self.row(*[stat_card(title, str(value), "T\u1eeb c\u01a1 s\u1edf d\u1eef li\u1ec7u", "info")
                   for title, value in values["stats"]])
        c1 = Card("S\u1ed1 l\u01b0\u1ee3t attendance trong 7 ng\u00e0y")
        c1.box.addWidget(LineChart(values["trend"], values["trend_labels"]))
        c2 = Card(values["group_title"])
        if values["bars"]:
            for name, pct, tone in values["bars"]: c2.box.addWidget(bar_row(name, pct, tone))
        else:
            c2.box.addWidget(label("Ch\u01b0a c\u00f3 d\u1eef li\u1ec7u nh\u00f3m", "muted"))
        c3 = Card("Attendance g\u1ea7n \u0111\u00e2y")
        if values["activities"]:
            for item in values["activities"]: c3.box.addWidget(activity_row(*item))
        else:
            c3.box.addWidget(label("Ch\u01b0a c\u00f3 b\u1ea3n ghi attendance", "muted"))
        self.row(c1, c2, c3, stretch=[3, 2, 2])
        extra_labels = (("Nh\u00e2n vi\u00ean ho\u1ea1t \u0111\u1ed9ng", "Embedding \u0111\u00e3 \u0111\u0103ng k\u00fd", "Check-out h\u00f4m nay")
                        if self.block == "staff" else
                        ("H\u1ecdc vi\u00ean ho\u1ea1t \u0111\u1ed9ng", "Embedding \u0111\u00e3 \u0111\u0103ng k\u00fd", "\u0110i\u1ec3m danh h\u00f4m nay"))
        self.row(*[stat_card(title, str(item[1]), "T\u1eeb c\u01a1 s\u1edf d\u1eef li\u1ec7u", "info")
                   for title, item in zip(extra_labels, values["extra"])])


class AttendanceView(BasePage):
    def heading(self): return self.d["att"]

    def build(self, d):
        from app.services.attendance_service import AttendanceService
        from app.services.t6_mode import development_attendance_without_liveness_enabled
        self._attendance_service = AttendanceService()
        self._development_t6_mode = development_attendance_without_liveness_enabled()
        self._dev_attempted_tracks = set()
        self._last_match = None
        self._last_analysis = None
        self._last_analysis_at = None
        self._held_match = None
        self._held_track = None
        self._held_at = None
        self._match_streak = 0
        self._liveness_challenge = ActiveLivenessChallenge()
        left = Card()
        self.camera_preview = CameraView(d["chip"])
        left.box.addWidget(self.camera_preview, 1)
        self._camera_controller = CameraPreviewController(
            self.camera_preview, parent=self, enable_face_analysis=True,
            enable_matching=True,
        )
        self._camera_controller.face_analysis_ready.connect(self._on_face_analysis)
        self._camera_controller.face_analysis_error.connect(self._on_face_analysis_error)
        if hasattr(self._camera_controller, "camera"):
            self._camera_controller.camera.camera_stopped.connect(self._on_attendance_camera_lost)
            self._camera_controller.camera.camera_error.connect(self._on_attendance_camera_error)
        left.box.addWidget(label(d["st_title"], "cardTitle")); left.box.addWidget(label(d["st_hint"], "muted"))
        self.steps_bar = StepsBar(d["steps"], d["cur"])
        left.box.addWidget(self.steps_bar)
        right = Card("K\u1ebft qu\u1ea3 x\u00e1c th\u1ef1c")
        right.box.addWidget(label("K\u1ebft qu\u1ea3 nh\u1eadn di\u1ec7n th\u1ef1c t\u1ebf t\u1eeb camera"))
        kv(right, "Ph\u00e1t hi\u1ec7n khu\u00f4n m\u1eb7t", "\u0110ang ch\u1edd", T.SAGE)
        self.liveness_status_label = label(
            "DEV MODE: kiểm tra nhận diện → attendance; bỏ qua bước MediaPipe"
            if self._development_t6_mode else "Chưa kiểm tra liveness MediaPipe",
            "muted",
        )
        self.liveness_status_label.setWordWrap(True)
        right.box.addWidget(self.liveness_status_label)
        self.liveness_button = PushButton("Bắt đầu thử thách chuyển động")
        self.liveness_button.clicked.connect(self._start_liveness_challenge)
        right.box.addWidget(self.liveness_button)
        match_row = QHBoxLayout(); match_row.addWidget(label("Nh\u1eadn di\u1ec7n khu\u00f4n m\u1eb7t", "muted")); match_row.addStretch()
        self.match_result_label = label("\u0110ang ch\u1edd khu\u00f4n m\u1eb7t\u2026")
        match_row.addWidget(self.match_result_label); right.box.addLayout(match_row)
        self.feedback_label = label("", "muted"); self.feedback_label.setWordWrap(True); right.box.addWidget(self.feedback_label)
        self._attendance_buttons = []
        for i, button_text in enumerate(d["btns"]):
            button = PrimaryPushButton(button_text) if i == 0 else PushButton(button_text)
            button.setEnabled(False)
            action = "check_out" if "Check-out" in button_text else "check_in"
            button.clicked.connect(lambda _=False, action=action: self._record_attendance(action))
            right.box.addWidget(button); self._attendance_buttons.append((action, button))
        right.box.addStretch()
        self.row(left, right, stretch=[3, 2])
        history = Card(f"Nh\u1eadt k\u00fd {d['att'].lower()}")
        filter_row = QHBoxLayout()
        self._attendance_from_date = DateEdit(placeholder="Từ ngày…")
        self._attendance_to_date = DateEdit(placeholder="Đến ngày…")
        self._attendance_status = ComboBox()
        self._attendance_status.addItems(["Tất cả trạng thái", "Có mặt", "Đi muộn", "Vắng", "Có phép"] +
                                         (["Chưa hoàn tất"] if self.block == "staff" else []))
        self._attendance_query = SearchLineEdit()
        self._attendance_query.setPlaceholderText("Tìm theo mã hoặc họ tên")
        self._attendance_query.setMinimumWidth(180)
        for widget in (self._attendance_from_date, self._attendance_to_date,
                       self._attendance_status, self._attendance_query):
            filter_row.addWidget(widget)
        filter_row.addStretch()
        export_button = PushButton("Xuất CSV")
        export_button.clicked.connect(self._export_attendance)
        filter_row.addWidget(export_button)
        history.box.addLayout(filter_row)
        self.attendance_table = make_table(d["lh"], [], tone_cols=(3, 4))
        history.box.addWidget(self.attendance_table)
        self._attendance_empty_label = label("Không có bản ghi phù hợp với bộ lọc.", "muted")
        self._attendance_empty_label.hide()
        history.box.addWidget(self._attendance_empty_label)
        self._attendance_page = 0
        self._attendance_filter_timer = QTimer(self)
        self._attendance_filter_timer.setSingleShot(True)
        self._attendance_filter_timer.setInterval(250)
        self._attendance_filter_timer.timeout.connect(self._reset_attendance_page)
        self._attendance_query.textChanged.connect(lambda _text: self._attendance_filter_timer.start())
        self._attendance_from_date.dateChanged.connect(lambda _d: self._reset_attendance_page())
        self._attendance_to_date.dateChanged.connect(lambda _d: self._reset_attendance_page())
        clear_dates = PushButton("Xóa ngày")
        clear_dates.clicked.connect(self._clear_attendance_dates)
        filter_row.insertWidget(2, clear_dates)
        self._attendance_status.currentIndexChanged.connect(self._reset_attendance_page)
        page_row = QHBoxLayout()
        self._attendance_page_label = label("Trang 1", "muted")
        self._attendance_previous = PushButton("\u2039")
        self._attendance_next = PushButton("\u203a")
        self._attendance_previous.clicked.connect(lambda: self._change_attendance_page(-1))
        self._attendance_next.clicked.connect(lambda: self._change_attendance_page(1))
        page_row.addStretch(); page_row.addWidget(self._attendance_page_label)
        page_row.addWidget(self._attendance_previous); page_row.addWidget(self._attendance_next)
        history.box.addLayout(page_row)
        self.body.addWidget(history)
        self._refresh_attendance_history()

    HOLD_SECONDS = 8.0
    HOLD_CONFIRMATIONS = 2

    def _release_hold(self):
        """Drop the locked identity so the next person starts from scratch."""
        self._held_match = None
        self._held_track = None
        self._held_at = None
        self._match_streak = 0

    def _hold_identity(self, match, result):
        """Lock a confirmed identity for a few seconds so the readout stops flickering.

        The lock only survives on the same tracked face and is dropped as soon as a
        different identity is matched, the track changes or the hold ages out; it
        never substitutes for the liveness proof, which is still validated per frame.
        """
        expected_kind = "employee" if self.block == "staff" else "student"
        track_id = getattr(result, "tracking_id", None) if result is not None else None
        now = time.monotonic()
        if (self._held_match is not None
                and (self._held_track != track_id
                     or now - self._held_at > self.HOLD_SECONDS)):
            self._release_hold()
        confirmed = (match is not None and match.status == "matched"
                     and match.person_type == expected_kind)
        if confirmed:
            if self._held_match is not None and self._held_match.person_id != match.person_id:
                self._release_hold()  # a different person took over the frame
            if self._held_match is not None:
                self._held_at = now
                return self._held_match
            self._match_streak += 1
            if self._match_streak >= self.HOLD_CONFIRMATIONS:
                self._held_match, self._held_track, self._held_at = match, track_id, now
                return self._held_match
            return match
        self._match_streak = 0
        # A single unmatched frame must not wipe a freshly confirmed identity.
        if self._held_match is not None and self._held_track == track_id:
            return self._held_match
        return match

    def _update_steps(self, *, recognized, proof_ready):
        step = 2 if proof_ready else (1 if recognized else 0)
        if hasattr(self, "steps_bar"):
            self.steps_bar.set_current(step)

    def _set_attendance_match(self, match):
        expected_kind = "employee" if self.block == "staff" else "student"
        self._last_match = match if (match is not None and match.status == "matched"
                                     and match.person_type == expected_kind) else None
        result = self._last_analysis
        fresh = (self._last_analysis_at is not None and
                 time.monotonic() - self._last_analysis_at <= ActiveLivenessChallenge.MAX_OBSERVATION_GAP)
        # Bystanders are allowed: T2 already reduced the frame to the nearest face.
        actual_face = bool(result is not None and result.status == "face_selected"
                           and result.selected is not None and result.embedding is not None)
        can_use_proof = bool(
            self._last_match is not None and actual_face and fresh
            and (self._development_t6_mode or result.mediapipe_landmarks is not None)
            and self._liveness_challenge.can_consume(
                self._last_match, track_id=result.tracking_id,
            )
        )
        enabled = bool(self._last_match is not None and actual_face and fresh
                       and (can_use_proof or self._development_t6_mode))
        for action, button in self._attendance_buttons:
            button.setEnabled(enabled)
            if self.block == "student":
                button.setToolTip("Điểm danh tự động sau thử thách; nút này dùng khi cần ghi thủ công.")
            elif not enabled:
                button.setToolTip("Cần nhận diện được người đã đăng ký và hoàn tất thử thách chuyển động.")
            else:
                button.setToolTip("")
        self._update_steps(recognized=self._last_match is not None,
                           proof_ready=can_use_proof or (enabled and self._development_t6_mode))

    def _update_liveness_control(self):
        active = self._liveness_challenge.state.status in ("active", "calibrating", "awaiting_turn")
        self.liveness_button.setText("Hủy thử thách" if active else "Bắt đầu thử thách chuyển động")

    def _on_face_analysis(self, frame, result):
        previous_challenge_status = self._liveness_challenge.state.status
        self._last_analysis = result
        self._last_analysis_at = time.monotonic()
        if result.liveness_config and self._liveness_challenge.state.status in ("idle", "cancelled", "failed"):
            try:
                self._liveness_challenge.configure(result.liveness_config)
            except ValueError as exc:
                result = replace(result, liveness_error=f"Cấu hình liveness từ DB không hợp lệ: {exc}")
        self._last_analysis = result
        self.camera_preview.set_face_bbox(result.tracking_bbox, frame.shape)
        if result.status == "no_face":
            self.match_result_label.setText("Kh\u00f4ng th\u1ea5y khu\u00f4n m\u1eb7t")
            self._liveness_challenge.observe(
                match=None, face_status=result.status, face_count=result.face_count,
                track_id=result.tracking_id, landmarks=result.landmarks,
                frame_sequence=result.frame_sequence,
            )
            self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
            self._update_liveness_control()
            self._release_hold()
            self._set_attendance_match(None)
            self._dev_attempted_tracks.clear()
            return
        if result.status != "face_selected" or result.embedding is None:
            self.match_result_label.setText("Nhi\u1ec1u khu\u00f4n m\u1eb7t ho\u1eb7c ch\u01b0a ch\u1ecdn an to\u00e0n")
            self._liveness_challenge.observe(
                match=None, face_status=result.status, face_count=result.face_count,
                track_id=result.tracking_id, landmarks=result.landmarks,
                frame_sequence=result.frame_sequence,
            )
            self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
            self._update_liveness_control()
            self._release_hold()
            self._set_attendance_match(None)
            self._dev_attempted_tracks.clear()
            return
        match = self._hold_identity(result.match_result, result)
        held = match is not None and match is self._held_match
        if match is None:
            self.match_result_label.setText("Ch\u01b0a c\u00f3 k\u1ebft qu\u1ea3 so kh\u1edbp")
        elif match.status == "matched":
            expected_kind = "employee" if self.block == "staff" else "student"
            if match.person_type != expected_kind:
                self.match_result_label.setText("Danh tính thuộc khối khác; không thể ghi attendance tại màn hình này.")
                self._liveness_challenge.invalidate("Danh tính không thuộc màn hình attendance hiện tại.")
                self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
                self._update_liveness_control()
                self._set_attendance_match(None)
                return
            self.match_result_label.setText(
                ("\u0110\u00e3 kh\u00f3a \u00b7 " if held else "")
                + f"{match.display_name} \u00b7 {match.person_code} \u00b7 cosine {match.similarity:.3f}"
            )
        elif match.status == "ambiguous":
            self.match_result_label.setText("K\u1ebft qu\u1ea3 m\u01a1 h\u1ed3 \u00b7 c\u1ea7n ch\u1ecdn l\u1ea1i khu\u00f4n m\u1eb7t")
        elif match.status == "no_match":
            self.match_result_label.setText("Kh\u00f4ng nh\u1eadn di\u1ec7n \u0111\u01b0\u1ee3c ng\u01b0\u1eddi \u0111\u00e3 \u0111\u0103ng k\u00fd")
        else:
            self.match_result_label.setText("L\u1ed7i khi so kh\u1edbp khu\u00f4n m\u1eb7t")
        if self._development_t6_mode:
            self.liveness_status_label.setText(
                "DEV MODE: đã bỏ qua MediaPipe; nhận diện vẫn dùng InsightFace và dữ liệu đăng ký thật."
            )
        elif result.liveness_error:
            self.liveness_status_label.setText(
                f"Chưa thể xác minh MediaPipe: {result.liveness_error}"
            )
            self.liveness_button.setEnabled(False)
        else:
            self.liveness_button.setEnabled(True)
            if (held and result.mediapipe_landmarks is not None
                    and self._liveness_challenge.state.status in
                    ("idle", "cancelled", "failed", "expired")):
                # Identity is locked, so the challenge can start on its own and the
                # operator only has to follow the prompt.
                self._liveness_challenge.start(match, track_id=result.tracking_id,
                                               frame_sequence=result.frame_sequence)
            state = self._liveness_challenge.observe(
                match=match, face_status=result.status, face_count=result.face_count,
                track_id=result.tracking_id, landmarks=result.mediapipe_landmarks,
                frame_sequence=result.frame_sequence,
            )
            self.liveness_status_label.setText(state.prompt)
            self._update_liveness_control()
        self._set_attendance_match(match)
        if (not self._development_t6_mode and not result.liveness_error
                and state.passed and previous_challenge_status != "passed"
                and self.block == "student" and self._last_match is not None):
            self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
            self._update_liveness_control()
            self._set_attendance_match(match)
            self._perform_attendance("check_in", liveness_challenge=self._liveness_challenge,
                                     track_id=result.tracking_id)
        elif (self._development_t6_mode and self.block == "student"
              and self._last_match is not None
              and (self._last_match.person_id, result.tracking_id) not in self._dev_attempted_tracks):
            self._dev_attempted_tracks.add((self._last_match.person_id, result.tracking_id))
            self._perform_attendance("check_in")

    def _on_face_analysis_error(self, message):
        self._release_hold()
        self._liveness_challenge.invalidate("Lỗi camera/nhận diện; thử thách đã bị hủy.")
        self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
        self._update_liveness_control()
        self.camera_preview.set_face_bbox(None)
        self.match_result_label.setText(f"Kh\u00f4ng th\u1ec3 ph\u00e2n t\u00edch khu\u00f4n m\u1eb7t: {message}")
        self._set_attendance_match(None)

    def _on_attendance_camera_lost(self):
        self._release_hold()
        self._liveness_challenge.invalidate("Camera đã dừng; thử thách bị hủy.")
        self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
        self._update_liveness_control()
        self._set_attendance_match(None)

    def _on_attendance_camera_error(self, message):
        self._release_hold()
        self._liveness_challenge.invalidate("Camera gặp lỗi; thử thách bị hủy.")
        self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
        self._update_liveness_control()
        self.feedback_label.setText(f"Lỗi camera: {message}")
        self._set_attendance_match(None)

    def _record_attendance(self, action):
        match = self._last_match
        if match is None:
            self.feedback_label.setText("C\u1ea7n nh\u1eadn di\u1ec7n th\u00e0nh c\u00f4ng tr\u01b0\u1edbc.")
            return
        if self._last_analysis is None or self._last_analysis_at is None or time.monotonic() - self._last_analysis_at > ActiveLivenessChallenge.MAX_OBSERVATION_GAP:
            self.feedback_label.setText("Kết quả camera đã cũ; hãy chờ nhận diện trực tiếp rồi thử lại.")
            self._set_attendance_match(None)
            return
        if (not self._development_t6_mode and not self._liveness_challenge.can_consume(
                match, track_id=self._last_analysis.tracking_id)):
            self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
            self._set_attendance_match(match)
            self.feedback_label.setText("Cần hoàn tất thử thách chuyển động trước khi chấm công.")
            return
        self.liveness_status_label.setText(self._liveness_challenge.state.prompt)
        self._set_attendance_match(match)
        self._perform_attendance(
            action,
            liveness_challenge=None if self._development_t6_mode else self._liveness_challenge,
            track_id=self._last_analysis.tracking_id,
        )

    def _perform_attendance(self, action, *, liveness_challenge=None, track_id=None):
        match = self._last_match
        if match is None:
            self.feedback_label.setText("Không còn kết quả nhận diện hợp lệ để ghi attendance.")
            return
        try:
            result = (self._attendance_service.check_out(
                match, liveness_challenge=liveness_challenge, track_id=track_id
            ) if action == "check_out" else self._attendance_service.check_in(
                match, liveness_challenge=liveness_challenge, track_id=track_id
            ))
        except Exception as exc:
            self.feedback_label.setText(f"Không ghi được attendance: {exc}")
            return
        self.feedback_label.setText(
            f"{result.message}" + (f" {result.recorded_at}" if result.recorded_at else "")
        )
        if result.status == "success":
            self._attendance_page = 0
            self._refresh_attendance_history()

    def _start_liveness_challenge(self):
        if self._development_t6_mode:
            self.liveness_status_label.setText(
                "DEV MODE đang bật: bước MediaPipe bị bỏ qua có chủ đích."
            )
            return
        if self._last_analysis is not None and self._last_analysis.liveness_error:
            self.liveness_status_label.setText(
                f"Không thể bắt đầu: {self._last_analysis.liveness_error}"
            )
            return
        if self._liveness_challenge.state.status in ("active", "calibrating", "awaiting_turn"):
            state = self._liveness_challenge.cancel("Đã hủy thử thách.")
            self.liveness_status_label.setText(state.prompt)
            self._update_liveness_control()
            self._set_attendance_match(self._last_match)
            return
        result = self._last_analysis
        match = self._last_match
        if (result is None or match is None or self._last_analysis_at is None
                or time.monotonic() - self._last_analysis_at > ActiveLivenessChallenge.MAX_OBSERVATION_GAP):
            self.liveness_status_label.setText("Cần chờ một khuôn mặt đã so khớp trực tiếp trước khi bắt đầu.")
            return
        state = self._liveness_challenge.start(
            match, track_id=result.tracking_id, frame_sequence=result.frame_sequence,
        )
        self.liveness_status_label.setText(state.prompt)
        self._update_liveness_control()
        self._set_attendance_match(match)

    def _refresh_attendance_history(self):
        page_size = 100
        try:
            filters = self._attendance_filters()
            total = self._attendance_service.count_history(self.block, **filters)
            pages = max(1, (total + page_size - 1) // page_size)
            if self._attendance_page >= pages:
                self._attendance_page = pages - 1
            rows = self._attendance_service.list_history(
                self.block, **filters, limit=page_size, offset=self._attendance_page * page_size,
            )
            has_next = self._attendance_page + 1 < pages
        except ValueError as exc:
            self.feedback_label.setText(f"Bộ lọc không hợp lệ: {exc}")
            rows, has_next, total, pages = [], False, None, 1
        except Exception:
            logger.exception("Attendance history query failed")
            self.feedback_label.setText("Không tải được lịch sử attendance. Hãy kiểm tra cơ sở dữ liệu rồi thử lại.")
            rows, has_next, total, pages = [], False, None, 1
        displayed = self._format_attendance_rows(rows)
        new_table = make_table(self.d["lh"], displayed, tone_cols=(3, 4))
        parent = self.attendance_table.parentWidget().layout()
        parent.replaceWidget(self.attendance_table, new_table)
        self.attendance_table.deleteLater()
        self.attendance_table = new_table
        self._attendance_empty_label.setVisible(not rows)
        suffix = f" · {total} bản ghi" if total is not None else " · chưa tải được tổng số"
        self._attendance_page_label.setText(f"Trang {self._attendance_page + 1} / {pages}{suffix}")
        self._attendance_previous.setEnabled(self._attendance_page > 0)
        self._attendance_next.setEnabled(has_next)

    def _clear_attendance_dates(self):
        """Return both calendars to the empty state so the filter spans everything."""
        self._attendance_from_date.clear()
        self._attendance_to_date.clear()

    def _attendance_filters(self):
        status_values = ("present", "late", "absent", "excused", "incomplete")
        index = self._attendance_status.currentIndex()
        return {
            "from_date": self._attendance_from_date.text().strip() or None,
            "to_date": self._attendance_to_date.text().strip() or None,
            "query": self._attendance_query.text(),
            "status": status_values[index - 1] if index else None,
        }

    def _reset_attendance_page(self, *_):
        self._attendance_page = 0
        self._refresh_attendance_history()

    def _export_attendance(self):
        filters = self._attendance_filters()
        try:
            def filtered_rows():
                offset, chunk = 0, 500
                while True:
                    rows = self._attendance_service.list_history(
                        self.block, **filters, limit=chunk, offset=offset
                    )
                    if not rows:
                        break
                    for row in self._format_attendance_rows(rows):
                        yield row
                    offset += len(rows)

            D.export_rows(self.window(), self.d["lh"], filtered_rows(),
                          "employee-attendance.csv" if self.block == "staff" else "student-attendance.csv")
        except Exception as exc:
            D.confirm(self.window(), "Không xuất được dữ liệu", str(exc), info=True)

    def _format_attendance_rows(self, rows):
        state_labels = {"present": "Có mặt", "late": "Đi muộn", "absent": "Vắng",
                        "excused": "Có phép", "incomplete": "Chưa hoàn tất"}
        if self.block == "staff":
            return [(name, department, day, f"In {check_in or '?'} · Out {check_out or '?'}",
                     state_labels.get(status, status))
                    for _code, name, department, day, check_in, check_out, status in rows]
        return [(name, class_name, day, state_labels.get(status, status), f"Điểm danh {check_in or '?'}")
                for _code, name, class_name, day, check_in, _check_out, status in rows]

    def _change_attendance_page(self, delta):
        next_page = self._attendance_page + delta
        if next_page < 0:
            return
        self._attendance_page = next_page
        self._refresh_attendance_history()


class PeopleView(BasePage):
    def heading(self): return self.d["people"]

    def build(self, d):
        if self.block == "staff":
            from app.services.employee_service import EmployeeService
            self._people_service = EmployeeService()
        else:
            from app.services.student_service import StudentService
            self._people_service = StudentService()
        add = PrimaryPushButton("+ \u0110\u0103ng k\u00fd m\u1edbi")
        add.clicked.connect(lambda: D.enroll(d, self.window(), on_saved=self._refresh_people))
        self.head.addWidget(add)
        tools = QHBoxLayout(); tools.setSpacing(10)
        self._people_search = SearchLineEdit(); self._people_search.setPlaceholderText("T\u00ecm theo t\u00ean, m\u00e3\u2026"); self._people_search.setFixedWidth(280)
        self._people_status = ComboBox(); self._people_status.addItems(["T\u1ea5t c\u1ea3 tr\u1ea1ng th\u00e1i", "\u0110ang ho\u1ea1t \u0111\u1ed9ng", "Ng\u1eebng ho\u1ea1t \u0111\u1ed9ng"]); self._people_status.setFixedWidth(190)
        tools.addWidget(self._people_search); tools.addWidget(self._people_status); tools.addStretch()
        ex = PushButton("Xu\u1ea5t CSV"); ex.clicked.connect(self._export_people); tools.addWidget(ex)
        self.body.addLayout(tools)
        self._people_card = Card()
        self._people_table = make_table(d["ph"], [], tone_cols=(3, 4))
        self._people_count = label("\u0110ang t\u1ea3i\u2026", "muted")
        self._people_card.box.addWidget(self._people_table)
        self._people_page = 0
        page_row = QHBoxLayout()
        self._people_page_label = label("Trang 1", "muted")
        self._people_previous = PushButton("\u2039")
        self._people_next = PushButton("\u203a")
        self._people_previous.clicked.connect(lambda: self._change_people_page(-1))
        self._people_next.clicked.connect(lambda: self._change_people_page(1))
        page_row.addWidget(self._people_count); page_row.addStretch()
        page_row.addWidget(self._people_page_label)
        page_row.addWidget(self._people_previous); page_row.addWidget(self._people_next)
        self._people_card.box.addLayout(page_row)
        self.body.addWidget(self._people_card)
        self._people_search.textChanged.connect(self._reset_people_page)
        self._people_status.currentIndexChanged.connect(self._reset_people_page)
        self._refresh_people()

    def _reset_people_page(self, *_):
        self._people_page = 0
        self._refresh_people()

    def _change_people_page(self, delta):
        next_page = self._people_page + delta
        if next_page < 0:
            return
        self._people_page = next_page
        self._refresh_people()

    def _refresh_people(self, *_):
        status = {1: "active", 2: ("on_leave", "terminated", "inactive") if self.block == "staff"
                  else ("reserved", "graduated", "inactive")}.get(self._people_status.currentIndex())
        try:
            page_size = 100
            rows, total = self._people_service.search_directory(
                self._people_search.text(), status, limit=page_size, offset=self._people_page * page_size
            )
            display_rows = [
                (row[0], row[1], row[2] or "Chưa xếp lớp" if self.block == "student" else row[2],
                 {"active": "Đang hoạt động", "on_leave": "Nghỉ phép", "terminated": "Đã nghỉ", "inactive": "Ngừng hoạt động"}.get(row[3], row[3]),
                 "Đã đăng ký" if row[4] else "Chưa đăng ký") for row in rows
            ]
            table = make_table(
                self.d["ph"], display_rows, tone_cols=(3, 4),
                actions=lambda row: [
                    ("Xem", "brass", lambda code=row[0]: D.person_detail(self.block, code, self.window(), on_saved=self._refresh_people)),
                    ("Sửa", "info", lambda code=row[0]: D.edit_person(self.block, code, self.window(), on_saved=self._refresh_people)),
                    ("Ngừng", "late", lambda code=row[0]: self._deactivate_person(code)),
                ],
            )
            self._people_card.box.replaceWidget(self._people_table, table)
            self._people_table.deleteLater()
            self._people_table = table
            self._people_count.setText(f"Hiển thị {len(display_rows)} / {total}")
            pages = max(1, (total + page_size - 1) // page_size)
            if self._people_page >= pages:
                self._people_page = pages - 1
                return self._refresh_people()
            self._people_page_label.setText(f"Trang {self._people_page + 1} / {pages}")
            self._people_previous.setEnabled(self._people_page > 0)
            self._people_next.setEnabled(self._people_page + 1 < pages)
        except Exception as exc:
            self._people_count.setText(f"Không tải được danh sách: {exc}")

    def _deactivate_person(self, code):
        message = (f"X\u00e1c nh\u1eadn ng\u1eebng h\u1ed3 s\u01a1 {code}? Enrollment \u0111ang ho\u1ea1t \u0111\u1ed9ng s\u1ebd \u0111\u01b0\u1ee3c k\u1ebft th\u00fac h\u00f4m nay; attendance v\u00e0 l\u1ecbch s\u1eed \u0111\u01b0\u1ee3c gi\u1eef l\u1ea1i."
                   if self.block == "student" else f"X\u00e1c nh\u1eadn ng\u1eebng ho\u1ea1t \u0111\u1ed9ng h\u1ed3 s\u01a1 {code}?")
        if not D.confirm(self.window(), "Ng\u1eebng ho\u1ea1t \u0111\u1ed9ng", message, danger=True):
            return
        try:
            record = self._people_service.get_by_code(code)
            if self.block == "staff":
                self._people_service.deactivate(record["employee"]["employee_id"])
            else:
                self._people_service.deactivate(record["student"]["student_id"])
            self._refresh_people()
        except Exception as exc:
            D.confirm(self.window(), "Không cập nhật được", str(exc), info=True)

    def _export_people(self):
        status = {1: "active", 2: ("on_leave", "terminated", "inactive") if self.block == "staff"
                  else ("reserved", "graduated", "inactive")}.get(self._people_status.currentIndex())
        try:
            def filtered_rows():
                offset, chunk = 0, 500
                while True:
                    rows, total = self._people_service.search_directory(
                        self._people_search.text(), status, limit=chunk, offset=offset
                    )
                    if not rows:
                        break
                    for row in rows:
                        yield (row[0], row[1], row[2] or "\u2014", row[3],
                               "\u0110\u00e3 \u0111\u0103ng k\u00fd" if row[4] else "Ch\u01b0a \u0111\u0103ng k\u00fd")
                    offset += len(rows)
                    if offset >= total:
                        break
            D.export_rows(self.window(), self.d["ph"], filtered_rows(), "employees.csv" if self.block == "staff" else "students.csv")
        except Exception as exc:
            D.confirm(self.window(), "Kh\u00f4ng xu\u1ea5t \u0111\u01b0\u1ee3c d\u1eef li\u1ec7u", str(exc), info=True)


class LeaveView(BasePage):
    HS = ["Mã", "Nhân viên", "Loại nghỉ", "Từ ngày", "Đến ngày", "Lý do", "Trạng thái"]
    HT = ["Mã", "Học viên", "Lớp", "Ngày nghỉ", "Người nộp", "Lý do", "Trạng thái"]
    def heading(self): return "Nghỉ phép" if self.block == "staff" else "Đơn nghỉ học"

    def build(self, d):
        from app.services.leave_service import LeaveService
        self._leave_service = LeaveService()
        self._leave_headers = self.HS if self.block == "staff" else self.HT
        add = PrimaryPushButton("+ Tạo đơn nghỉ phép" if self.block == "staff" else "+ Tạo đơn nghỉ học")
        add.clicked.connect(lambda: D.leave_form(self.block, self.window(), on_saved=self._refresh_leaves)); self.head.addWidget(add)
        filters = QHBoxLayout()
        self._leave_search = SearchLineEdit(); self._leave_search.setPlaceholderText("Tìm theo mã hoặc họ tên")
        self._leave_status = ComboBox(); self._leave_status.addItems(["Tất cả", "Chờ duyệt", "Đã duyệt", "Từ chối"])
        filters.addWidget(self._leave_search); filters.addWidget(self._leave_status); filters.addStretch()
        self.body.addLayout(filters)
        self._leave_stats = QHBoxLayout(); self.body.addLayout(self._leave_stats)
        self._leave_card = Card(); self._leave_table = make_table(self._leave_headers, [], tone_cols=(6,))
        self._leave_card.box.addWidget(self._leave_table); self.body.addWidget(self._leave_card)
        self._leave_search.textChanged.connect(self._refresh_leaves)
        self._leave_status.currentIndexChanged.connect(self._refresh_leaves)
        self._refresh_leaves()

    def _refresh_leaves(self, *_):
        statuses = {1: "pending", 2: "approved", 3: "rejected"}
        try:
            all_rows = self._leave_service.list_requests(self.block)
            rows = self._leave_service.list_requests(
                self.block, status=statuses.get(self._leave_status.currentIndex()), query=self._leave_search.text()
            )
            counts = {status: sum(row[-1] == status for row in all_rows) for status in ("pending", "approved", "rejected")}
            for i in reversed(range(self._leave_stats.count())):
                item = self._leave_stats.takeAt(i)
                if item.widget(): item.widget().deleteLater()
            for title, value, tone in (("Chờ duyệt", counts["pending"], "wait"), ("Đã duyệt", counts["approved"], "ok"), ("Từ chối", counts["rejected"], "late")):
                self._leave_stats.addWidget(stat_card(title, str(value), "Từ dữ liệu đang lưu", tone))
            state_names = {"pending": "Chờ duyệt", "approved": "Đã duyệt", "rejected": "Từ chối"}
            display = []
            for row in rows:
                if self.block == "staff":
                    request_id, code, name, kind, start, end, reason, status = row
                    shown = (code, name, kind, start, end, reason, state_names.get(status, status))
                else:
                    request_id, code, name, class_name, day, submitted, reason, status = row
                    shown = (code, name, class_name, day, submitted, reason, state_names.get(status, status))
                display.append((request_id, shown, status))
            from app.ui import session
            self._may_review_leaves = session.has_permission(
                "employee.leave.review" if self.block == "staff" else "student.leave.review")
            self._leave_pending_ids = {item[1]: item[0] for item in display if item[2] == "pending"}
            self._leave_rows_by_id = {item[0]: item[1] for item in display}
            table = make_table(self._leave_headers, [item[1] for item in display], tone_cols=(6,),
                actions=self._leave_actions)
            table.setToolTip("Duy\u1ec7t/t\u1eeb ch\u1ed1i ch\u1ec9 hi\u1ec7n v\u1edbi \u0111\u01a1n \u0111ang ch\u1edd."
                             if self._may_review_leaves else
                             "T\u00e0i kho\u1ea3n hi\u1ec7n t\u1ea1i kh\u00f4ng c\u00f3 quy\u1ec1n duy\u1ec7t \u0111\u01a1n; ch\u1ec9 xem.")
            self._leave_card.box.replaceWidget(self._leave_table, table); self._leave_table.deleteLater(); self._leave_table = table
        except Exception as exc:
            self._leave_card.box.addWidget(label(f"Không tải được đơn nghỉ: {exc}"))

    def _leave_actions(self, shown):
        """View is always available; review actions only for pending rows the session may review."""
        actions = [("Xem", "brass", lambda row=shown: D.leave_detail(self._leave_headers, row, self.window()))]
        request_id = self._leave_pending_ids.get(tuple(shown))
        if not self._may_review_leaves or request_id is None:
            return actions
        return actions + [
            (caption, tone, lambda row=shown, rid=request_id, value=decision: D.leave_review(
                self.block, rid, value, self._leave_headers, row, self.window(),
                on_saved=self._refresh_leaves))
            for caption, tone, decision in (("Duyệt", "ok", "approved"), ("Từ chối", "late", "rejected"))
        ]


class ClassesView(BasePage):
    TITLE = "Lớp học"

    def build(self, d):
        from app.services.class_service import ClassService
        self._class_service = ClassService()
        nb = PrimaryPushButton("+ Tạo lớp"); nb.clicked.connect(lambda: D.class_form(self.window(), on_saved=self._refresh_classes)); self.head.addWidget(nb)
        self._class_grid = QGridLayout(); self._class_grid.setSpacing(14)
        self.body.addLayout(self._class_grid)
        self._refresh_classes()

    def _refresh_classes(self):
        while self._class_grid.count():
            item = self._class_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        try:
            rows = self._class_service.list_classes()
            for i, record in enumerate(rows):
                c = Card()
                top = QHBoxLayout(); top.addWidget(label(record["class_name"], "cardTitle")); top.addStretch()
                top.addWidget(tag("Đang hoạt động" if record["class_status"] == "active" else "Đã đóng", "ok" if record["class_status"] == "active" else "wait")); c.box.addLayout(top)
                c.box.addWidget(label(f"GV phụ trách: {record['teacher_name'] or '—'}", "muted"))
                c.box.addWidget(label(f"{record['active_students']} học viên · {record['academic_year']} · {record['schedule_text'] or 'Chưa có lịch'}", "muted"))
                buttons = QHBoxLayout(); roster = PushButton("Danh sách"); edit = PushButton("Sửa lớp")
                roster.clicked.connect(lambda _=False, record=record: D.roster(record, self.window()))
                edit.clicked.connect(lambda _=False, record=record: D.class_form(self.window(), dict(record), on_saved=self._refresh_classes))
                buttons.addWidget(roster); buttons.addWidget(edit); c.box.addLayout(buttons)
                self._class_grid.addWidget(c, i // 3, i % 3)
            if not rows:
                self._class_grid.addWidget(label("Chưa có lớp trong cơ sở dữ liệu."), 0, 0)
        except Exception as exc:
            self._class_grid.addWidget(label(f"Không tải được danh sách lớp: {exc}"), 0, 0)


class SettingsView(BasePage):
    TITLE = "Cài đặt hệ thống"

    def db_btns(self):
        h = QHBoxLayout(); a, b = PushButton("Sao lưu ngay"), PushButton("Khôi phục")
        def backup():
            path, _ = QFileDialog.getSaveFileName(self, "Chọn tệp sao lưu", "attendance-backup.sqlite", "SQLite (*.sqlite *.db)")
            if not path: return
            try:
                from app.services.settings_service import SettingsService
                result = SettingsService().backup_to(path)
                D.confirm(self.window(), "Sao lưu hoàn tất", f"Đã tạo bản sao lưu: {result}", info=True)
            except Exception as exc:
                D.confirm(self.window(), "Không sao lưu được", str(exc), info=True)
        a.clicked.connect(backup)
        b.setEnabled(False)
        b.setToolTip("Khôi phục sẽ ghi đè dữ liệu; thao tác này chưa được bật trong phạm vi bảo toàn dữ liệu T5.")
        h.addWidget(a); h.addWidget(b); return h

    T6_FIELDS = [
        ("blink_closed_ear_max", "EAR tối đa khi nhắm mắt"),
        ("blink_open_ear_min", "EAR tối thiểu khi mở mắt"),
        ("blink_closed_frames", "Số frame mắt nhắm liên tiếp"),
        ("blink_open_frames", "Số frame mắt mở liên tiếp"),
        ("neutral_frames", "Số frame giữ mặt chính diện"),
        ("turn_threshold", "Ngưỡng quay đầu (tỉ lệ)"),
        ("turn_frames", "Số frame giữ hướng quay"),
        ("timeout_seconds", "Thời hạn hoàn thành thử thách (giây)"),
        ("proof_seconds", "Hiệu lực của proof (giây)"),
        ("max_observation_gap", "Khoảng cách tối đa giữa 2 frame (giây)"),
    ]

    def build(self, d):
        from app.services.settings_service import SettingsService
        from app.ui import session
        self._settings_service = SettingsService()
        self._may_write_settings = session.has_permission("settings.write")
        self._t6_inputs = {}
        sv = PrimaryPushButton("Lưu thay đổi")
        sv.setEnabled(self._may_write_settings)
        if not self._may_write_settings:
            sv.setToolTip("Tài khoản hiện tại không có quyền settings.write.")
        sv.clicked.connect(self._save_t6)
        self.head.addWidget(sv)
        unconfigured = "Chưa cấu hình (chờ quy định nghiệp vụ)"
        extra = ("Ca làm việc", [("Giờ vào ca", unconfigured), ("Giờ tan ca", unconfigured), ("Cho phép đi muộn", unconfigured)]) if self.block == "staff" \
            else ("Lịch điểm danh", [("Mở điểm danh trước giờ học", unconfigured), ("Tính muộn sau", unconfigured), ("Báo phụ huynh khi vắng", unconfigured)])
        groups = [extra,
                  ("Nhận diện & chống giả mạo", [("Face Recognition", "InsightFace buffalo_l · CPU"),
                   ("Tiền xử lý", "Histogram equalization (kênh Y) trước khi trích embedding"),
                   ("Anti-spoofing", "Chưa tích hợp (T7 MiniFASNet chưa thực hiện)"),
                   ("Active liveness", "Nháy mắt → quay trái → quay phải, ngưỡng lấy từ cơ sở dữ liệu")]),
                  ("Camera", [("Thiết bị", "Theo thiết bị khả dụng"), ("Độ phân giải", "Theo frame camera thực tế"), ("FPS", "Theo tốc độ capture thực tế")]),
                  ("Database & sao lưu", self._database_rows())]
        g = QGridLayout(); g.setSpacing(14)
        for i, (t, rows) in enumerate(groups):
            c = Card(t)
            for k, v in rows: kv(c, k, v, T.SAGE if v.startswith("Đã") else None)
            if t.startswith("Database"): c.box.addLayout(self.db_btns())
            c.box.addStretch(); g.addWidget(c, i // 2, i % 2)
        g.addWidget(self._t6_card(), 2, 0, 1, 2)
        n = Card("Thông báo Telegram")
        for k, on in [("Bật Telegram Bot", True), ("Báo khi đi muộn", True), ("Báo khi vắng", False), ("Báo cáo cuối ngày", True)]: switch_row(n, k, on, scope=self.block, supported=False)
        g.addWidget(n, 3, 0, 1, 2)
        self.body.addLayout(g)

    def _database_rows(self):
        """Report the actual database file, its size, row counts and latest backup."""
        from pathlib import Path
        from app.database.database import DEFAULT_DATABASE_PATH, connect
        path = Path(self._settings_service.database_path or DEFAULT_DATABASE_PATH)
        rows = [("Tệp dữ liệu", str(path))]
        if not path.exists():
            return rows + [("Trạng thái", "Tệp dữ liệu chưa tồn tại")]
        rows.append(("Kích thước", f"{path.stat().st_size / (1024 * 1024):.2f} MB"))
        try:
            connection = connect(path)
            try:
                counts = []
                for table, caption in (("people", "hồ sơ"), ("employee_attendance", "chấm công NV"),
                                       ("student_attendance", "chấm công HV"),
                                       ("face_embeddings", "embedding")):
                    total = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    counts.append(f"{total} {caption}")
                rows.append(("Trạng thái", "Đã kết nối · " + " · ".join(counts)))
            finally:
                connection.close()
        except Exception as exc:
            rows.append(("Trạng thái", f"Không đọc được dữ liệu: {exc}"))
        backups = sorted(Path(path.parent / "backups").glob("*"), key=lambda item: item.stat().st_mtime) \
            if (path.parent / "backups").is_dir() else []
        if backups:
            from datetime import datetime
            latest = backups[-1]
            when = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            rows.append(("Sao lưu gần nhất", f"{latest.name} · {when} · {latest.stat().st_size / (1024 * 1024):.2f} MB"))
        else:
            rows.append(("Sao lưu gần nhất", "Chưa có bản sao lưu nào"))
        return rows

    def _t6_card(self):
        card = Card("Ngưỡng liveness T6 (lưu trong system_settings)")
        self._t6_status = label("")
        self._t6_status.setWordWrap(True)
        try:
            config = self._settings_service.load_liveness_config()
        except Exception as exc:
            card.box.addWidget(label(f"Không đọc được ngưỡng liveness: {exc}"))
            card.box.addWidget(self._t6_status)
            return card
        grid = QGridLayout(); grid.setSpacing(10)
        for index, (field, caption) in enumerate(self.T6_FIELDS):
            editor = LineEdit(); editor.setText(str(config[field]))
            editor.setEnabled(self._may_write_settings)
            self._t6_inputs[field] = editor
            grid.addWidget(label(caption, "muted"), index // 2, (index % 2) * 2)
            grid.addWidget(editor, index // 2, (index % 2) * 2 + 1)
        card.box.addLayout(grid)
        card.box.addWidget(label("Giá trị được kiểm tra bằng chính bộ kiểm liveness trước khi lưu; "
                                 "thử thách tiếp theo dùng ngưỡng mới mà không cần khởi động lại.", "muted"))
        card.box.addWidget(self._t6_status)
        return card

    def _save_t6(self):
        if not self._t6_inputs:
            return
        values = {field: editor.text().strip() for field, editor in self._t6_inputs.items()}
        try:
            saved = self._settings_service.set_liveness_config(values)
        except Exception as exc:
            self._t6_status.setText(f"Không lưu được: {exc}")
            self._t6_status.setStyleSheet(f"color:{T.ROSE};")
            return
        for field, editor in self._t6_inputs.items():
            editor.setText(str(saved[field]))
        self._t6_status.setText("Đã lưu ngưỡng liveness vào cơ sở dữ liệu.")
        self._t6_status.setStyleSheet(f"color:{T.SAGE};")





class AccountsView(BasePage):
    TITLE = "Tài khoản & phân quyền"

    def build(self, d):
        from app.services.account_service import AccountService
        self._account_service = AccountService()
        from app.ui import session
        self._may_manage_accounts = session.has_permission("account.manage")
        add = PrimaryPushButton("+ Thêm tài khoản")
        add.setEnabled(self._may_manage_accounts)
        if not self._may_manage_accounts:
            add.setToolTip("Tài khoản hiện tại không có quyền account.manage.")
        add.clicked.connect(lambda: D.account_form(self.window(), on_saved=self._refresh_accounts))
        self.head.addWidget(add)
        password = PushButton("Đổi mật khẩu của tôi")
        password.clicked.connect(lambda: D.change_password(self.window(), session.identity().username))
        self.head.addWidget(password)
        self._account_card = Card("Danh sách tài khoản")
        self._roles_card = Card("Vai trò và quyền đã lưu")
        self.body.addWidget(self._account_card); self.body.addWidget(self._roles_card)
        self._refresh_accounts()

    def _refresh_accounts(self):
        from PySide6.QtWidgets import QLabel
        for card in (self._account_card, self._roles_card):
            while card.box.count() > 1:
                item = card.box.takeAt(1)
                if item.widget(): item.widget().deleteLater()
        try:
            accounts, roles, permissions, assignments = self._account_service.directory()
            account_rows = [(row["username"], row["full_name"], row["roles"],
                             {"active": "Hoạt động", "locked": "Đã khóa", "disabled": "Đã vô hiệu hóa"}.get(row["account_status"], row["account_status"]))
                            for row in accounts]
            by_row = {row: (int(record["account_id"]), record["account_status"])
                      for row, record in zip(account_rows, accounts)}

            def row_actions(shown):
                account_id, status = by_row.get(shown, (None, None))
                if not self._may_manage_accounts or account_id is None:
                    return []
                target, caption, tone = (("locked", "Khóa", "late") if status == "active"
                                         else ("active", "Mở khóa", "ok"))
                return [(caption, tone,
                         lambda aid=account_id, value=target: self._set_account_status(aid, value))]

            table = make_table(["Tài khoản", "Họ tên", "Vai trò", "Trạng thái"], account_rows,
                               tone_cols=(3,), actions=row_actions)
            self._account_card.box.addWidget(table)
            if not accounts:
                self._account_card.box.addWidget(label("Chưa có tài khoản trong cơ sở dữ liệu."))
            if roles:
                self._roles_card.box.addWidget(make_table(["Vai trò", "Quyền"], assignments))
                if not assignments: self._roles_card.box.addWidget(label("Có vai trò nhưng chưa có quyền được gán."))
            else:
                self._roles_card.box.addWidget(label("Chưa có vai trò hoặc quyền được cấu hình; không hiển thị ma trận mẫu."))
        except Exception as exc:
            self._account_card.box.addWidget(label(f"Không tải được tài khoản: {exc}"))

    def _set_account_status(self, account_id, status):
        caption = "khóa" if status == "locked" else "mở khóa"
        if not D.confirm(self.window(), f"Xác nhận {caption} tài khoản",
                         f"Tài khoản #{account_id} sẽ được {caption}.", danger=status == "locked"):
            return
        try:
            self._account_service.set_status(account_id, status)
        except Exception as exc:
            D.confirm(self.window(), "Không đổi được trạng thái", str(exc), info=True)
        self._refresh_accounts()
