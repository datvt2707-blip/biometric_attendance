"""Enrollment workflow/service tests; camera/model outputs are deliberately mocked."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sqlite3
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QDialog

from app.database.database import connect, initialize_database
from app.database.models.class_model import Class
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.user_repository import UserRepository
from app.biometric.face_recognition.detector import FaceAnalysisWorker
from app.services.enrollment_service import (
    EnrollmentCaptureSession,
    EnrollmentConflictError,
    EnrollmentSample,
    EnrollmentService,
    EnrollmentValidationError,
)
from auth_test_helpers import login_admin, logout
from app.ui.common.dialogs import EnrollmentDialog


class EnrollmentCaptureSessionTests(unittest.TestCase):
    def setUp(self):
        self.session = EnrollmentCaptureSession()

    @staticmethod
    def result(frame_id=1, *, status="face_selected", face_count=1, embedding=None):
        frame = np.full((100, 100, 3), frame_id, dtype=np.uint8)
        return frame, SimpleNamespace(
            status=status,
            face_count=face_count,
            selected=SimpleNamespace(bbox=(10, 10, 90, 90)),
            embedding=np.asarray(embedding if embedding is not None else [1.0, float(frame_id), 0.25], dtype=np.float32),
        )

    def test_invalid_and_ambiguous_samples_do_not_increment_count(self):
        for status, face_count in (("no_face", 0), ("multiple_faces", 2), ("ambiguous", 2)):
            frame, result = self.result(status=status, face_count=face_count)
            with self.assertRaises(EnrollmentValidationError):
                self.session.accept(frame, result)
            self.assertEqual(len(self.session.samples), 0)

    def test_duplicate_frame_or_embedding_is_rejected(self):
        frame, result = self.result(1)
        self.session.accept(frame, result)
        with self.assertRaises(EnrollmentValidationError):
            self.session.accept(frame.copy(), result)
        frame2, repeated_embedding = self.result(2, embedding=result.embedding)
        with self.assertRaises(EnrollmentValidationError):
            self.session.accept(frame2, repeated_embedding)
        self.assertEqual(len(self.session.samples), 1)

    def test_malformed_embeddings_are_rejected(self):
        for vector in (np.array([np.nan], dtype=np.float32), np.zeros(3, dtype=np.float32), np.ones((2, 2), dtype=np.float32)):
            frame, result = self.result(1, embedding=vector)
            with self.assertRaises(EnrollmentValidationError):
                self.session.accept(frame, result)
            self.assertEqual(len(self.session.samples), 0)

    def test_embedding_dimensions_must_match(self):
        frame, result = self.result(1)
        self.session.accept(frame, result)
        frame2, result2 = self.result(2, embedding=[0.1, 0.2])
        with self.assertRaises(EnrollmentValidationError):
            self.session.accept(frame2, result2)
        self.assertEqual(len(self.session.samples), 1)

    def test_retake_releases_sample_for_recapture(self):
        frame, result = self.result(1)
        self.session.accept(frame, result)
        self.assertIsNotNone(self.session.retake_last())
        self.assertEqual(len(self.session.samples), 0)
        self.session.accept(frame, result)


class EnrollmentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "attendance.db"
        initialize_database(self.db_path)
        connection = connect(self.db_path)
        users = UserRepository(connection)
        users.create_department("Engineering")
        ClassRepository(connection).create_class(Class(class_id=None, class_name="10A", academic_year="2026-2027"))
        connection.execute("INSERT INTO roles(role_code, role_name) VALUES ('TEST_KEEP', 'Unrelated role')")
        connection.execute("INSERT INTO system_settings(scope, setting_key, setting_value) VALUES ('global', 'test_keep', 'unchanged')")
        connection.commit()
        connection.close()
        login_admin(self.db_path)
        self.service = EnrollmentService(self.db_path)

    def tearDown(self):
        logout()
        self.temp.cleanup()

    @staticmethod
    def samples():
        return [
            EnrollmentSample(
                frame=np.full((100, 100, 3), index + 1, dtype=np.uint8),
                bbox=(10, 10, 90, 90),
                embedding=np.eye(4, dtype=np.float32)[index],
            ) for index in range(4)
        ]

    @staticmethod
    def person():
        return {"full_name": "Test Person", "date_of_birth": "2000-01-02", "gender": "unspecified"}

    def counts(self):
        connection = connect(self.db_path)
        try:
            return tuple(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                         for table in ("people", "employees", "students", "face_images", "face_embeddings", "enrollments", "roles", "system_settings", "classes", "departments"))
        finally:
            connection.close()

    def test_employee_enrollment_saves_four_images_and_embeddings(self):
        result = self.service.enroll_employee(
            self.person(), {"employee_code": "EMP-T1", "department_name": "Engineering"}, self.samples()
        )
        connection = connect(self.db_path)
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM employees").fetchone()[0], 1)
            images = connection.execute("SELECT image_id, capture_label, image_path FROM face_images WHERE person_id=? ORDER BY image_id", (result["person_id"],)).fetchall()
            embeddings = connection.execute("SELECT image_id, dimension, dtype, length(vector_data) FROM face_embeddings WHERE person_id=?", (result["person_id"],)).fetchall()
            self.assertEqual([row["capture_label"] for row in images], ["front", "left", "right", "up"])
            self.assertEqual(len(embeddings), 4)
            self.assertTrue(all(row["dimension"] == 4 and row["dtype"] == "float32" and row["length(vector_data)"] == 16 for row in embeddings))
            self.assertEqual({row["image_id"] for row in embeddings}, {row["image_id"] for row in images})
            self.assertTrue(all((self.root / row["image_path"]).is_file() for row in images))
            self.assertEqual(connection.execute("SELECT role_name FROM roles WHERE role_code='TEST_KEEP'").fetchone()[0], "Unrelated role")
            self.assertEqual(connection.execute("SELECT setting_value FROM system_settings WHERE setting_key='test_keep'").fetchone()[0], "unchanged")
        finally:
            connection.close()

    def test_student_enrollment_saves_profile_class_and_four_samples(self):
        result = self.service.enroll_student(
            self.person(),
            {"student_code": "STU-T1", "class_name": "10A", "academic_year": "2026-2027", "guardian_name": "Guardian"},
            self.samples(),
        )
        connection = connect(self.db_path)
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM students WHERE student_id=?", (result["profile_id"],)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM enrollments WHERE student_id=?", (result["profile_id"],)).fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM face_embeddings WHERE person_id=?", (result["person_id"],)).fetchone()[0], 4)
        finally:
            connection.close()

    def test_missing_department_or_class_is_rejected_without_creating_records(self):
        fresh_db = self.root / "fresh" / "attendance.db"
        service = EnrollmentService(fresh_db)
        with self.assertRaises(EnrollmentConflictError):
            service.enroll_employee(
                self.person(), {"employee_code": "EMP-FRESH", "department_name": "Engineering"}, self.samples()
            )
        with self.assertRaises(EnrollmentConflictError):
            service.enroll_student(
                {"full_name": "Student Person", "gender": "unspecified"},
                {"student_code": "STU-FRESH", "class_name": "10A", "academic_year": "2026-2027"}, self.samples(),
            )
        connection = connect(fresh_db)
        try:
            self.assertEqual(connection.execute("SELECT count(*) FROM people").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM employees").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM students").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM face_embeddings").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM departments").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM classes").fetchone()[0], 0)
        finally:
            connection.close()
        self.assertEqual(list((self.root / "faces").glob("*.jpg")), [])

    def test_existing_employee_search_and_duplicate_retry_preserve_record(self):
        first = self.service.enroll_employee(
            {"full_name": "Nguy?n V?n ??t", "gender": "unspecified"},
            {"employee_code": "NV100", "department_name": "Engineering"}, self.samples()
        )
        connection = connect(self.db_path)
        try:
            rows, total = UserRepository(connection).search_employee_directory("NV100")
            self.assertEqual(total, 1)
            self.assertEqual(rows[0][0:2], ("NV100", "Nguy?n V?n ??t"))
            self.assertTrue(rows[0][4])
        finally:
            connection.close()
        before = self.counts()
        with self.assertRaises(EnrollmentConflictError):
            self.service.enroll_employee(
                {"full_name": "Nguy?n V?n ??t", "gender": "unspecified"},
                {"employee_code": "NV100", "department_name": "Engineering"}, self.samples()
            )
        self.assertEqual(self.counts(), before)
        self.assertEqual(first["profile_id"], 1)

    def test_duplicate_person_code_is_a_conflict_and_does_not_replace_records(self):
        args = (self.person(), {"employee_code": "EMP-DUP", "department_name": "Engineering"}, self.samples())
        self.service.enroll_employee(*args)
        before = self.counts()
        with self.assertRaises(EnrollmentConflictError):
            self.service.enroll_employee(*args)
        self.assertEqual(self.counts(), before)

    def test_persistence_failure_rolls_back_database_and_removes_written_images(self):
        connection = connect(self.db_path)
        connection.execute("CREATE TRIGGER fail_embedding BEFORE INSERT ON face_embeddings BEGIN SELECT RAISE(ABORT, 'forced failure'); END")
        connection.commit(); connection.close()
        before = self.counts()
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.enroll_employee(
                self.person(), {"employee_code": "EMP-ROLLBACK", "department_name": "Engineering"}, self.samples()
            )
        self.assertEqual(self.counts(), before)
        self.assertEqual(list((self.root / "faces").glob("*.jpg")), [])


class EnrollmentDialogCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication([])

    def test_save_error_keeps_dialog_open_and_success_closes_after_single_cleanup(self):
        class SignalStub:
            def connect(self, _slot): pass

        class ControllerStub:
            def __init__(self, *_args, **_kwargs):
                self.sample_analysis_ready = SignalStub()
                self.sample_analysis_error = SignalStub()
                self.face_analysis_error = SignalStub()
                self.shutdown_calls = 0
            def shutdown(self): self.shutdown_calls += 1

        class ServiceStub:
            fail = True
            def enroll_employee(self, *_args):
                if self.fail: raise OSError("disk unavailable")
                return {"dimension": 512}

        holder = {}
        def factory(*args, **kwargs):
            holder["controller"] = ControllerStub(*args, **kwargs)
            return holder["controller"]

        with patch("app.ui.common.dialogs.CameraPreviewController", side_effect=factory):
            dialog = EnrollmentDialog({"name": "Kh?i nh?n vi?n"}, service=ServiceStub())
        dialog.kind = "employee"
        dialog.samples.extend([object()] * 4)
        dialog._form_data = lambda: ({"full_name": "Test"}, {"employee_code": "EMP-1"})
        dialog._save_enrollment()
        self.assertEqual(dialog.result(), 0)
        self.assertIn("disk unavailable", dialog.status_label.text())
        self.assertEqual(holder["controller"].shutdown_calls, 0)
        dialog.service.fail = False
        dialog._save_enrollment()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(holder["controller"].shutdown_calls, 1)

    def test_cancel_calls_camera_worker_cleanup(self):
        class SignalStub:
            def connect(self, _slot):
                pass

        class ControllerStub:
            def __init__(self, *_args, **_kwargs):
                self.sample_analysis_ready = SignalStub()
                self.sample_analysis_error = SignalStub()
                self.face_analysis_error = SignalStub()
                self.cleaned = False

            def shutdown(self):
                self.cleaned = True

        holder = {}
        def controller_factory(*args, **kwargs):
            holder["controller"] = ControllerStub(*args, **kwargs)
            return holder["controller"]

        with patch("app.ui.common.dialogs.CameraPreviewController", side_effect=controller_factory):
            dialog = EnrollmentDialog({"name": "Khối nhân viên"}, service=object())
        dialog.done(QDialog.DialogCode.Rejected)
        self.assertTrue(holder["controller"].cleaned)
        self.assertEqual(len(dialog.samples), 0)


class EnrollmentWorkerTests(unittest.TestCase):
    def test_real_sample_request_is_inferred_on_background_qthread(self):
        calling_thread = threading.get_ident()
        worker_threads = {}
        completed = threading.Event()
        result_holder = {}

        class FakeFace:
            bbox = np.array([30, 30, 130, 130], dtype=np.float32)
            det_score = 0.99
            normed_embedding = np.array([1.0, 0.1, 0.2, 0.3], dtype=np.float32)

        class FakeModel:
            session = SimpleNamespace(_model_path="C:/models/w600k_r50.onnx")

        class FakeDetector:
            def __init__(self, **_kwargs):
                worker_threads["init"] = threading.get_ident()
                self.name = "buffalo_l"
                self.analysis = SimpleNamespace(models={"recognition": FakeModel()})

            def analyze(self, _frame):
                worker_threads["infer"] = threading.get_ident()
                return [FakeFace()]

        def on_result(index, frame, result):
            result_holder["value"] = (index, frame.shape, result)
            completed.set()

        worker = FaceAnalysisWorker()
        worker.sample_analysis_ready.connect(on_result, Qt.ConnectionType.DirectConnection)
        frame = np.full((200, 200, 3), 70, dtype=np.uint8)
        try:
            with patch("app.biometric.face_recognition.detector.InsightFaceDetector", FakeDetector):
                self.assertTrue(worker.submit_sample(2, frame))
                self.assertTrue(completed.wait(10))
        finally:
            if worker.isRunning():
                worker.stop_worker()
        index, shape, result = result_holder["value"]
        self.assertEqual(index, 2)
        self.assertEqual(shape, frame.shape)
        self.assertEqual(result.status, "face_selected")
        self.assertEqual(result.embedding_shape, (4,))
        self.assertNotEqual(worker_threads["init"], calling_thread)
        self.assertNotEqual(worker_threads["infer"], calling_thread)


if __name__ == "__main__":
    unittest.main()
