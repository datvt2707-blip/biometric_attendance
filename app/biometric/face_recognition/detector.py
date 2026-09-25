"""InsightFace buffalo_l loading and asynchronous frame analysis."""
from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

from app.biometric.liveness.active_liveness import landmarks_for_selected_face
from app.biometric.preprocessing.face_filter import FaceDetection


class DetectorUnavailableError(RuntimeError):
    """Model pack download, loading, or inference failed."""


class InsightFaceDetector:
    """One process-wide FaceAnalysis instance; uses InsightFace's buffalo_l pack."""

    _instance_lock = threading.Lock()
    _instances = {}

    def __init__(self, *, name="buffalo_l", root=None, det_size=(640, 640), confidence=0.5):
        self.name = name
        self.root = Path(root or Path.home() / ".insightface").expanduser()
        self.model_dir = self.root / "models" / name
        key = (str(self.root.resolve()), name, tuple(det_size), float(confidence))
        with self._instance_lock:
            analysis = self._instances.get(key)
            if analysis is None:
                try:
                    from insightface.app import FaceAnalysis
                    analysis = FaceAnalysis(
                        name=name,
                        root=str(self.root),
                        allowed_modules=["detection", "recognition"],
                        providers=["CPUExecutionProvider"],
                    )
                    analysis.prepare(ctx_id=-1, det_thresh=float(confidence), det_size=tuple(det_size))
                except Exception as exc:
                    raise DetectorUnavailableError(
                        f"InsightFace không tải/khởi tạo được model '{name}' tại {self.root}: {exc}"
                    ) from exc
                self._instances[key] = analysis
        self._analysis = analysis
        self._models = getattr(analysis, "models", {})
        self._loaded_model_files = tuple(
            str(getattr(getattr(model, "session", None), "_model_path", ""))
            for model in self._models.values()
        )

    @property
    def analysis(self):
        return self._analysis

    @property
    def loaded_modules(self):
        return tuple(self._models.keys())

    @property
    def loaded_model_files(self):
        return tuple(path for path in self._loaded_model_files if path)

    def analyze(self, bgr_image):
        """Run FaceAnalysis.get (detector + recognition) on an original BGR frame."""
        if not isinstance(bgr_image, np.ndarray) or bgr_image.size == 0:
            raise ValueError("bgr_image must be a non-empty NumPy image")
        try:
            return self._analysis.get(bgr_image)
        except Exception as exc:
            raise DetectorUnavailableError(f"InsightFace inference failed: {exc}") from exc

    def detect(self, bgr_image):
        return [
            FaceDetection(
                bbox=tuple(float(value) for value in face.bbox[:4]),
                confidence=float(getattr(face, "det_score", 0.0)),
            )
            for face in self.analyze(bgr_image)
        ]


