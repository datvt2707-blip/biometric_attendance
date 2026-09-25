"""
widgets.py — LINH KIỆN GIAO DIỆN DÙNG LẠI
LÀM GÌ   : Card, thẻ thống kê, thẻ trạng thái (tag), bảng (make_table), nút hành động trong bảng (action_cell),
             thẻ thông tin người dùng, thanh chọn Pill, các bí danh nút/ô nhập vuông.
CÔNG NGHỆ: Qt Widgets (QFrame, QTableWidget, QPushButton...) + QSS nội tuyến (setStyleSheet)
             + QPainter cho: Bar (thanh %), LineChart (biểu đồ đường), StepsBar (các bước xoay mặt),
             CameraView (khung camera, có set_frame để nhận ảnh OpenCV).
NGHIỆP VỤ: Không có nghiệp vụ, chỉ là gạch xây giao diện.
CHI TIẾT : docs/UI_GUIDE.md (tìm theo tên file)
"""
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (QPainter, QColor, QPen, QPolygonF, QRadialGradient, QPainterPath)
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QTableWidget, QTableWidgetItem, QHeaderView
from app.ui import theme as T


def label(text, name=None, color=None):
    lb = QLabel(text)
    if name: lb.setObjectName(name)
    if color: lb.setStyleSheet(f"color:{color};")
    return lb


def tone_of(text):
    if any(k in text for k in ("Đang", "Có mặt", "Thành", "Đã đăng", "Hoàn")): return "ok"
    if any(k in text for k in ("Nghỉ phép", "Bảo", "Chưa")): return "wait"
    return "late"


class Card(QFrame):
    def __init__(self, title=None):
        super().__init__()
        self.setObjectName("card")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(18, 16, 18, 16)
        self.box.setSpacing(10)
        if title: self.box.addWidget(label(title, "cardTitle"))


def stat_card(title, value, note, tone):
    c = Card()
    c.box.setSpacing(2)
    c.box.addWidget(label(title, "muted"))
    c.box.addWidget(label(value, "big"))
    c.box.addWidget(label(note, "muted", T.TONE[tone]))
    return c


def tag(text, tone):
    col = T.TONE[tone]
    lb = QLabel(text)
    lb.setStyleSheet(f"color:{col}; border:1px solid {col}; border-radius:0px; padding:1px 9px; font-size:11px;")
    return lb


def make_table(headers, rows, tone_cols=()):
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionMode(QTableWidget.NoSelection)
    t.setShowGrid(False)
    t.setFocusPolicy(Qt.NoFocus)
    for r, row in enumerate(rows):
        t.setRowHeight(r, 42)
        for c, val in enumerate(row):
            it = QTableWidgetItem(val)
            if c in tone_cols: it.setForeground(QColor(T.TONE[tone_of(val)]))
            t.setItem(r, c, it)
    t.setFixedHeight(42 * len(rows) + 40)
    return t


class Bar(QWidget):
    def __init__(self, pct, color):
        super().__init__()
        self.pct, self.color = pct, color
        self.setFixedHeight(6)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.CARD2)); p.drawRect(self.rect())
        p.setBrush(QColor(self.color)); p.drawRect(0, 0, int(self.width() * self.pct / 100), 6)


def bar_row(name, pct, tone):
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(5)
    h = QHBoxLayout(); h.addWidget(label(name)); h.addStretch(); h.addWidget(label(f"{pct}%", "muted"))
    v.addLayout(h)
    v.addWidget(Bar(pct, T.BRASS if tone == "brass" else T.TONE[tone]))
    return w


def activity_row(ini, name, sub, status):
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 4, 0, 4); h.setSpacing(10)
    av = label(ini, "avatar"); av.setFixedSize(32, 32); av.setAlignment(Qt.AlignCenter)
    col = QVBoxLayout(); col.setSpacing(0); col.addWidget(label(name)); col.addWidget(label(sub, "muted"))
    h.addWidget(av); h.addLayout(col, 1); h.addWidget(tag(status, tone_of(status)))
    return w


