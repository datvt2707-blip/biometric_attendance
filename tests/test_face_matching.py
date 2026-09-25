"""Matching/tracking tests; synthetic detections and templates only."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt

from app.biometric.face_recognition.detector import FaceAnalysisWorker
from app.biometric.face_recognition.face_recognizer import FaceRecognizer
from app.biometric.preprocessing.face_filter import FaceDetection
from app.database.database import connect, initialize_database
from app.database.models.face import FaceEmbedding
from app.database.repositories.face_repository import FaceRepository
from app.database.repositories.user_repository import UserRepository
from app.services.enrollment_service import (
    EnrollmentCaptureSession,
    EnrollmentSample,
    EnrollmentService,
    EnrollmentValidationError,
)
from app.services.face_matching_service import FaceMatchingService
from auth_test_helpers import login_admin, logout
from app.ui.common.widgets import map_bbox_to_preview
from PySide6.QtCore import QRectF


class FaceMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "attendance.db"
        initialize_database(self.db)
        login_admin(self.db)
        self.service = EnrollmentService(self.db)
        self.matching = FaceMatchingService(self.db, threshold=0.60, ambiguity_margin=0.03)

    def tearDown(self):
        logout()
        self.temp.cleanup()

    @staticmethod
    def samples(vectors):
        result = []
        for index, vector in enumerate(vectors):
            varied = np.asarray(vector, dtype=np.float32).copy()
            axis = next((i for i, value in enumerate(varied) if abs(float(value)) < 0.5), (index + 1) % varied.size)
            varied[axis] += (index + 1) * 0.01
            result.append(EnrollmentSample(
                frame=np.full((120, 120, 3), index + 1, dtype=np.uint8),
                bbox=(10, 10, 110, 110), embedding=varied,
            ))
        return result

    def register(self, code, name, vectors):
        return self.service.enroll_employee(
            {"full_name": name, "gender": "unspecified"},
            {"employee_code": code, "department_name": None}, self.samples(vectors),
        )

    def test_genuine_embedding_matches_identity_and_checks_all_four_samples(self):
        self.register("E-1", "Person One", [[1,0,0], [.99,.1,0], [.9,.2,0], [.8,.3,0]])
        result = self.matching.match([.8, .3, 0], model_name="buffalo_l", model_version="w600k_r50.onnx")
        self.assertEqual(result.status, "matched")
        self.assertEqual((result.person_code, result.display_name), ("E-1", "Person One"))
        self.assertEqual(result.samples_compared, 4)
        self.assertGreaterEqual(result.similarity, .60)

    def test_similar_registered_person_is_not_arbitrarily_selected(self):
        self.register("E-1", "Person One", [[1,0,0]] * 4)
        self.register("E-2", "Person Two", [[0,1,0]] * 4)
        result = self.matching.match([0, 1, 0], model_name="buffalo_l", model_version="w600k_r50.onnx")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.person_code, "E-2")

    def test_unknown_invalid_and_corrupt_samples_are_safe(self):
        self.register("E-1", "Person One", [[1,0,0]] * 4)
        self.assertEqual(self.matching.match([-1,0,0], model_name="buffalo_l", model_version="w600k_r50.onnx").status, "no_match")
        for invalid in (None, [], [np.nan, 0], [0, 0, 0], [[1, 0, 0]]):
            self.assertEqual(self.matching.match(invalid).status, "invalid_embedding")

        connection = connect(self.db)
        try:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE face_embeddings SET vector_data=x'01' WHERE embedding_id=(SELECT min(embedding_id) FROM face_embeddings)")
            connection.commit()
        finally:
            connection.close()
        result = self.matching.match([1,0,0], model_name="buffalo_l", model_version="w600k_r50.onnx")
        self.assertIn(result.status, ("matched", "no_match"))
        self.assertEqual(result.samples_compared, 3)

    def test_missing_registered_samples_returns_explicit_no_match(self):
        result = self.matching.match([1, 0, 0], model_name="buffalo_l", model_version="w600k_r50.onnx")
        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.reason, "no_compatible_registered_samples")

    def test_ambiguous_candidates_and_no_attendance_writes(self):
        self.register("E-1", "Person One", [[1,0,0]] * 4)
        self.register("E-2", "Person Two", [[1,0,0]] * 4)
        connection = connect(self.db)
        before = tuple(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                       for table in ("employee_attendance", "student_attendance"))
        connection.close()
        result = self.matching.match([1,0,0], model_name="buffalo_l", model_version="w600k_r50.onnx")
        self.assertEqual(result.status, "ambiguous")
        connection = connect(self.db)
        after = tuple(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                       for table in ("employee_attendance", "student_attendance"))
        connection.close()
        self.assertEqual(after, before)


class TrackingTests(unittest.TestCase):
    @staticmethod
    def detected(bbox, embedding=(1.0, 0.0, 0.0)):
        return SimpleNamespace(bbox=np.asarray(bbox, dtype=np.float32), det_score=.99,
                               normed_embedding=np.asarray(embedding, dtype=np.float32))

    class Detector:
        name = "test-model"
        analysis = SimpleNamespace(models={})
        def __init__(self, faces): self.faces = iter(faces)
        def analyze(self, _frame): return next(self.faces)

    def frame(self): return np.zeros((400, 600, 3), dtype=np.uint8)

    def test_box_follows_moving_face_and_ema_reduces_jitter(self):
        xs = (100, 120, 120, 116)
        faces = [[self.detected((x,100,x+100,200))] for x in xs]
        recognizer = FaceRecognizer(self.Detector(faces), smoothing=.25)
        boxes = [recognizer.analyze(self.frame()).tracking_bbox for _ in xs]
        self.assertAlmostEqual(boxes[0][0], 100)
        self.assertGreater(boxes[1][0], boxes[0][0])
        self.assertLess(boxes[1][0], 120)
        raw_jitter = abs(xs[3] - xs[2])
        smooth_jitter = abs(boxes[3][0] - boxes[2][0])
        self.assertLess(smooth_jitter, raw_jitter)

    def test_does_not_switch_identity_when_another_face_enters(self):
        faces = [[self.detected((100,100,200,200), (1,0,0))],
                 [self.detected((101,100,201,200), (0,1,0))]]
        recognizer = FaceRecognizer(self.Detector(faces), track_similarity_floor=.8)
        self.assertEqual(recognizer.analyze(self.frame()).status, "face_selected")
        result = recognizer.analyze(self.frame())
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.embedding)

    def test_lost_track_clears_after_grace_and_a_new_face_starts_a_new_track(self):
        face = self.detected((100,100,200,200))
        other = self.detected((300,100,400,200))
        recognizer = FaceRecognizer(self.Detector([[face], [], [], [], [other]]), max_lost_frames=2)
        first = recognizer.analyze(self.frame())
        self.assertIsNotNone(first.tracking_bbox)
        self.assertEqual(recognizer.analyze(self.frame()).status, "no_face")
        self.assertIsNotNone(recognizer.analyze(self.frame()).tracking_bbox)
        self.assertIsNone(recognizer.analyze(self.frame()).tracking_bbox)
        fresh = recognizer.analyze(self.frame())
        self.assertEqual(fresh.status, "face_selected")
        self.assertEqual(fresh.tracking_bbox, tuple(float(v) for v in other.bbox))
        self.assertNotEqual(fresh.tracking_id, first.tracking_id)

    def test_scan_roi_requires_full_box_inside_frame_region(self):
        recognizer = FaceRecognizer(self.Detector([[self.detected((0,100,80,180))]]))
        result = recognizer.analyze(self.frame())
        self.assertNotEqual(result.status, "face_selected")
        self.assertIsNone(result.embedding)

    def test_preview_mapping_scales_and_mirrors_coordinates(self):
        rect = QRectF(10, 20, 300, 200)
        normal = map_bbox_to_preview((100, 50, 300, 150), (600, 400), rect)
        mirrored = map_bbox_to_preview((100, 50, 300, 150), (600, 400), rect, mirrored=True)
        self.assertEqual((normal.x(), normal.y(), normal.width(), normal.height()), (60, 45, 100, 50))
        self.assertEqual((mirrored.x(), mirrored.y(), mirrored.width(), mirrored.height()), (160, 45, 100, 50))

    def test_matching_runs_inside_the_background_qthread(self):
        caller_thread = threading.get_ident()
        worker_thread = {}
        complete = threading.Event()
        holder = {}

        class FakeFace:
            bbox = np.asarray([50, 50, 150, 150], dtype=np.float32)
            det_score = .99
            normed_embedding = np.asarray([1, .1, 0], dtype=np.float32)

        class FakeModelDetector:
            name = "test-model"
            analysis = SimpleNamespace(models={})
            def analyze(self, _frame): return [FakeFace()]

        class Matcher:
            def match(self, embedding, **_kwargs):
                worker_thread["match"] = threading.get_ident()
                return SimpleNamespace(status="matched", person_id=7)

        def on_result(_frame, result):
            holder["result"] = result
            worker_thread["signal"] = threading.get_ident()
            complete.set()

        worker = FaceAnalysisWorker(enable_matching=True, matching_service_factory=Matcher)
        worker.analysis_ready.connect(on_result, Qt.ConnectionType.DirectConnection)
        try:
            with patch("app.biometric.face_recognition.detector.InsightFaceDetector", return_value=FakeModelDetector()):
                worker.submit_frame(np.zeros((240, 240, 3), dtype=np.uint8))
                self.assertTrue(complete.wait(10))
        finally:
            if worker.isRunning():
                worker.stop_worker()
        self.assertEqual(holder["result"].match_result.status, "matched")
        self.assertNotEqual(worker_thread["match"], caller_thread)
        self.assertNotEqual(worker_thread["signal"], caller_thread)

    def test_largest_bounding_box_is_selected_and_background_faces_are_ignored(self):
        near = self.detected((100,100,260,260), (1,0,0))      # 160 x 160
        background = self.detected((300,100,400,200), (0,1,0))  # 100 x 100
        for order in ([near, background], [background, near]):
            result = FaceRecognizer(self.Detector([list(order)])).analyze(self.frame())
            self.assertEqual(result.status, "face_selected")
            self.assertEqual(result.reason, "largest_bounding_box_area")
            self.assertEqual(result.selected.bbox, tuple(float(v) for v in near.bbox))
            self.assertEqual(result.face_count, 2)
            np.testing.assert_allclose(result.embedding, [1, 0, 0], atol=1e-6)

    def test_equal_area_faces_resolve_to_the_same_face_every_frame(self):
        left = self.detected((100,100,200,200))
        right = self.detected((300,100,400,200))
        selected = set()
        for order in ([left, right], [right, left]):
            for _ in range(2):
                result = FaceRecognizer(self.Detector([list(order)])).analyze(self.frame())
                self.assertEqual(result.status, "face_selected")
                selected.add(result.selected.bbox)
        self.assertEqual(selected, {tuple(float(v) for v in left.bbox)})

    def test_empty_and_invalid_detections_never_produce_a_selection(self):
        invalid = [
            [],
            [self.detected((float("nan"), 100, 200, 200))],
            [self.detected((100, 100, 100, 200))],            # zero width
            [self.detected((-10, 100, 90, 200))],             # outside the frame
            [self.detected((0, 0, 600, 400))],                # fills the frame
        ]
        for faces in invalid:
            result = FaceRecognizer(self.Detector([faces])).analyze(self.frame())
            self.assertNotEqual(result.status, "face_selected")
            self.assertIsNone(result.selected)
            self.assertIsNone(result.embedding)
            self.assertIsNone(result.match_result)

    def test_only_the_selected_face_reaches_enrollment_and_attendance(self):
        near = self.detected((100,100,260,260))
        background = self.detected((300,100,400,200))
        result = FaceRecognizer(self.Detector([[near, background]])).analyze(self.frame())
        # The background face never produces a second candidate result...
        self.assertEqual(result.selected.bbox, tuple(float(v) for v in near.bbox))
        # ...and a frame that still contains a stranger cannot silently enroll:
        # both the capture session and the service require face_count == 1.
        session = EnrollmentCaptureSession()
        with self.assertRaises(EnrollmentValidationError):
            session.accept(self.frame(), result)
        self.assertEqual(session.samples, [])


if __name__ == "__main__":
    unittest.main()
