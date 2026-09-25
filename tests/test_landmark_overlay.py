"""Overlay tests: preview coordinate mapping, mesh pairing hand-off, and — when the
official MediaPipe asset is present — real FaceLandmarker inference on a real photo."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from app.biometric.liveness.active_liveness import (
    DEFAULT_FACE_LANDMARKER_PATH, MediaPipeFaceLandmarker, landmarks_for_selected_face,
)
from app.camera.camera_manager import CameraPreviewController
from app.ui.common import widgets
from app.ui.common.widgets import CameraView, map_bbox_to_preview, map_landmarks_to_preview

APP = QApplication.instance() or QApplication([])
SAMPLE_PHOTO = Path(__import__("insightface").__file__).parent / "data" / "images" / "Tom_Hanks_54745.png"


def mesh(cx=0.5, cy=0.5, half=0.1):
    """A synthetic normalized 478-point mesh centred on (cx, cy)."""
    points = np.zeros((478, 3), dtype=np.float64)
    angles = np.linspace(0, 2 * np.pi, 478, endpoint=False)
    points[:, 0] = cx + half * np.cos(angles)
    points[:, 1] = cy + half * np.sin(angles)
    return points


class LandmarkPreviewMappingTests(unittest.TestCase):
    rect = QRectF(10, 20, 300, 200)

    def test_normalized_landmarks_map_onto_the_stretched_preview(self):
        points = map_landmarks_to_preview(
            np.asarray([[0.0, 0.0, 0.0], [0.5, 0.25, 0.0], [1.0, 1.0, 0.0]]),
            (600, 400), self.rect,
        )
        self.assertEqual([tuple(p) for p in points], [(10, 20), (160, 70), (310, 220)])

    def test_mirroring_moves_landmarks_the_same_way_as_the_bounding_box(self):
        frame_size, box = (600, 400), (100.0, 50.0, 300.0, 150.0)
        corners = np.asarray([[box[0] / 600, box[1] / 400, 0.0], [box[2] / 600, box[3] / 400, 0.0]])
        mapped_box = map_bbox_to_preview(box, frame_size, self.rect, mirrored=True)
        mapped_points = map_landmarks_to_preview(corners, frame_size, self.rect, mirrored=True)
        self.assertAlmostEqual(min(p[0] for p in mapped_points), mapped_box.left())
        self.assertAlmostEqual(max(p[0] for p in mapped_points), mapped_box.right())
        self.assertAlmostEqual(min(p[1] for p in mapped_points), mapped_box.top())
        self.assertAlmostEqual(max(p[1] for p in mapped_points), mapped_box.bottom())

    def test_a_degenerate_frame_size_is_rejected_rather_than_drawn(self):
        with self.assertRaises(ValueError):
            map_landmarks_to_preview(mesh(), (0, 400), self.rect)


class CameraViewOverlayTests(unittest.TestCase):
    def setUp(self):
        self.view = CameraView("test")

    def test_a_valid_mesh_is_stored_as_two_dimensional_points(self):
        self.view.set_face_landmarks(mesh(), (480, 640, 3))
        self.assertEqual(self.view.face_landmarks.shape, (478, 2))
        self.assertEqual(self.view.frame_size, (640, 480))

    def test_malformed_or_missing_meshes_clear_the_overlay(self):
        self.view.set_face_landmarks(mesh(), (480, 640, 3))
        for bad in (None, np.zeros((478, 3)) * np.nan, np.zeros((3,)), np.zeros((478, 5))):
            self.view.set_face_landmarks(bad)
            self.assertIsNone(self.view.face_landmarks)
            self.view.set_face_landmarks(mesh(), (480, 640, 3))

    def test_painting_with_a_mesh_does_not_raise(self):
        self.view.resize(320, 240)
        self.view.set_face_bbox((10, 10, 100, 100), (480, 640, 3))
        self.view.set_face_landmarks(mesh(), (480, 640, 3))
        # Resolved off the paint path: importing MediaPipe from inside
        # paintEvent destabilises Qt teardown.
        self.assertIsNotNone(widgets._MESH_CONNECTIONS)
        self.view.grab()  # renders paintEvent offscreen


class PreviewControllerOverlayTests(unittest.TestCase):
    """The controller feeds the widget, so both attendance and enrollment previews
    receive the mesh of the Max-Area face only."""

    def setUp(self):
        self.view = CameraView("test")
        self.controller = CameraPreviewController(self.view, enable_face_analysis=False)
        self.addCleanup(self.controller.shutdown)
        self.controller._camera_accept_analysis = True

    def analysis(self, landmarks):
        return SimpleNamespace(status="face_selected", mediapipe_landmarks=landmarks,
                               tracking_bbox=(10.0, 10.0, 100.0, 100.0))

    def test_the_selected_face_mesh_reaches_the_preview_widget(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.controller._on_face_analysis_from_worker(frame, self.analysis(mesh()))
        self.assertEqual(self.view.face_landmarks.shape, (478, 2))
        self.assertEqual(self.view.frame_size, (640, 480))

    def test_a_frame_without_a_paired_mesh_clears_the_overlay(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.controller._on_face_analysis_from_worker(frame, self.analysis(mesh()))
        self.controller._on_face_analysis_from_worker(frame, self.analysis(None))
        self.assertIsNone(self.view.face_landmarks)

    def test_stopping_the_camera_clears_both_overlays(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.controller._on_face_analysis_from_worker(frame, self.analysis(mesh()))
        self.view.set_face_bbox((10, 10, 100, 100), frame.shape)
        self.controller.stop()
        self.assertIsNone(self.view.face_landmarks)
        self.assertIsNone(self.view.face_bbox)

    def test_a_bystander_mesh_is_never_forwarded_to_the_overlay(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        target, bystander = mesh(0.3, 0.5, 0.12), mesh(0.8, 0.5, 0.05)
        selected_box = (0.18 * 640, 0.38 * 480, 0.42 * 640, 0.62 * 480)
        paired = landmarks_for_selected_face([bystander, target], selected_box, frame.shape)
        self.controller._on_face_analysis_from_worker(frame, self.analysis(paired))
        np.testing.assert_allclose(self.view.face_landmarks, target[:, :2])


@unittest.skipUnless(DEFAULT_FACE_LANDMARKER_PATH.is_file(),
                     "official face_landmarker.task not installed")
class RealMediaPipeAssetTests(unittest.TestCase):
    """Real inference with the official Google asset — no webcam, still images only."""

    @classmethod
    def setUpClass(cls):
        cls.landmarker = MediaPipeFaceLandmarker()

    @classmethod
    def tearDownClass(cls):
        cls.landmarker.close()

    def test_the_default_asset_initializes_from_the_project_data_directory(self):
        self.assertEqual(Path(self.landmarker.model_path), DEFAULT_FACE_LANDMARKER_PATH.resolve())

    @unittest.skipUnless(SAMPLE_PHOTO.is_file(), "insightface sample photo not installed")
    def test_a_real_photo_yields_a_finite_478_point_mesh_paired_to_its_own_box(self):
        import cv2
        image = cv2.imread(str(SAMPLE_PHOTO))
        faces = self.landmarker.detect(image)
        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0].shape, (478, 3))
        self.assertTrue(np.all(np.isfinite(faces[0])))
        height, width = image.shape[:2]
        xs, ys = faces[0][:, 0] * width, faces[0][:, 1] * height
        box = (xs.min(), ys.min(), xs.max(), ys.max())
        self.assertIsNotNone(landmarks_for_selected_face(faces, box, image.shape))

    @unittest.skipUnless(SAMPLE_PHOTO.is_file(), "insightface sample photo not installed")
    def test_two_real_faces_yield_two_meshes_and_pairing_picks_the_larger_one(self):
        import cv2
        photo = cv2.imread(str(SAMPLE_PHOTO))
        scene = np.full((480, 640, 3), 220, dtype=np.uint8)
        target = cv2.resize(photo, (260, 260))
        bystander = cv2.resize(photo, (140, 140))
        scene[110:370, 40:300] = target
        scene[150:290, 470:610] = bystander
        faces = self.landmarker.detect(scene)
        self.assertEqual(len(faces), 2)
        paired = landmarks_for_selected_face(faces, (40, 110, 300, 370), scene.shape)
        self.assertIsNotNone(paired)
        self.assertLess(paired[:, 0].max() * 640, 400)  # the mesh sits on the large face
        self.assertIsNone(
            landmarks_for_selected_face(faces, (0, 0, 20, 20), scene.shape),
            "a box overlapping neither face must fail closed",
        )

    def test_an_empty_frame_produces_no_mesh_instead_of_a_fabricated_one(self):
        self.assertEqual(self.landmarker.detect(np.zeros((480, 640, 3), dtype=np.uint8)), ())


if __name__ == "__main__":
    unittest.main()