class LineChart(QWidget):
    DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

    def __init__(self, values, labels=None):
        super().__init__()
        self.values = values
        self.labels = labels or self.DAYS
        self.setMinimumHeight(170)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h, l, t, b = self.width(), self.height(), 10, 10, 24
        p.setPen(QPen(QColor(T.LINE), 1, Qt.DashLine))
        for i in range(3):
            y = t + i * (h - t - b) / 2
            p.drawLine(QPointF(l, y), QPointF(w - l, y))
        n = len(self.values)
        maximum = max(1, max(self.values, default=0))
        pts = [QPointF(l + i * (w - 2 * l) / max(1, n - 1),
                       t + (maximum - v) / maximum * (h - t - b)) for i, v in enumerate(self.values)]
        p.setPen(QPen(QColor(T.BRASS), 2)); p.drawPolyline(QPolygonF(pts))
        p.setBrush(QColor(T.CARD))
        for pt in pts: p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
        p.setPen(QColor(T.MUT))
        for pt, d in zip(pts, self.labels): p.drawText(QPointF(pt.x() - 12, h - 6), d)


class StepsBar(QWidget):
    def __init__(self, steps, cur):
        super().__init__()
        self.steps, self.cur = steps, cur
        self.setFixedHeight(56)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        n, w = len(self.steps), self.width(); cw = w / n
        p.setPen(QPen(QColor(T.LINE), 1)); p.drawLine(QPointF(cw / 2, 12), QPointF(w - cw / 2, 12))
        for i, s in enumerate(self.steps):
            x = (i + .5) * cw
            if i < self.cur: p.setPen(Qt.NoPen); p.setBrush(QColor(T.SAGE)); p.drawRect(QRectF(x - 9, 3, 18, 18))
            elif i == self.cur:
                p.setPen(Qt.NoPen); p.setBrush(QColor(184, 155, 98, 50)); p.drawRect(QRectF(x - 13, -1, 26, 26))
                p.setPen(QPen(QColor(T.BRASS), 2)); p.setBrush(QColor(T.CARD)); p.drawRect(QRectF(x - 9, 3, 18, 18))
            else: p.setPen(QPen(QColor(T.LINE), 2)); p.setBrush(QColor(T.CARD)); p.drawRect(QRectF(x - 9, 3, 18, 18))
            p.setPen(QColor(T.BRASS if i == self.cur else T.TX if i < self.cur else T.MUT))
            p.drawText(QRectF(x - cw / 2, 30, cw, 20), Qt.AlignCenter, s)


