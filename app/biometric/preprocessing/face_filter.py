"""Model-independent validation and largest-bounding-box selection (T2)."""
from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class FaceDetection:
    bbox: tuple[float, float, float, float]
    confidence: float
    quality: Optional[float] = None
    track_id: Optional[str] = None

    @property
    def width(self): return max(0.0, self.bbox[2] - self.bbox[0])
    @property
    def height(self): return max(0.0, self.bbox[3] - self.bbox[1])
    @property
    def area(self): return self.width * self.height


@dataclass(frozen=True)
class FaceFilterConfig:
    min_width: int = 64
    min_height: int = 64
    min_confidence: float = 0.5
    min_quality: Optional[float] = None
    max_area_fraction: float = 0.55


@dataclass(frozen=True)
class FaceSelectionResult:
    status: str
    selected: Optional[FaceDetection]
    face_count: int
    candidates: tuple[FaceDetection, ...]
    reason: str


def _clip_box(detection: FaceDetection, width: int, height: int) -> FaceDetection:
    x1, y1, x2, y2 = detection.bbox
    return FaceDetection((max(0.0, min(width, x1)), max(0.0, min(height, y1)),
                          max(0.0, min(width, x2)), max(0.0, min(height, y2))),
                         detection.confidence, detection.quality, detection.track_id)


def _inside_roi(box: FaceDetection, roi: Optional[Sequence[float]]) -> bool:
    if roi is None:
        return True
    x1, y1, x2, y2 = roi
    return x1 <= box.bbox[0] and box.bbox[2] <= x2 and y1 <= box.bbox[1] and box.bbox[3] <= y2


def select_face(detections: Iterable[FaceDetection], frame_shape, *,
                config: FaceFilterConfig = FaceFilterConfig(),
                roi: Optional[Sequence[float]] = None) -> FaceSelectionResult:
    """Max Area Filter: the validated detection with the largest width x height.

    Detections that are not finite, reach outside the frame or the scan ROI, are
    too small, fill too much of the frame, or fall below the confidence/quality
    floors are discarded first; remaining background faces simply lose on area.
    Exact area ties are broken by confidence and then position, so one frame
    always yields the same face.
    """
    height, width = int(frame_shape[0]), int(frame_shape[1])
    raw = tuple(detections)
    if not raw:
        return FaceSelectionResult("no_face", None, 0, (), "detector_returned_no_faces")

    candidates = []
    for detection in raw:
        if (not all(isfinite(float(value)) for value in detection.bbox)
                or not isfinite(float(detection.confidence))
                or (detection.quality is not None and not isfinite(float(detection.quality)))):
            continue
        x1, y1, x2, y2 = detection.bbox
        # Do not turn a partially out-of-frame detection into an eligible crop.
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            continue
        box = _clip_box(detection, width, height)
        area_fraction = box.area / max(1, width * height)
        if (box.width < config.min_width or box.height < config.min_height
                or box.confidence < config.min_confidence
                or (config.min_quality is not None and (box.quality is None or box.quality < config.min_quality))
                or area_fraction > config.max_area_fraction
                or not _inside_roi(box, roi)):
            continue
        candidates.append(box)

    if not candidates:
        return FaceSelectionResult("ambiguous", None, len(raw), (),
                                   "all_detections_failed_frame_scan_size_confidence_or_area_filters")

    candidates.sort(key=_selection_key, reverse=True)
    reason = "single_plausible_face" if len(candidates) == 1 else "largest_bounding_box_area"
    return FaceSelectionResult("face_selected", candidates[0], len(raw), tuple(candidates), reason)


def _selection_key(face: FaceDetection):
    return (face.area, face.confidence, -face.bbox[0], -face.bbox[1])
