# File: tests/test_face_recognition.py
"""T3: prove histogram equalization runs inside the real recognition pipeline."""
import unittest
from types import SimpleNamespace

import cv2
import numpy as np

from app.biometric.face_recognition.face_recognizer import (
    RECOGNITION_PREPROCESSING, FaceRecognizer,
)
from app.biometric.preprocessing.image_preprocessing import (
    PreprocessingConfig, preprocess_face,
)
from app.services.enrollment_service import EnrollmentCaptureSession


def equalized(frame):
    """What T3 requires: cv2.equalizeHist on luminance, never CLAHE."""
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    ycrcb[:, :, 0] = cv2.equalizeHist(ycrcb[:, :, 0])
    return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)


def frame(seed=0, shape=(400, 600, 3)):
    """A low-contrast, unevenly lit frame, so equalization measurably changes it."""
    rng = np.random.default_rng(seed)
    gradient = np.linspace(20, 90, shape[1], dtype=np.float64)[None, :, None]
    noise = rng.integers(0, 12, size=shape)
    return np.clip(gradient + noise, 0, 255).astype(np.uint8)


class Face:
    """Stand-in for insightface.app.common.Face: normed_embedding is derived."""

    def __init__(self, bbox, kps=((0, 0),) * 5, embedding=(1.0, 0.0, 0.0)):
        self.bbox = np.asarray(bbox, dtype=np.float32)
        self.det_score = 0.99
        self.kps = np.asarray(kps, dtype=np.float32)
        self.embedding = np.asarray(embedding, dtype=np.float32)

    @property
    def normed_embedding(self):
        return self.embedding / float(np.linalg.norm(self.embedding))


class RecognitionModel:
    """Mimics ArcFaceONNX.get(img, face): embeds whatever image it is handed."""

    def __init__(self):
        self.images = []
        self.faces = []
        self.session = SimpleNamespace(_model_path="/models/w600k_r50.onnx")

    def get(self, img, face):
        self.images.append(np.asarray(img).copy())
        self.faces.append(face)
        face.embedding = np.asarray(
            [float(img.mean()), float(img.std()), 1.0], dtype=np.float32,
        )
        return face.embedding


class Detector:
    name = "buffalo_l"

    def __init__(self, faces, recognition=None):
        self.frames = []
        self._faces = list(faces)
        self.analysis = SimpleNamespace(
            models={"recognition": recognition} if recognition is not None else {},
        )

    def analyze(self, bgr_image):
        self.frames.append(np.asarray(bgr_image).copy())
        return list(self._faces)


class HistogramEqualizationInPipelineTests(unittest.TestCase):
    """The pipeline, not just preprocess_face(), must equalize before embedding."""

    def setUp(self):
        self.model = RecognitionModel()
        self.face = Face((200, 100, 360, 260))
        self.detector = Detector([self.face], self.model)
        self.recognizer = FaceRecognizer(self.detector)
        self.frame = frame()

    def test_recognition_input_is_the_histogram_equalized_frame(self):
        result = self.recognizer.analyze(self.frame)
        self.assertEqual(result.status, "face_selected")
        self.assertEqual(result.preprocessing, "histogram")
        self.assertEqual(len(self.model.images), 1, "recognition ran once, on the selected face")
        np.testing.assert_array_equal(self.model.images[0], equalized(self.frame))
        self.assertFalse(np.array_equal(self.model.images[0], self.frame))
        # Detection still sees the untouched capture.
        np.testing.assert_array_equal(self.detector.frames[0], self.frame)

    def test_embedding_comes_from_the_equalized_inference(self):
        result = self.recognizer.analyze(self.frame)
        expected = np.asarray(
            [equalized(self.frame).mean(), equalized(self.frame).std(), 1.0], dtype=np.float32,
        )
        np.testing.assert_allclose(
            result.embedding, expected / np.linalg.norm(expected), rtol=1e-6,
        )
        self.assertEqual(result.embedding_shape, (3,))

    def test_it_is_histogram_equalization_and_not_clahe(self):
        self.assertEqual(RECOGNITION_PREPROCESSING.equalization, "histogram")
        clahe = preprocess_face(self.frame, config=PreprocessingConfig(equalization="clahe"))
        self.recognizer.analyze(self.frame)
        self.assertFalse(np.array_equal(self.model.images[0], clahe))

    def test_geometry_dimensions_and_tracking_are_unchanged_by_preprocessing(self):
        plain = FaceRecognizer(
            Detector([Face((200, 100, 360, 260))], RecognitionModel()),
            preprocessing=PreprocessingConfig(equalization="none"),
        ).analyze(self.frame)
        equal = self.recognizer.analyze(self.frame)
        self.assertEqual(equal.selected.bbox, plain.selected.bbox)
        self.assertEqual(equal.tracking_bbox, plain.tracking_bbox)
        self.assertEqual(equal.face_count, plain.face_count)
        np.testing.assert_array_equal(equal.landmarks, plain.landmarks)
        self.assertEqual(self.model.images[0].shape, self.frame.shape)
        self.assertEqual(self.model.images[0].dtype, self.frame.dtype)
        self.assertEqual(plain.preprocessing, "none")

    def test_only_the_max_area_face_is_equalized_and_embedded(self):
        target = Face((200, 100, 400, 300))
        bystander = Face((40, 40, 90, 90))
        model = RecognitionModel()
        recognizer = FaceRecognizer(Detector([bystander, target], model))
        result = recognizer.analyze(self.frame)
        self.assertEqual(result.selected.bbox, tuple(float(v) for v in target.bbox))
        self.assertEqual(len(model.faces), 1)
        self.assertIs(model.faces[0], target)

    def test_pipeline_falls_back_instead_of_dropping_a_frame(self):
        without_model = FaceRecognizer(Detector([Face((200, 100, 360, 260))]))
        self.assertEqual(without_model.analyze(self.frame).preprocessing, "none")

        no_landmarks = Face((200, 100, 360, 260))
        no_landmarks.kps = None
        self.assertEqual(
            FaceRecognizer(Detector([no_landmarks], RecognitionModel())).analyze(self.frame).preprocessing,
            "none",
        )

        grayscale = cv2.cvtColor(self.frame, cv2.COLOR_BGR2GRAY)
        broken = FaceRecognizer(Detector([Face((200, 100, 360, 260))], RecognitionModel()))
        result = broken.analyze(grayscale)
        self.assertEqual(result.preprocessing, "histogram_unavailable")
        self.assertIsNotNone(result.embedding)

    def test_enrollment_samples_are_captured_from_the_equalized_pipeline(self):
        session = EnrollmentCaptureSession()
        for index in range(4):
            captured = frame(seed=index + 1)
            recognizer = FaceRecognizer(
                Detector([Face((200, 100, 360, 260))], RecognitionModel()),
            )
            result = recognizer.analyze(captured)
            self.assertEqual(result.preprocessing, "histogram")
            session.accept(captured, result)
        self.assertEqual(len(session.samples), 4)


if __name__ == "__main__":
    unittest.main()