class CameraView(QWidget):
    """Khung camera. Gọi set_frame(QImage) mỗi khi CameraManager có frame mới."""
    def __init__(self, chip=""):
        super().__init__()
        self.chip, self.frame = chip, None
        self.face_bbox = None
        self.face_landmarks = None
        self.frame_size = None
        self.preview_mirrored = False
        self.camera_status = "Camera chưa kết nối"
        self.setMinimumSize(360, 280)

    def set_frame(self, qimage):
        self.frame = qimage; self.update()

    def set_cv_frame(self, frame):
        """Display a copied OpenCV BGR/grayscale frame without changing layout."""
        import numpy as np
        from PySide6.QtGui import QImage
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            return
        frame = np.ascontiguousarray(frame)
        if frame.ndim == 2:
            fmt = QImage.Format.Format_Grayscale8
        elif frame.ndim == 3 and frame.shape[2] == 3:
            fmt = QImage.Format.Format_BGR888
        elif frame.ndim == 3 and frame.shape[2] == 4:
            fmt = QImage.Format.Format_ARGB32
        else:
            self.set_camera_status("Frame camera sai định dạng")
            return
        height, width = frame.shape[:2]
        self.frame_size = (width, height)
        image = QImage(frame.data, width, height, int(frame.strides[0]), fmt).copy()
        self.set_frame(image)
        self.set_camera_status("Camera đang hoạt động")

    def set_face_bbox(self, bbox, frame_shape=None):
        """Set an original-frame pixel box; None clears the overlay."""
        self.face_bbox = tuple(float(value) for value in bbox) if bbox is not None else None
        if frame_shape is not None:
            self.frame_size = (int(frame_shape[1]), int(frame_shape[0]))
        self.update()

    def set_face_landmarks(self, landmarks, frame_shape=None):
        """Set the MediaPipe mesh of the selected face; None clears the overlay."""
        import numpy as np
        if landmarks is None:
            self.face_landmarks = None
        else:
            points = np.asarray(landmarks, dtype=np.float64)
            valid = (points.ndim == 2 and points.shape[0] >= 3 and points.shape[1] in (2, 3)
                     and np.all(np.isfinite(points)))
            self.face_landmarks = points[:, :2] if valid else None
            # Resolve MediaPipe's tesselation here: importing it from inside
            # paintEvent destabilises Qt teardown.
            face_mesh_connections()
        if frame_shape is not None and len(tuple(frame_shape)) >= 2:
            self.frame_size = (int(frame_shape[1]), int(frame_shape[0]))
        self.update()

    def set_camera_status(self, message):
        self.camera_status = str(message)
        self.setToolTip(self.camera_status)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = QPainterPath(); path.addRect(r); p.setClipPath(path)
        if self.frame:
            frame = self.frame.mirrored(True, False) if self.preview_mirrored else self.frame
            p.drawImage(r, frame)
        else:
            g = QRadialGradient(r.center().x(), r.height() * .4, r.width() * .6)
            g.setColorAt(0, QColor("#25313D")); g.setColorAt(1, QColor("#0E1318")); p.fillRect(r, g)
            p.setPen(QPen(QColor(T.MUT), 1.4)); p.setBrush(Qt.NoBrush)
            cx, fw = r.center().x(), r.width() * .13
            p.drawEllipse(QPointF(cx, r.height() * .42), fw, fw * 1.25)
            p.drawArc(QRectF(cx - fw * 1.9, r.height() * .72, fw * 3.8, fw * 3), 0, 180 * 16)
        if self.face_bbox is not None and self.frame_size is not None:
            fr = map_bbox_to_preview(self.face_bbox, self.frame_size, r, self.preview_mirrored)
            p.setPen(QPen(QColor(T.SAGE), 1.6)); p.setBrush(Qt.NoBrush)
            p.drawRect(fr)
        if self.face_landmarks is not None and self.frame_size is not None:
            self._paint_face_mesh(p, r)
        p.setClipping(False)
        p.setPen(QPen(QColor(T.LINE), 1)); p.drawPath(path)
        p.setBrush(QColor(12, 17, 22, 210)); p.setPen(QPen(QColor("#3B5A4D"), 1))
        p.drawRect(QRectF(12, 12, 170, 24))
        p.setPen(QColor(T.SAGE)); p.drawText(QRectF(12, 12, 170, 24), Qt.AlignCenter, self.chip)
        p.setPen(Qt.NoPen); p.setBrush(QColor(T.ROSE)); p.drawRect(QRectF(16.5, r.height() - 21.5, 7, 7))
        p.setPen(QColor(T.MUT)); p.drawText(QPointF(30, r.height() - 14), self.camera_status[:48])


    def _paint_face_mesh(self, p, r):
        """Draw the MediaPipe tesselation and landmark dots over the live frame."""
        points = map_landmarks_to_preview(self.face_landmarks, self.frame_size, r,
                                          self.preview_mirrored)
        mesh = QPainterPath()
        for start, end in face_mesh_connections():
            if start < len(points) and end < len(points):
                mesh.moveTo(QPointF(*points[start]))
                mesh.lineTo(QPointF(*points[end]))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(122, 168, 143, 90), 0.6))
        p.drawPath(mesh)
        p.setPen(Qt.NoPen); p.setBrush(QColor(T.BRASS))
        for x, y in points:
            p.drawEllipse(QPointF(x, y), 0.9, 0.9)
        p.setBrush(Qt.NoBrush)  # the frame outline below must not be filled


_MESH_CONNECTIONS = None


def face_mesh_connections():
    """MediaPipe's own tesselation index pairs; empty when MediaPipe is absent."""
    global _MESH_CONNECTIONS
    if _MESH_CONNECTIONS is None:
        try:
            from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections
            _MESH_CONNECTIONS = tuple(
                (int(c.start), int(c.end))
                for c in FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION
            )
        except Exception:
            _MESH_CONNECTIONS = ()
    return _MESH_CONNECTIONS


def map_landmarks_to_preview(landmarks, frame_size, preview_rect, mirrored=False):
    """Map normalized MediaPipe landmarks onto the stretched preview rectangle.

    Mirroring matches the bounding box so the mesh stays on the same face when
    the preview shows a selfie view.
    """
    import numpy as np
    frame_width, frame_height = map(float, frame_size)
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame_size must be positive")
    points = np.asarray(landmarks, dtype=np.float64)[:, :2].copy()
    if mirrored:
        points[:, 0] = 1.0 - points[:, 0]
    points[:, 0] = preview_rect.left() + points[:, 0] * preview_rect.width()
    points[:, 1] = preview_rect.top() + points[:, 1] * preview_rect.height()
    return points


