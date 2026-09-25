"""CameraManager lifecycle tests using an injected capture double."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from app.camera.camera_manager import CameraManager


class FakeCapture:
    def __init__(self, *, opened=True, readable=True):
        self.opened = opened
        self.readable = readable
        self.released = False
        self.reads = 0

    def isOpened(self):
        return self.opened

    def set(self, *_args):
        return True

    def read(self):
        self.reads += 1
        if not self.readable:
            return False, None
        return True, np.full((24, 32, 3), self.reads, dtype=np.uint8)

    def release(self):
        self.released = True


class CameraManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def run_until_result(self, capture):
        loop = QEventLoop()
        manager = CameraManager(capture_factory=lambda _source: capture)
        received = {"frame": None, "error": None, "opened": False}
        manager.camera_opened.connect(lambda: received.update(opened=True))
        manager.frame_ready.connect(lambda frame: (received.update(frame=frame), loop.quit()))
        manager.camera_error.connect(lambda message: (received.update(error=message), loop.quit()))
        self.assertTrue(manager.start_camera(source=0, fps=30))
        QTimer.singleShot(2000, loop.quit)
        loop.exec()
        stopped = manager.stop_camera(wait=True, timeout_ms=2000)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()
        return manager, received, stopped

    def test_frame_delivery_stop_and_capture_release(self):
        capture = FakeCapture()
        manager, received, stopped = self.run_until_result(capture)
        self.assertTrue(received["opened"])
        self.assertIsInstance(received["frame"], np.ndarray)
        self.assertEqual(received["frame"].shape, (24, 32, 3))
        self.assertTrue(stopped)
        self.assertTrue(capture.released)
        self.assertFalse(manager.is_running)

    def test_unavailable_camera_reports_error_and_releases_capture(self):
        capture = FakeCapture(opened=False)
        manager, received, stopped = self.run_until_result(capture)
        self.assertIsNone(received["frame"])
        self.assertIn("camera", received["error"].lower())
        self.assertTrue(stopped)
        self.assertTrue(capture.released)
        self.assertFalse(manager.is_running)

    def test_frame_read_failure_reports_error_and_releases_capture(self):
        capture = FakeCapture(readable=False)
        manager, received, stopped = self.run_until_result(capture)
        self.assertTrue(received["opened"])
        self.assertIsNone(received["frame"])
        self.assertIn("frame", received["error"].lower())
        self.assertTrue(stopped)
        self.assertTrue(capture.released)
        self.assertFalse(manager.is_running)

    def test_repeated_camera_open_close_cycles_release_each_capture(self):
        for _ in range(3):
            capture = FakeCapture()
            manager, received, stopped = self.run_until_result(capture)
            self.assertTrue(received["opened"])
            self.assertIsNotNone(received["frame"])
            self.assertTrue(stopped)
            self.assertTrue(capture.released)
            self.assertFalse(manager.is_running)


if __name__ == "__main__":
    unittest.main()
