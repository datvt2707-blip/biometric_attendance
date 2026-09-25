"""Unit tests for MediaPipe metric handling and the T6 challenge state machine."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.biometric.liveness import active_liveness
from app.biometric.liveness.active_liveness import (
    ActiveLivenessChallenge, MediaPipeFaceLandmarker, MediaPipeUnavailableError,
    landmarks_for_selected_face,
)


def mesh(ear="open", yaw=0.0):
    points = np.zeros((478, 3), dtype=np.float64)
    points[:, 0] = 0.5
    points[:, 1] = 0.5
    # Keep the eye-corner distance at 0.2 and vary only eyelid separation.
    vertical = {"open": 0.04, "closed": 0.004, "mid": 0.025}[ear]
    for left, ids in ((0.35, (33, 160, 158, 133, 153, 144)),
                      (0.55, (362, 385, 387, 263, 373, 380))):
        a, b, c, d, e, f = ids
        points[a] = (left, 0.40, 0)
        points[b] = (left + 0.02, 0.40 - vertical / 2, 0)
        points[c] = (left + 0.08, 0.40 - vertical / 2, 0)
        points[d] = (left + 0.10, 0.40, 0)
        points[e] = (left + 0.08, 0.40 + vertical / 2, 0)
        points[f] = (left + 0.02, 0.40 + vertical / 2, 0)
    points[33, 0], points[263, 0] = 0.35, 0.65
    points[1, 0] = 0.50 + yaw
    return points


class ActiveLivenessTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.config = {
            "blink_closed_ear_max": 0.2, "blink_open_ear_min": 0.24,
            "blink_closed_frames": 2, "blink_open_frames": 2,
            "neutral_frames": 5, "turn_threshold": 0.12,
            "turn_frames": 3, "timeout_seconds": 15,
            "proof_seconds": 5, "max_observation_gap": 2,
        }
        self.challenge = ActiveLivenessChallenge(self.config, clock=lambda: self.now)
        self.match = {"status": "matched", "person_id": 42, "person_type": "employee"}
        self.sequence = 0
        self.challenge.start(self.match, track_id=7, frame_sequence=self.sequence)

    def see(self, *, eye="open", yaw=0, track=7, match=None, status="face_selected", count=1):
        self.sequence += 1
        self.now += 0.1
        return self.challenge.observe(
            match=self.match if match is None else match, face_status=status,
            face_count=count, track_id=track, landmarks=mesh(eye, yaw),
            frame_sequence=self.sequence,
        )

    def test_challenge_requires_open_closed_open_then_left_then_right(self):
        for _ in range(5): self.see(eye="open")
        for _ in range(2): self.see(eye="closed")
        self.assertIn("mắt", self.challenge.state.prompt)
        for _ in range(2): self.see(eye="open")
        self.assertIn("trái", self.challenge.state.prompt)
        for _ in range(3): self.see(yaw=0.05)
        self.assertIn("phải", self.challenge.state.prompt)
        for _ in range(3): self.see(yaw=-0.05)
        self.assertTrue(self.challenge.state.passed)
        self.assertTrue(self.challenge.can_consume(self.match, track_id=7))
        self.assertTrue(self.challenge.consume(self.match, track_id=7))
        self.assertFalse(self.challenge.can_consume(self.match, track_id=7))

    def test_same_direction_twice_cannot_substitute_for_left_then_right(self):
        for _ in range(5): self.see()
        for _ in range(2): self.see(eye="closed")
        for _ in range(2): self.see()
        for _ in range(4): self.see(yaw=0.05)
        self.assertIn("phải", self.challenge.state.prompt)
        for _ in range(5): self.see(yaw=0.05)
        self.assertFalse(self.challenge.state.passed)

    def test_track_change_multiple_faces_and_invalid_landmarks_fail_closed(self):
        self.see(track=8)
        self.assertEqual(self.challenge.state.status, "failed")
        self.challenge.start(self.match, track_id=7, frame_sequence=self.sequence)
        self.see(status="ambiguous", count=2)
        self.assertEqual(self.challenge.state.status, "failed")
        self.challenge.start(self.match, track_id=7, frame_sequence=self.sequence)
        self.sequence += 1
        self.challenge.observe(match=self.match, face_status="face_selected", face_count=1,
            track_id=7, landmarks=None, frame_sequence=self.sequence)
        self.assertEqual(self.challenge.state.status, "failed")

    def test_duplicate_frame_is_ignored_and_old_gap_invalidates(self):
        self.sequence += 1
        self.challenge.observe(match=self.match, face_status="face_selected", face_count=1,
            track_id=7, landmarks=mesh(), frame_sequence=self.sequence)
        state = self.challenge.state
        self.challenge.observe(match=self.match, face_status="face_selected", face_count=1,
            track_id=7, landmarks=mesh("closed"), frame_sequence=self.sequence)
        self.assertEqual(self.challenge.state, state)
        self.now += 3
        self.sequence += 1
        self.challenge.observe(match=self.match, face_status="face_selected", face_count=1,
            track_id=7, landmarks=mesh(), frame_sequence=self.sequence)
        self.assertEqual(self.challenge.state.status, "failed")

    def test_incorrect_threshold_geometry_is_rejected(self):
        with self.assertRaises(ValueError):
            ActiveLivenessChallenge({"blink_closed_ear_max": 0.3, "blink_open_ear_min": 0.2})

    def test_missing_model_asset_is_reported_without_fabricating_landmarks(self):
        absent = Path(tempfile.gettempdir()) / "no-such-face_landmarker.task"
        with patch.dict(os.environ, {"MEDIAPIPE_FACE_LANDMARKER_MODEL": ""}), \
                patch.object(active_liveness, "DEFAULT_FACE_LANDMARKER_PATH", absent):
            with self.assertRaises(MediaPipeUnavailableError) as unconfigured:
                MediaPipeFaceLandmarker()
            self.assertIn("MEDIAPIPE_FACE_LANDMARKER_MODEL", str(unconfigured.exception))
            with self.assertRaises(MediaPipeUnavailableError) as missing:
                MediaPipeFaceLandmarker(str(absent))
            self.assertIn(absent.name, str(missing.exception))

    def test_a_corrupt_asset_raises_instead_of_returning_fake_landmarks(self):
        with tempfile.NamedTemporaryFile(suffix=".task", delete=False) as handle:
            handle.write(b"not a real tflite bundle")
            broken = handle.name
        self.addCleanup(os.unlink, broken)
        with self.assertRaises(MediaPipeUnavailableError):
            MediaPipeFaceLandmarker(broken)

    def test_the_configured_default_asset_path_is_used_when_the_env_var_is_unset(self):
        with tempfile.NamedTemporaryFile(suffix=".task", delete=False) as handle:
            handle.write(b"placeholder")
            placeholder = Path(handle.name)
        self.addCleanup(os.unlink, str(placeholder))
        with patch.dict(os.environ, {"MEDIAPIPE_FACE_LANDMARKER_MODEL": ""}), \
                patch.object(active_liveness, "DEFAULT_FACE_LANDMARKER_PATH", placeholder):
            # The asset is a placeholder, so loading fails — but the error proves
            # the default location was used instead of "not configured".
            with self.assertRaises(MediaPipeUnavailableError) as failure:
                MediaPipeFaceLandmarker()
        self.assertIn("FaceLandmarker", str(failure.exception))
        self.assertNotIn("MEDIAPIPE_FACE_LANDMARKER_MODEL", str(failure.exception))

    def test_bystanders_do_not_invalidate_a_bound_challenge(self):
        for _ in range(5): self.see(count=3)
        for _ in range(2): self.see(eye="closed", count=3)
        for _ in range(2): self.see(eye="open", count=4)
        for _ in range(3): self.see(yaw=0.05, count=2)
        for _ in range(3): self.see(yaw=-0.05, count=2)
        self.assertTrue(self.challenge.state.passed)
        self.assertTrue(self.challenge.can_consume(self.match, track_id=7))

    def test_identity_track_and_face_status_still_fail_closed_with_bystanders(self):
        self.see(count=3, track=8)
        self.assertEqual(self.challenge.state.status, "failed")
        self.challenge.start(self.match, track_id=7, frame_sequence=self.sequence)
        self.see(count=3, match={"status": "matched", "person_id": 99, "person_type": "employee"})
        self.assertEqual(self.challenge.state.status, "failed")
        self.challenge.start(self.match, track_id=7, frame_sequence=self.sequence)
        self.see(count=3, status="ambiguous")
        self.assertEqual(self.challenge.state.status, "failed")


class LandmarkPairingTests(unittest.TestCase):
    """The mesh handed to the challenge must belong to the Max-Area face."""

    @staticmethod
    def placed(points, box, shape=(480, 640)):
        """Rescale a normalized mesh so that it spans `box` in pixel space."""
        x1, y1, x2, y2 = box
        height, width = shape
        moved = np.asarray(points, dtype=np.float64).copy()
        xs, ys = moved[:, 0], moved[:, 1]
        xs[:] = (xs - xs.min()) / max(1e-9, xs.max() - xs.min())
        ys[:] = (ys - ys.min()) / max(1e-9, ys.max() - ys.min())
        moved[:, 0] = (x1 + xs * (x2 - x1)) / width
        moved[:, 1] = (y1 + ys * (y2 - y1)) / height
        return moved

    def test_mesh_of_the_selected_face_is_chosen_over_a_bystander_mesh(self):
        target_box = (100.0, 100.0, 260.0, 260.0)
        target = self.placed(mesh(yaw=0.01), target_box)
        bystander = self.placed(mesh(yaw=-0.01), (400.0, 120.0, 480.0, 200.0))
        for faces in ((target, bystander), (bystander, target)):
            chosen = landmarks_for_selected_face(faces, target_box, (480, 640))
            self.assertIsNotNone(chosen)
            np.testing.assert_allclose(chosen, target)

    def test_no_overlapping_mesh_or_missing_input_returns_nothing(self):
        bystander = self.placed(mesh(), (400.0, 120.0, 480.0, 200.0))
        self.assertIsNone(landmarks_for_selected_face((bystander,), (100, 100, 260, 260), (480, 640)))
        self.assertIsNone(landmarks_for_selected_face((), (100, 100, 260, 260), (480, 640)))
        self.assertIsNone(landmarks_for_selected_face((bystander,), None, (480, 640)))
        self.assertIsNone(landmarks_for_selected_face((np.zeros((10, 3)),), (100, 100, 260, 260), (480, 640)))


class WorkerLandmarkWiringTests(unittest.TestCase):
    """The worker must hand the challenge the mesh of the selected face."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def worker(self, faces):
        from app.biometric.face_recognition.detector import FaceAnalysisWorker
        worker = FaceAnalysisWorker()
        worker._liveness_landmarker = SimpleNamespace(detect=lambda _frame: faces)
        return worker

    @staticmethod
    def result(bbox=(100.0, 100.0, 260.0, 260.0), status="face_selected"):
        from app.biometric.face_recognition.face_recognizer import FaceAnalysisResult
        from app.biometric.preprocessing.face_filter import FaceDetection
        selected = FaceDetection(bbox, 0.99) if bbox is not None else None
        return FaceAnalysisResult(status=status, face_count=2, detections=(), selected=selected)

    def test_selected_face_mesh_is_attached_even_with_a_bystander_mesh(self):
        target_box = (100.0, 100.0, 260.0, 260.0)
        target = LandmarkPairingTests.placed(mesh(), target_box)
        bystander = LandmarkPairingTests.placed(mesh(), (400.0, 120.0, 480.0, 200.0))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        attached = self.worker((bystander, target))._attach_landmarks(self.result(target_box), frame)
        np.testing.assert_allclose(attached.mediapipe_landmarks, target)
        self.assertEqual(attached.liveness_error, "")

    def test_unmatched_or_failing_landmarks_report_an_error_instead_of_a_stranger(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bystander = LandmarkPairingTests.placed(mesh(), (400.0, 120.0, 480.0, 200.0))
        unmatched = self.worker((bystander,))._attach_landmarks(self.result(), frame)
        self.assertIsNone(unmatched.mediapipe_landmarks)
        self.assertTrue(unmatched.liveness_error)

        def explode(_frame):
            raise RuntimeError("inference down")
        broken = self.worker(())
        broken._liveness_landmarker = SimpleNamespace(detect=explode)
        failed = broken._attach_landmarks(self.result(), frame)
        self.assertIsNone(failed.mediapipe_landmarks)
        self.assertIn("inference down", failed.liveness_error)


class AttendanceGateWithBystandersTests(unittest.TestCase):
    """The check-in button must survive a bystander but not a missing target."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def view(self):
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import QWidget
        from app.ui.common import views as ui_views

        class PreviewController(QObject):
            face_analysis_ready = Signal(object, object)
            face_analysis_error = Signal(str)
            def __init__(self, *_args, **_kwargs): super().__init__()

        class HistoryService:
            def list_history(self, kind, **kwargs): return []
            def count_history(self, kind, **kwargs): return 0

        with patch.object(ui_views, "CameraPreviewController", PreviewController), \
             patch.object(ui_views, "user_chip", return_value=QWidget()), \
             patch("app.services.attendance_service.AttendanceService", return_value=HistoryService()):
            return ui_views.AttendanceView("staff", "attendance")

    @staticmethod
    def analysis(*, status="face_selected", face_count=3, landmarks=None, selected=True):
        return SimpleNamespace(
            status=status, face_count=face_count,
            selected=SimpleNamespace(bbox=(100.0, 100.0, 260.0, 260.0)) if selected else None,
            embedding=np.asarray([1.0, 0.0, 0.0], dtype=np.float32) if selected else None,
            mediapipe_landmarks=landmarks, tracking_id=7, frame_sequence=99,
        )

    def test_check_in_is_available_with_a_smaller_background_face(self):
        view = self.view()
        view._development_t6_mode = False
        match = SimpleNamespace(status="matched", person_id=42, person_type="employee",
                                display_name="Person", person_code="E-1", similarity=0.9)
        challenge, sequence = view._liveness_challenge, 0
        challenge.start(match, track_id=7, frame_sequence=sequence)
        script = ([("open", 0)] * 5 + [("closed", 0)] * 2 + [("open", 0)] * 2
                  + [("open", 0.05)] * 3 + [("open", -0.05)] * 3)
        for eye, yaw in script:
            sequence += 1
            challenge.observe(match=match, face_status="face_selected", face_count=3,
                              track_id=7, landmarks=mesh(eye, yaw), frame_sequence=sequence)
        self.assertTrue(challenge.state.passed)
        view._last_analysis = self.analysis(landmarks=mesh())
        view._last_analysis_at = time.monotonic()
        view._set_attendance_match(match)
        self.assertTrue(any(button.isEnabled() for _action, button in view._attendance_buttons))
        view.close()

    def test_no_valid_target_face_keeps_check_in_disabled(self):
        view = self.view()
        view._development_t6_mode = False
        match = SimpleNamespace(status="matched", person_id=42, person_type="employee",
                                display_name="Person", person_code="E-1", similarity=0.9)
        for result in (self.analysis(status="ambiguous", selected=False),
                       self.analysis(status="no_face", face_count=0, selected=False),
                       self.analysis(landmarks=None)):
            view._last_analysis = result
            view._last_analysis_at = time.monotonic()
            view._set_attendance_match(match)
            self.assertFalse(any(button.isEnabled() for _action, button in view._attendance_buttons))
        view.close()


class LivenessThresholdReloadTests(unittest.TestCase):
    """Edited T6 thresholds reach the running detector worker without a restart."""

    def worker(self):
        from app.biometric.face_recognition.detector import FaceAnalysisWorker
        worker = FaceAnalysisWorker.__new__(FaceAnalysisWorker)
        worker._liveness_config = {"turn_frames": 2}
        worker._liveness_generation = 0
        worker._liveness_error = ""
        return worker

    def test_worker_reloads_only_when_the_generation_changes(self):
        from app.services import settings_service as module
        worker = self.worker()
        loads = []

        class Service:
            def load_liveness_config(self):
                loads.append(1)
                return {"turn_frames": 9}

        with patch.object(module, "SettingsService", Service), \
             patch.object(module, "liveness_config_generation", lambda: 0):
            worker._reload_liveness_config()
        self.assertEqual((loads, worker._liveness_config), ([], {"turn_frames": 2}))
        with patch.object(module, "SettingsService", Service), \
             patch.object(module, "liveness_config_generation", lambda: 4):
            worker._reload_liveness_config()
            worker._reload_liveness_config()
        self.assertEqual((len(loads), worker._liveness_config, worker._liveness_generation),
                         (1, {"turn_frames": 9}, 4))
        self.assertEqual(worker._liveness_error, "")

    def test_a_failing_reload_keeps_the_previous_thresholds_and_reports_the_error(self):
        from app.services import settings_service as module
        worker = self.worker()

        class Broken:
            def load_liveness_config(self):
                raise RuntimeError("database locked")

        with patch.object(module, "SettingsService", Broken), \
             patch.object(module, "liveness_config_generation", lambda: 3):
            worker._reload_liveness_config()
        self.assertEqual(worker._liveness_config, {"turn_frames": 2})
        self.assertIn("database locked", worker._liveness_error)

    def test_an_unstarted_worker_does_not_touch_the_database(self):
        worker = self.worker()
        worker._liveness_generation = None
        from app.services import settings_service as module
        with patch.object(module, "liveness_config_generation", side_effect=AssertionError("queried")):
            worker._reload_liveness_config()


if __name__ == "__main__":
    unittest.main()