def map_bbox_to_preview(bbox, frame_size, preview_rect, mirrored=False):
    """Map source pixel coordinates to the stretched preview rectangle."""
    frame_width, frame_height = map(float, frame_size)
    x1, y1, x2, y2 = map(float, bbox)
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame_size must be positive")
    x1, x2 = max(0.0, min(frame_width, x1)), max(0.0, min(frame_width, x2))
    y1, y2 = max(0.0, min(frame_height, y1)), max(0.0, min(frame_height, y2))
    if mirrored:
        x1, x2 = frame_width - x2, frame_width - x1
    left = preview_rect.left() + x1 / frame_width * preview_rect.width()
    top = preview_rect.top() + y1 / frame_height * preview_rect.height()
    right = preview_rect.left() + x2 / frame_width * preview_rect.width()
    bottom = preview_rect.top() + y2 / frame_height * preview_rect.height()
    return QRectF(left, top, max(0.0, right - left), max(0.0, bottom - top))


# ---------- bổ sung v2 ----------
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QButtonGroup


def tone_of(text):
    if any(k in text for k in ("Đang", "Có mặt", "Thành", "Đã đăng", "Hoàn", "Đã duyệt", "Hoạt động")): return "ok"
    if any(k in text for k in ("Nghỉ phép", "Bảo", "Chưa", "Chờ", "Có phép")): return "wait"
    return "late"


class Pill(QFrame):
    """Thanh chọn dạng viên thuốc: chỉ ô đang chọn được tô, hover chỉ đổi màu chữ."""
    changed = Signal(int)

    def __init__(self, items):
        super().__init__()
        self.setObjectName("pill")
        h = QHBoxLayout(self); h.setContentsMargins(3, 3, 3, 3); h.setSpacing(2)
        self.g = QButtonGroup(self)
        for i, t in enumerate(items):
            b = QPushButton(t); b.setCheckable(True); b.setChecked(i == 0)
            b.setCursor(Qt.PointingHandCursor); self.g.addButton(b, i); h.addWidget(b)
        self.g.idClicked.connect(self.changed)


def action_cell(items):
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(6, 4, 6, 4); h.setSpacing(6)
    for it in items:
        text, tone = it[0], it[1]
        col = T.TONE.get(tone, T.BRASS)
        b = QPushButton(text); b.setCursor(Qt.PointingHandCursor)
        if len(it) > 2: b.clicked.connect(lambda _=False, f=it[2]: f())
        b.setStyleSheet(f"QPushButton{{color:{col};border:1px solid {col};border-radius:0px;padding:3px 12px;background:transparent;}}"
                        f"QPushButton:hover{{background:{T.CARD2};}}")
        h.addWidget(b)
    h.addStretch()
    return w


def make_table(headers, rows, tone_cols=(), actions=None):
    n = len(headers) + (1 if actions else 0)
    t = QTableWidget(len(rows), n)
    t.setHorizontalHeaderLabels(list(headers) + (["Thao tác"] if actions else []))
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.setEditTriggers(QTableWidget.NoEditTriggers); t.setSelectionMode(QTableWidget.NoSelection)
    t.setShowGrid(False); t.setFocusPolicy(Qt.NoFocus)
    for r, row in enumerate(rows):
        t.setRowHeight(r, 46)
        for c, val in enumerate(row):
            it = QTableWidgetItem(val)
            if c in tone_cols: it.setForeground(QColor(T.TONE[tone_of(val)]))
            t.setItem(r, c, it)
        if actions: t.setCellWidget(r, n - 1, action_cell(actions(row)))
    t.setFixedHeight(46 * len(rows) + 42)
    return t


def user_chip():
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
    from app.ui import session; r = session.role(); av = label("".join(x[0] for x in r["name"].split())[:2].upper(), "avatar"); av.setFixedSize(32, 32); av.setAlignment(Qt.AlignCenter)
    c = QVBoxLayout(); c.setSpacing(0); c.addWidget(label(r["name"])); c.addWidget(label(r["title"], "muted"))
    h.addWidget(av); h.addLayout(c)
    return w


from PySide6.QtWidgets import QLineEdit, QComboBox, QCheckBox


def PrimaryPushButton(t):
    b = QPushButton(t); b.setObjectName("primary"); b.setCursor(Qt.PointingHandCursor); return b


def PushButton(t):
    b = QPushButton(t); b.setObjectName("ghost"); b.setCursor(Qt.PointingHandCursor); return b


def LineEdit(): return QLineEdit()
def SearchLineEdit(): return QLineEdit()
def PasswordLineEdit():
    e = QLineEdit(); e.setEchoMode(QLineEdit.Password); return e
ComboBox = QComboBox
CheckBox = QCheckBox