class FaceAnalysisWorker(QThread):
    """Load and run InsightFace away from the UI thread; coalesces pending frames."""

    model_ready = Signal(object)
    analysis_ready = Signal(object, object)
    analysis_error = Signal(str)
    sample_analysis_ready = Signal(int, object, object)
    sample_analysis_error = Signal(int, str)

    def __init__(self, *, name="buffalo_l", root=None, det_size=(640, 640), parent=None,
                 enable_matching=False, matching_service_factory=None):
        super().__init__(parent)
        self._options = dict(name=name, root=root, det_size=det_size)
        self._lock = threading.Lock()
        self._latest = None
        self._sample_requests = []
        self._wake_event = threading.Event()
        self._detector: Optional[InsightFaceDetector] = None
        self._recognizer = None
        self._load_failed = False
        self._enable_matching = bool(enable_matching)
        self._matching_service_factory = matching_service_factory
        self._reset_tracking_requested = False
        self._frame_sequence = 0
        self._liveness_landmarker = None
        self._liveness_error = ""
        self._liveness_config = None
        self._liveness_generation = None

    def stop_worker(self):
        self.requestInterruption()
        self._wake_event.set()
        return self.wait()

    def submit_frame(self, bgr_image):
        if bgr_image is None or self._load_failed:
            return
        with self._lock:
            self._latest = np.ascontiguousarray(bgr_image.copy())
        if not self.isRunning():
            self.start()
        self._wake_event.set()

    def submit_sample(self, sample_index, bgr_image):
        if bgr_image is None or self._load_failed:
            return False
        with self._lock:
            self._sample_requests.append((int(sample_index), np.ascontiguousarray(bgr_image.copy())))
        if not self.isRunning():
            self.start()
        self._wake_event.set()
        return True

    def request_tracking_reset(self):
        with self._lock:
            self._reset_tracking_requested = True
            self._latest = None
        self._wake_event.set()

    def _attach_landmarks(self, result, frame):
        """Bind the MediaPipe mesh of the Max-Area face; bystanders are tolerated."""
        if self._liveness_landmarker is None or result.status != "face_selected":
            return result
        try:
            faces = self._liveness_landmarker.detect(frame)
            landmarks = landmarks_for_selected_face(
                faces, getattr(result.selected, "bbox", None), frame.shape,
            )
        except Exception as exc:
            return replace(result, liveness_error=f"MediaPipe inference failed: {exc}")
        if landmarks is None:
            return replace(result, liveness_error="MediaPipe không có landmark khớp khuôn mặt đã chọn.")
        return replace(result, mediapipe_landmarks=landmarks)

    def _reload_liveness_config(self):
        """Pick up thresholds edited in the settings screen without restarting."""
        if self._liveness_generation is None:
            return
        try:
            from app.services.settings_service import SettingsService, liveness_config_generation
            generation = liveness_config_generation()
            if generation == self._liveness_generation:
                return
            self._liveness_config = SettingsService().load_liveness_config()
            self._liveness_generation = generation
        except Exception as exc:
            self._liveness_error = f"Không nạp lại được ngưỡng liveness: {exc}"

    def run(self):
        # Load on this QThread, not on the camera preview/UI thread.
        try:
            self._detector = InsightFaceDetector(**self._options)
        except DetectorUnavailableError as exc:
            self._load_failed = True
            self.analysis_error.emit(str(exc))
            return
        from app.biometric.face_recognition.face_recognizer import FaceRecognizer
        self._recognizer = FaceRecognizer(self._detector)
        try:
            from app.services.settings_service import SettingsService
            from app.services.settings_service import liveness_config_generation
            self._liveness_generation = liveness_config_generation()
            self._liveness_config = SettingsService().load_liveness_config()
            from app.biometric.liveness.active_liveness import (
                MediaPipeFaceLandmarker, MediaPipeUnavailableError,
            )
            self._liveness_landmarker = MediaPipeFaceLandmarker()
        except Exception as exc:
            # Recognition and explicit development mode remain usable; production
            # attendance remains blocked by the missing MediaPipe result.
            self._liveness_error = str(exc)
        matcher = None
        if self._enable_matching:
            try:
                factory = self._matching_service_factory
                if factory is None:
                    from app.services.face_matching_service import FaceMatchingService
                    factory = FaceMatchingService
                matcher = factory()
            except Exception as exc:
                self.analysis_error.emit(f"Không khởi tạo được dịch vụ so khớp: {exc}")
                self._load_failed = True
                return
        self.model_ready.emit(self._detector)
        while not self.isInterruptionRequested():
            self._wake_event.wait()
            self._wake_event.clear()
            if self.isInterruptionRequested():
                break
            with self._lock:
                sample_request = self._sample_requests.pop(0) if self._sample_requests else None
                frame, self._latest = self._latest, None
                reset_tracking, self._reset_tracking_requested = self._reset_tracking_requested, False
            if reset_tracking:
                self._recognizer.reset_tracking()
            if sample_request is not None:
                sample_index, sample_frame = sample_request
                try:
                    result = self._recognizer.analyze(sample_frame)
                    self._frame_sequence += 1
                    result = replace(result, frame_sequence=self._frame_sequence)
                    self.sample_analysis_ready.emit(sample_index, sample_frame, result)
                except Exception as exc:
                    self.sample_analysis_error.emit(sample_index, str(exc))
                continue
            if frame is None:
                continue
            try:
                result = self._recognizer.analyze(frame)
                self._frame_sequence += 1
                result = replace(result, frame_sequence=self._frame_sequence)
                if matcher is not None and result.status == "face_selected" and result.embedding is not None:
                    match_result = matcher.match(
                        result.embedding, model_name=result.model_name,
                        model_version=result.model_version,
                    )
                    result = replace(result, match_result=match_result)
                result = self._attach_landmarks(result, frame)
                self._reload_liveness_config()
                result = replace(result, liveness_config=self._liveness_config,
                                 liveness_error=result.liveness_error or self._liveness_error)
                self.analysis_ready.emit(frame, result)
            except Exception as exc:
                self.analysis_error.emit(str(exc))
        if self._liveness_landmarker is not None:
            try:
                self._liveness_landmarker.close()
            except Exception:
                pass
