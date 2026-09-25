"""Face selection, identity continuity, and real embedding extraction."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from app.biometric.face_recognition.embeddings import embedding_from_face
from app.biometric.preprocessing.face_filter import FaceDetection, FaceFilterConfig, select_face
from app.biometric.preprocessing.image_preprocessing import PreprocessingConfig, preprocess_face

# T3: real histogram equalization (cv2.equalizeHist on luminance), not CLAHE.
RECOGNITION_PREPROCESSING = PreprocessingConfig(equalization="histogram")


@dataclass(frozen=True)
class FaceAnalysisResult:
    status: str
    face_count: int
    detections: tuple[FaceDetection, ...]
    selected: Optional[FaceDetection]
    embedding: object = None
    embedding_shape: Optional[tuple[int, ...]] = None
    reason: str = ""
    model_name: str = ""
    model_version: str = ""
    tracking_bbox: Optional[tuple[float, float, float, float]] = None
    match_result: object = None
    landmarks: object = None
    tracking_id: Optional[int] = None
    frame_sequence: int = 0
    preprocessing: str = ""
    mediapipe_landmarks: object = None
    liveness_config: object = None
    liveness_error: str = ""


class FaceRecognizer:
    """Select one safe face and maintain a smoothed, embedding-checked track.

    Coordinates and InsightFace input stay in original BGR pixel space. The
    default scan window is configurable and spans 94% of each frame dimension.
    """

    def __init__(self, detector, *, config=FaceFilterConfig(), roi=None,
                 scan_region=(0.03, 0.03, 0.97, 0.97), smoothing=0.35,
                 max_lost_frames=3, track_similarity_floor=0.45,
                 preprocessing=RECOGNITION_PREPROCESSING):
        self.detector = detector
        self.config = config
        self.preprocessing = preprocessing
        self.roi = roi
        self.scan_region = tuple(float(v) for v in scan_region)
        if len(self.scan_region) != 4 or not (0 <= self.scan_region[0] < self.scan_region[2] <= 1
                                               and 0 <= self.scan_region[1] < self.scan_region[3] <= 1):
            raise ValueError("scan_region must be normalized x1,y1,x2,y2 bounds")
        if not 0 < float(smoothing) <= 1:
            raise ValueError("smoothing must be in (0, 1]")
        self.smoothing = float(smoothing)
        self.max_lost_frames = max(0, int(max_lost_frames))
        self.track_similarity_floor = float(track_similarity_floor)
        self._previous_embedding = None
        self._smoothed_bbox = None
        self._lost_frames = 0
        self._track_serial = 0
        self._tracking_id = None
        self.model_name = getattr(detector, "name", "")
        recognition_model = getattr(detector, "analysis", None)
        recognition_model = getattr(recognition_model, "models", {}).get("recognition")
        self.recognition_model = recognition_model
        session = getattr(recognition_model, "session", None)
        model_path = getattr(session, "_model_path", "")
        self.model_version = Path(model_path).name if model_path else ""

    def reset_tracking(self):
        self._previous_embedding = None
        self._smoothed_bbox = None
        self._lost_frames = 0
        self._tracking_id = None

    def _tracking_bbox_after_loss(self):
        self._lost_frames += 1
        if self._lost_frames > self.max_lost_frames:
            self.reset_tracking()
            return None
        return self._smoothed_bbox

    def analyze(self, bgr_image) -> FaceAnalysisResult:
        faces = self.detector.analyze(bgr_image)
        detections = tuple(
            FaceDetection(tuple(float(value) for value in face.bbox[:4]),
                          float(getattr(face, "det_score", 0.0)))
            for face in faces
        )
        height, width = bgr_image.shape[:2]
        scan_roi = tuple((self.roi or (0, 0, 0, 0))) if self.roi is not None else (
            self.scan_region[0] * width, self.scan_region[1] * height,
            self.scan_region[2] * width, self.scan_region[3] * height,
        )
        selection = select_face(detections, bgr_image.shape, config=self.config, roi=scan_roi)
        if selection.status != "face_selected" or selection.selected is None:
            tracking_bbox = self._tracking_bbox_after_loss()
            return FaceAnalysisResult(
                selection.status, selection.face_count, detections, None,
                reason=selection.reason, model_name=self.model_name,
                model_version=self.model_version, tracking_bbox=tracking_bbox,
                tracking_id=self._tracking_id,
            )

        selected = selection.selected
        matched_face = min(
            faces,
            key=lambda face: sum(abs(float(a) - float(b)) for a, b in zip(face.bbox[:4], selected.bbox)),
        )
        vector, preprocessing = self._embedding(matched_face, bgr_image)
        if self._previous_embedding is not None and self._lost_frames <= self.max_lost_frames:
            similarity = float(np.dot(self._previous_embedding, vector))
            if similarity < self.track_similarity_floor:
                tracking_bbox = self._tracking_bbox_after_loss()
                return FaceAnalysisResult(
                    "ambiguous", len(faces), detections, None,
                    reason="tracked_identity_embedding_changed", model_name=self.model_name,
                    model_version=self.model_version, tracking_bbox=tracking_bbox,
                    tracking_id=self._tracking_id,
                )

        if self._previous_embedding is None or self._lost_frames > self.max_lost_frames:
            self._track_serial += 1
            self._tracking_id = self._track_serial
        if self._smoothed_bbox is None or self._lost_frames > self.max_lost_frames:
            smoothed = np.asarray(selected.bbox, dtype=np.float64)
        else:
            previous = np.asarray(self._smoothed_bbox, dtype=np.float64)
            current = np.asarray(selected.bbox, dtype=np.float64)
            smoothed = (self.smoothing * current) + ((1.0 - self.smoothing) * previous)
        self._previous_embedding = vector.copy()
        self._smoothed_bbox = tuple(float(value) for value in smoothed)
        self._lost_frames = 0
        return FaceAnalysisResult(
            status=selection.status, face_count=selection.face_count,
            detections=detections, selected=selected, embedding=vector,
            embedding_shape=tuple(vector.shape), reason=selection.reason,
            model_name=self.model_name, model_version=self.model_version,
            tracking_bbox=self._smoothed_bbox,
            landmarks=np.asarray(getattr(matched_face, "kps", None), dtype=np.float32).copy()
            if getattr(matched_face, "kps", None) is not None else None,
            tracking_id=self._tracking_id,
            preprocessing=preprocessing,
        )

    def _embedding(self, face, bgr_image):
        """Extract the embedding from the equalized frame, keeping detector geometry.

        Detection stays on the captured frame; only the recognition input is
        equalized, and the same landmarks are reused, so the alignment crop is
        pixel-aligned with the detection.
        """
        landmarks = getattr(face, "kps", None)
        if (self.preprocessing is None or self.preprocessing.equalization == "none"
                or self.recognition_model is None or landmarks is None):
            return embedding_from_face(face), "none"
        try:
            equalized = preprocess_face(bgr_image, config=self.preprocessing)
            if equalized.shape != bgr_image.shape or equalized.dtype != bgr_image.dtype:
                raise ValueError("preprocessing changed the frame geometry")
            self.recognition_model.get(equalized, face)
        except Exception:
            # Fall back to the detector's own embedding rather than losing the
            # frame; `preprocessing` reports which input the vector came from.
            return embedding_from_face(face), f"{self.preprocessing.equalization}_unavailable"
        return embedding_from_face(face), self.preprocessing.equalization
