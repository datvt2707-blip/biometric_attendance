"""MediaPipe Tasks face landmarks and identity-bound blink/turn verification."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import time
import uuid

import numpy as np


DEFAULT_LIVENESS_CONFIG = {
    "blink_closed_ear_max": 0.20,
    "blink_open_ear_min": 0.24,
    "blink_closed_frames": 2,
    "blink_open_frames": 2,
    "neutral_frames": 5,
    "turn_threshold": 0.12,
    "turn_frames": 3,
    "timeout_seconds": 15.0,
    "proof_seconds": 5.0,
    "max_observation_gap": 1.5,
}


class MediaPipeUnavailableError(RuntimeError):
    pass


# Official Google asset; keep it out of Git and out of the repository history.
DEFAULT_FACE_LANDMARKER_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "models" / "face_landmarker.task"
)


def _intersection_over_union(first, second):
    ax1, ay1, ax2, ay2 = (float(value) for value in first)
    bx1, by1, bx2, by2 = (float(value) for value in second)
    width = min(ax2, bx2) - max(ax1, bx1)
    height = min(ay2, by2) - max(ay1, by1)
    if width <= 0 or height <= 0:
        return 0.0
    overlap = width * height
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - overlap
    return overlap / union if union > 0 else 0.0


def landmarks_for_selected_face(faces, bbox, frame_shape, *, min_overlap=0.30):
    """Return the mesh belonging to the face the Max Area Filter selected.

    Bystanders keep producing their own meshes, so liveness follows the one
    face T2 chose instead of refusing every frame that contains more than one.
    Returns None when no mesh overlaps the selected box well enough, which
    keeps the challenge fail-closed rather than binding it to a stranger.
    """
    if bbox is None or not faces:
        return None
    try:
        target = tuple(float(value) for value in tuple(bbox)[:4])
        height, width = float(frame_shape[0]), float(frame_shape[1])
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if len(target) != 4 or width <= 0 or height <= 0 or not all(math.isfinite(v) for v in target):
        return None
    best, best_overlap = None, 0.0
    for points in faces:
        mesh = np.asarray(points, dtype=np.float64)
        if mesh.shape != (478, 3) or not np.all(np.isfinite(mesh)):
            continue
        xs, ys = mesh[:, 0] * width, mesh[:, 1] * height
        overlap = _intersection_over_union(
            (xs.min(), ys.min(), xs.max(), ys.max()), target,
        )
        if overlap > best_overlap:
            best, best_overlap = mesh, overlap
    return best if best_overlap >= float(min_overlap) else None


class MediaPipeFaceLandmarker:
    """One MediaPipe Tasks FaceLandmarker instance, called by a background worker."""

    def __init__(self, model_path=None, *, max_faces=5):
        configured = model_path or os.environ.get("MEDIAPIPE_FACE_LANDMARKER_MODEL")
        if not configured and DEFAULT_FACE_LANDMARKER_PATH.is_file():
            configured = str(DEFAULT_FACE_LANDMARKER_PATH)
        if not configured:
            raise MediaPipeUnavailableError(
                "Chưa cấu hình tệp FaceLandmarker .task; đặt MEDIAPIPE_FACE_LANDMARKER_MODEL "
                f"hoặc đặt tệp tại {DEFAULT_FACE_LANDMARKER_PATH}."
            )
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise MediaPipeUnavailableError(f"Không tìm thấy mô hình MediaPipe: {path}")
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions
            vision = mp.tasks.vision
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(path)),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=max(1, int(max_faces)),
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._mp = mp
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
            self.model_path = str(path)
        except Exception as exc:
            raise MediaPipeUnavailableError(f"Không khởi tạo được FaceLandmarker: {exc}") from exc

    def detect(self, bgr_frame):
        import cv2
        if not isinstance(bgr_frame, np.ndarray) or bgr_frame.size == 0:
            raise ValueError("Cần khung hình BGR hợp lệ.")
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect(image)
        faces = []
        for face in result.face_landmarks:
            points = np.asarray([(point.x, point.y, point.z) for point in face], dtype=np.float64)
            if points.shape == (478, 3) and np.all(np.isfinite(points)):
                faces.append(points)
        return tuple(faces)

    def close(self):
        landmarker, self._landmarker = getattr(self, "_landmarker", None), None
        if landmarker is not None:
            landmarker.close()


@dataclass(frozen=True)
class ChallengeState:
    status: str
    prompt: str
    challenge_id: str | None = None
    reason: str = ""

    @property
    def passed(self):
        return self.status == "passed"


class ActiveLivenessChallenge:
    """Require stable open→closed→open blink, then anatomical left and right turns.

    Input is the unmirrored, normalized 478-point MediaPipe face mesh. The
    signed yaw proxy is nose-x minus eye-center-x divided by eye distance.
    In unmirrored camera coordinates, the subject's anatomical left is positive
    image-x and the subject's right is negative image-x. UI mirroring is preview-only.
    """

    MAX_OBSERVATION_GAP = DEFAULT_LIVENESS_CONFIG["max_observation_gap"]

    def __init__(self, config=None, *, clock=time.monotonic):
        self._clock = clock
        self.configure(config or DEFAULT_LIVENESS_CONFIG)
        self._reset()

    def configure(self, config):
        merged = dict(DEFAULT_LIVENESS_CONFIG)
        if config:
            merged.update(config)
        numeric = ("blink_closed_ear_max", "blink_open_ear_min", "turn_threshold",
                   "timeout_seconds", "proof_seconds", "max_observation_gap")
        integer = ("blink_closed_frames", "blink_open_frames", "neutral_frames", "turn_frames")
        try:
            for key in numeric:
                merged[key] = float(merged[key])
                if not math.isfinite(merged[key]) or merged[key] <= 0:
                    raise ValueError
            for key in integer:
                merged[key] = int(merged[key])
                if merged[key] < 1:
                    raise ValueError
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Cấu hình ngưỡng liveness không hợp lệ.") from exc
        if merged["blink_closed_ear_max"] >= merged["blink_open_ear_min"]:
            raise ValueError("Ngưỡng mắt nhắm phải nhỏ hơn ngưỡng mắt mở.")
        if merged["turn_threshold"] > 1:
            raise ValueError("Ngưỡng quay đầu vượt miền tỷ lệ chuẩn hóa.")
        self.config = merged

    def _reset(self):
        self._status = "idle"
        self._prompt = "Chưa bắt đầu xác minh liveness MediaPipe."
        self._challenge_id = None
        self._person_id = self._person_type = self._track_id = None
        self._started = self._expires = self._passed_at = self._last_observed = None
        self._last_sequence = -1
        self._phase = "blink"
        self._open_count = self._closed_count = self._reopen_count = 0
        self._saw_open = self._saw_closed = False
        self._neutral = []
        self._baseline = None
        self._turn_count = 0

    @property
    def state(self):
        return ChallengeState(self._status, self._prompt, self._challenge_id)

    def start(self, match, *, track_id, frame_sequence, now=None):
        if not self._valid_identity(match) or track_id is None:
            self.cancel("Cần nhận diện đúng người trước khi xác minh liveness.")
            return self.state
        self._reset()
        instant = self._clock() if now is None else float(now)
        self._status = "active"
        self._prompt = "Nhìn thẳng, sau đó chớp mắt tự nhiên."
        self._challenge_id = uuid.uuid4().hex
        self._person_id = self._value(match, "person_id")
        self._person_type = self._value(match, "person_type")
        self._track_id = track_id
        self._started = instant
        self._expires = instant + self.config["timeout_seconds"]
        self._last_sequence = int(frame_sequence)
        return self.state

    def cancel(self, reason="Đã hủy thử thách."):
        self._status, self._prompt, self._passed_at = "cancelled", str(reason), None
        return self.state

    def invalidate(self, reason="Khuôn mặt hoặc camera bị gián đoạn; cần bắt đầu lại."):
        if self._status not in ("idle", "cancelled", "failed", "consumed", "expired"):
            self._status, self._prompt, self._passed_at = "failed", str(reason), None
        return self.state

    def observe(self, *, match, face_status, face_count, track_id, landmarks,
                frame_sequence, now=None):
        if self._status in ("idle", "cancelled", "failed", "consumed", "expired"):
            return self.state
        instant = self._clock() if now is None else float(now)
        if instant > self._expires:
            return self.invalidate("Hết thời gian xác minh; hãy bắt đầu lại.")
        # face_count intentionally unconstrained: T2 already reduced the frame to
        # one selected face, and the landmarks handed in belong to that face.
        if (face_status != "face_selected" or track_id != self._track_id
                or not self._same_identity(match)):
            return self.invalidate("Danh tính hoặc khuôn mặt đã thay đổi; thử thách bị hủy.")
        sequence = int(frame_sequence)
        if sequence <= self._last_sequence:
            return self.state
        if self._last_observed is not None and instant - self._last_observed > self.config["max_observation_gap"]:
            return self.invalidate("Khung hình bị gián đoạn hoặc quá cũ; hãy bắt đầu lại.")
        self._last_sequence, self._last_observed = sequence, instant
        points = self._valid_points(landmarks)
        if points is None:
            return self.invalidate("Không đọc được đủ landmark MediaPipe hợp lệ.")
        ear, yaw = self._measure(points)
        if ear is None or yaw is None:
            return self.invalidate("Hình học mắt/khuôn mặt không hợp lệ; hãy bắt đầu lại.")
        if self._status == "passed":
            return self.state

        if len(self._neutral) < self.config["neutral_frames"]:
            self._neutral.append(yaw)
            if len(self._neutral) == self.config["neutral_frames"]:
                self._baseline = float(np.median(self._neutral))

        if self._phase == "blink":
            self._observe_blink(ear)
        elif self._phase == "left":
            self._observe_turn(yaw, direction=1, next_phase="right")
        elif self._phase == "right":
            self._observe_turn(yaw, direction=-1, next_phase="done")
        if self._phase == "done":
            self._status, self._passed_at = "passed", instant
            self._prompt = "Đã hoàn tất chớp mắt → quay trái → quay phải."
        return self.state

    def _observe_blink(self, ear):
        cfg = self.config
        if ear >= cfg["blink_open_ear_min"]:
            self._open_count += 1
            self._closed_count = 0
            if self._open_count >= cfg["blink_open_frames"]:
                self._saw_open = True
            if self._saw_closed and self._open_count >= cfg["blink_open_frames"]:
                self._phase = "left"
                self._prompt = "Đã nhận chớp mắt. Quay nhẹ sang trái của bạn."
        elif ear <= cfg["blink_closed_ear_max"]:
            self._closed_count += 1
            self._open_count = 0
            if self._saw_open and self._closed_count >= cfg["blink_closed_frames"]:
                self._saw_closed = True
                self._prompt = "Đã nhận mắt nhắm; hãy mở mắt."
        else:
            self._open_count = self._closed_count = 0

    def _observe_turn(self, yaw, *, direction, next_phase):
        if self._baseline is None:
            self._prompt = "Giữ đầu nhìn thẳng để lấy mốc trung tính."
            self._turn_count = 0
            return
        delta = (yaw - self._baseline) * direction
        if delta >= self.config["turn_threshold"]:
            self._turn_count += 1
            if self._turn_count >= self.config["turn_frames"]:
                self._phase, self._turn_count = next_phase, 0
                if next_phase == "right":
                    self._prompt = "Đã nhận quay trái. Quay nhẹ sang phải của bạn."
                else:
                    self._prompt = "Đã nhận quay phải; xác minh gần hoàn tất."
        else:
            self._turn_count = 0

    def can_consume(self, match, *, track_id, now=None):
        instant = self._clock() if now is None else float(now)
        return (self._status == "passed" and self._passed_at is not None
                and instant <= self._passed_at + self.config["proof_seconds"]
                and self._last_observed is not None
                and instant - self._last_observed <= self.config["max_observation_gap"]
                and track_id == self._track_id and self._same_identity(match))

    def consume(self, match, *, track_id, now=None):
        if self.can_consume(match, track_id=track_id, now=now):
            self._status, self._prompt = "consumed", "Kết quả liveness đã được dùng một lần."
            return True
        if self._status == "passed":
            self.invalidate("Kết quả liveness hết hạn hoặc không còn khớp danh tính.")
        return False

    @staticmethod
    def _valid_points(value):
        try:
            points = np.asarray(value, dtype=np.float64)
        except (TypeError, ValueError, OverflowError):
            return None
        if points.shape != (478, 3) or not np.all(np.isfinite(points)):
            return None
        if np.any(points[:, :2] < -0.1) or np.any(points[:, :2] > 1.1):
            return None
        return points

    @staticmethod
    def _measure(points):
        # MediaPipe Face Mesh eye contours; normalized x/y coordinates.
        def ear(ids):
            a, b, c, d, e, f = (points[i, :2] for i in ids)
            horizontal = float(np.linalg.norm(a - d))
            if horizontal <= 1e-6:
                return None
            return (float(np.linalg.norm(b - f)) + float(np.linalg.norm(c - e))) / (2 * horizontal)
        left, right = ear((33, 160, 158, 133, 153, 144)), ear((362, 385, 387, 263, 373, 380))
        eye_distance = float(np.linalg.norm(points[33, :2] - points[263, :2]))
        if left is None or right is None or eye_distance <= 1e-6:
            return None, None
        eyes_mid_x = float((points[33, 0] + points[263, 0]) * 0.5)
        yaw = float((points[1, 0] - eyes_mid_x) / eye_distance)
        value = (left + right) * 0.5
        return (value, yaw) if math.isfinite(value) and math.isfinite(yaw) else (None, None)

    @staticmethod
    def _value(match, key, default=None):
        return match.get(key, default) if isinstance(match, dict) else getattr(match, key, default)

    @classmethod
    def _valid_identity(cls, match):
        return (cls._value(match, "status") == "matched"
                and isinstance(cls._value(match, "person_id"), int)
                and cls._value(match, "person_id") > 0
                and cls._value(match, "person_type") in ("employee", "student"))

    def _same_identity(self, match):
        return (self._valid_identity(match)
                and self._value(match, "person_id") == self._person_id
                and self._value(match, "person_type") == self._person_type)
