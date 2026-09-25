"""Threaded OpenCV capture and lifecycle binding for existing preview widgets."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QThread, Qt, Signal
from app.biometric.face_recognition.detector import FaceAnalysisWorker


CaptureFactory = Callable[..., object]
_active_managers = set()
_active_managers_lock = threading.Lock()
_shutdown_hook_installed = False


def _shutdown_active_cameras():
    with _active_managers_lock:
        managers = tuple(_active_managers)
    for manager in managers:
        manager.stop_camera(wait=True)


class CameraWorker(QThread):
    frame_captured = Signal(object)
    camera_opened = Signal()
    camera_error = Signal(str)

    def __init__(self, source=0, *, width=None, height=None, fps=30,
                 capture_factory: Optional[CaptureFactory] = None, parent=None):
        super().__init__(parent)
        self.source = source
        self.width = width
        self.height = height
        self.fps = max(1, int(fps))
        self.capture_factory = capture_factory or cv2.VideoCapture
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        self.requestInterruption()

    def _open_capture(self):
        # Let OpenCV choose the platform's default backend unless a caller injects
        # a custom capture factory.
        return self.capture_factory(self.source)

    def run(self):
        capture = None
        try:
            capture = self._open_capture()
            if capture is None or not capture.isOpened():
                self.camera_error.emit(f"Không mở được camera: {self.source}")
                return

            # Timeout properties are best-effort; some camera backends ignore them.
            for prop_name, value in (("CAP_PROP_OPEN_TIMEOUT_MSEC", 3000),
                                     ("CAP_PROP_READ_TIMEOUT_MSEC", 2000)):
                prop = getattr(cv2, prop_name, None)
                if prop is not None:
                    try:
                        capture.set(prop, value)
                    except Exception:
                        pass
            if self.width:
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
            if self.height:
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
            capture.set(cv2.CAP_PROP_FPS, self.fps)
            self.camera_opened.emit()

            interval = 1.0 / self.fps
            while not self._stop_event.is_set() and not self.isInterruptionRequested():
                started = time.monotonic()
                ok, frame = capture.read()
                if not ok or frame is None:
                    if not self._stop_event.is_set():
                        self.camera_error.emit("Camera không trả về frame hợp lệ.")
                    break
                if not isinstance(frame, np.ndarray) or frame.ndim not in (2, 3):
                    self.camera_error.emit("Camera trả về frame sai định dạng.")
                    break
                self.frame_captured.emit(frame.copy())
                self._stop_event.wait(max(0.0, interval - (time.monotonic() - started)))
        except Exception as exc:
            self.camera_error.emit(f"Lỗi camera: {exc}")
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception as exc:
                    self.camera_error.emit(f"Lỗi giải phóng camera: {exc}")


class CameraManager(QObject):
    """Reusable, single-camera-in-process capture service.

    `frame_ready` emits copied OpenCV frames in BGR (or grayscale if the driver
    supplies grayscale). `get_latest_frame()` returns an independent copy.
    """
    frame_ready = Signal(object)
    camera_opened = Signal()
    camera_stopped = Signal()
    camera_error = Signal(str)

    _device_lease = threading.Lock()

    def __init__(self, parent=None, *, capture_factory: Optional[CaptureFactory] = None):
        super().__init__(parent)
        self._capture_factory = capture_factory
        self._worker: Optional[CameraWorker] = None
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._lease_held = False

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def start_camera(self, source=0, *, width=1280, height=720, fps=30) -> bool:
        """Start capture asynchronously; false means already active or device busy."""
        if self.is_running:
            return False
        if self._worker is not None:
            previous = self._worker
            previous.wait()
            self._on_worker_finished(previous)
        if not self._device_lease.acquire(blocking=False):
            self.camera_error.emit("Camera đang được sử dụng bởi một preview khác.")
            return False
        self._lease_held = True
        worker = CameraWorker(source, width=width, height=height, fps=fps,
                              capture_factory=self._capture_factory, parent=self)
        worker.frame_captured.connect(self._on_frame, Qt.ConnectionType.QueuedConnection)
        worker.camera_opened.connect(self.camera_opened, Qt.ConnectionType.QueuedConnection)
        worker.camera_error.connect(self.camera_error, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(lambda w=worker: self._on_worker_finished(w), Qt.ConnectionType.QueuedConnection)
        self._worker = worker
        with _active_managers_lock:
            _active_managers.add(self)
        global _shutdown_hook_installed
        app = QCoreApplication.instance()
        if app is not None and not _shutdown_hook_installed:
            app.aboutToQuit.connect(_shutdown_active_cameras)
            _shutdown_hook_installed = True
        worker.start()
        return True

    def _on_frame(self, frame):
        with self._frame_lock:
            self._latest_frame = frame.copy()
        self.frame_ready.emit(frame)

    def _on_worker_finished(self, worker):
        # stop_camera(wait=True) and QThread.finished can both reach this
        # callback. Finalize a worker exactly once during dialog teardown.
        if getattr(worker, "_camera_finalized", False):
            return
        worker._camera_finalized = True
        # The capture thread owns and releases VideoCapture. The lease can be
        # returned only after its run() finally block has completed.
        is_current_worker = self._worker is worker
        if is_current_worker:
            if self._lease_held:
                self._lease_held = False
                self._device_lease.release()
            self._worker = None
            with _active_managers_lock:
                _active_managers.discard(self)
            with self._frame_lock:
                self._latest_frame = None
            self.camera_stopped.emit()
        worker.deleteLater()

    def get_latest_frame(self):
        with self._frame_lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def stop_camera(self, *, wait=True, timeout_ms=None) -> bool:
        worker = self._worker
        if worker is None:
            return True
        worker.stop()
        if not wait:
            return True
        stopped = worker.wait() if timeout_ms is None else worker.wait(int(timeout_ms))
        if stopped:
            self._on_worker_finished(worker)
        return bool(stopped)


class CameraPreviewController(QObject):
    """Starts/stops CameraManager with preview visibility and sends real frames to it."""

    face_analysis_ready = Signal(object, object)
    face_analysis_error = Signal(str)
    sample_analysis_ready = Signal(int, object, object)
    sample_analysis_error = Signal(int, str)

    def __init__(self, preview_widget, *, source=0, parent=None,
                 capture_factory: Optional[CaptureFactory] = None,
                 enable_face_analysis=False, enable_matching=False,
                 matching_service_factory=None):
        super().__init__(parent or preview_widget)
        self.preview_widget = preview_widget
        # Keep capture alive until its worker has released VideoCapture even if
        # the dialog/preview is being destroyed during an in-flight read.
        self.camera = CameraManager(capture_factory=capture_factory)
        self.camera.frame_ready.connect(preview_widget.set_cv_frame)
        self._face_worker = None
        if enable_face_analysis:
            self._face_worker = FaceAnalysisWorker(
                parent=self, enable_matching=enable_matching,
                matching_service_factory=matching_service_factory,
            )
            self.camera.frame_ready.connect(self._face_worker.submit_frame)
            self._face_worker.analysis_ready.connect(self._on_face_analysis_from_worker)
            self._face_worker.analysis_error.connect(self.face_analysis_error)
            self._face_worker.sample_analysis_ready.connect(self.sample_analysis_ready)
            self._face_worker.sample_analysis_error.connect(self.sample_analysis_error)
        self.camera.camera_opened.connect(self._on_camera_opened)
        self.camera.camera_error.connect(self._on_camera_error)
        self.camera.camera_stopped.connect(self._on_camera_stopped)
        self.source = source
        self._stopping_for_hide = False
        self._restart_requested = False
        self._had_error = False
        self._shutdown_complete = False
        self._camera_accept_analysis = False
        preview_widget.installEventFilter(self)
        preview_widget.destroyed.connect(self.shutdown)
        if preview_widget.isVisible():
            self.start()

    def start(self):
        was_stopping = self._stopping_for_hide
        self._stopping_for_hide = False
        self._had_error = False
        if self._face_worker is not None:
            self._face_worker.request_tracking_reset()
        self._clear_face_overlay()
        if self.camera.is_running:
            if was_stopping:
                self._restart_requested = True
                self.preview_widget.set_camera_status("Đang kết nối lại camera…")
            else:
                self.preview_widget.set_camera_status("Camera đang hoạt động")
            return False
        self.preview_widget.set_camera_status("Đang mở camera…")
        started = self.camera.start_camera(self.source)
        self._camera_accept_analysis = bool(started or self.camera.is_running)
        if not started and self.camera.is_running and was_stopping:
            self._restart_requested = True
        return started

    def stop(self):
        self._camera_accept_analysis = False
        self._clear_face_overlay()
        if self._face_worker is not None:
            self._face_worker.request_tracking_reset()
        return self.camera.stop_camera(wait=False)

    def capture_sample(self, sample_index):
        """Queue the latest actual camera frame for enrollment inference."""
        if self._face_worker is None:
            return False
        frame = self.camera.get_latest_frame()
        if frame is None:
            return False
        return self._face_worker.submit_sample(sample_index, frame)

    def shutdown(self, *_):
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        self._camera_accept_analysis = False
        self.camera.stop_camera(wait=True)
        if self._face_worker is not None and self._face_worker.isRunning():
            self._face_worker.stop_worker()

    def _on_camera_opened(self):
        self._camera_accept_analysis = True
        self._had_error = False
        self.preview_widget.set_camera_status("Camera đang hoạt động")

    def _on_camera_error(self, message):
        self._camera_accept_analysis = False
        self._had_error = True
        self.preview_widget.set_camera_status(message)

    def _on_camera_stopped(self):
        self._camera_accept_analysis = False
        self._clear_face_overlay()
        if self._face_worker is not None:
            self._face_worker.request_tracking_reset()
        if self._restart_requested and self.preview_widget.isVisible():
            self._restart_requested = False
            self._stopping_for_hide = False
            self.start()
        elif self.preview_widget.isVisible() and not self._had_error:
            self.preview_widget.set_camera_status("Camera đã dừng")

    def _clear_face_overlay(self):
        self.preview_widget.set_face_bbox(None)
        setter = getattr(self.preview_widget, "set_face_landmarks", None)
        if setter is not None:
            setter(None)

    def _on_face_analysis_from_worker(self, frame, result):
        if self._camera_accept_analysis and not self._shutdown_complete:
            setter = getattr(self.preview_widget, "set_face_landmarks", None)
            if setter is not None:
                # Only the Max-Area face has a paired mesh, so the overlay can
                # never follow a bystander.
                setter(getattr(result, "mediapipe_landmarks", None), getattr(frame, "shape", None))
            self.face_analysis_ready.emit(frame, result)

    def eventFilter(self, watched, event):
        if watched is self.preview_widget:
            if event.type() == QEvent.Type.Show:
                self.start()
            elif event.type() == QEvent.Type.Hide:
                self._stopping_for_hide = True
                self.stop()
        return super().eventFilter(watched, event)
