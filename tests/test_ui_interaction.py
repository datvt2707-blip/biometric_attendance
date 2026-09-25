"""Regressions for the responsive layout, date pickers, identity hold and password change."""
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from app.ui.common.widgets import Card, DateEdit, ResponsiveRow, action_cell, make_table


def qt_app():
    return QApplication.instance() or QApplication([])


def match(person_id=42, person_type="employee", status="matched", similarity=0.91):
    return SimpleNamespace(status=status, person_id=person_id, person_type=person_type,
                           display_name="Person", person_code="E-1", similarity=similarity)


def analysis(tracking_id=7):
    return SimpleNamespace(status="face_selected", face_count=1,
                           selected=SimpleNamespace(bbox=(10.0, 10.0, 90.0, 90.0)),
                           embedding=np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
                           mediapipe_landmarks=None, tracking_id=tracking_id,
                           frame_sequence=1)


class DatePickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_empty_calendar_reports_no_date_and_round_trips_iso(self):
        edit = DateEdit()
        self.assertEqual(edit.text(), "")
        edit.set_value("2026-09-25")
        self.assertEqual(edit.text(), "2026-09-25")
        edit.clear()
        self.assertEqual(edit.text(), "")

    def test_invalid_or_missing_value_stays_empty(self):
        for value in (None, "", "25/09/2026", "not-a-date"):
            self.assertEqual(DateEdit(value).text(), "")

    def test_calendar_popup_is_available_for_picking(self):
        self.assertTrue(DateEdit().calendarPopup())


class ResponsiveLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_cards_stack_when_narrow_and_sit_side_by_side_when_wide(self):
        row = ResponsiveRow([Card(), Card()], threshold=980)
        row.show()
        row.resize(1400, 400)
        self.app.processEvents()
        self.assertTrue(row._horizontal)
        row.resize(700, 400)
        self.app.processEvents()
        self.assertFalse(row._horizontal)
        row.resize(1400, 400)
        self.app.processEvents()
        self.assertTrue(row._horizontal)

    def test_three_leave_buttons_keep_their_full_caption_width(self):
        cell = action_cell([("Xem", "brass"), ("Duy\u1ec7t", "ok"), ("T\u1eeb ch\u1ed1i", "late")])
        buttons = cell.findChildren(QPushButton)
        self.assertEqual([b.text() for b in buttons], ["Xem", "Duy\u1ec7t", "T\u1eeb ch\u1ed1i"])
        for button in buttons:
            needed = button.fontMetrics().horizontalAdvance(button.text())
            self.assertGreater(button.minimumWidth(), needed)
        self.assertGreaterEqual(cell.minimumWidth(),
                                sum(b.minimumWidth() for b in buttons))

    def test_action_column_is_sized_to_its_buttons(self):
        from PySide6.QtWidgets import QHeaderView
        table = make_table(["A", "B"], [("1", "2")],
                           actions=lambda _row: [("Xem", "brass"), ("Duy\u1ec7t", "ok"),
                                                 ("T\u1eeb ch\u1ed1i", "late")])
        header = table.horizontalHeader()
        self.assertEqual(header.sectionResizeMode(2), QHeaderView.Fixed)
        table.resize(520, 300)
        self.app.processEvents()
        cell = table.cellWidget(0, 2)
        self.assertGreaterEqual(table.columnWidth(2), cell.minimumWidth())


class RecognitionHoldTests(unittest.TestCase):
    """A confirmed identity must stop flickering between frames."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def view(self):
        from PySide6.QtCore import QObject, Signal
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
             patch("app.services.attendance_service.AttendanceService",
                   return_value=HistoryService()):
            return ui_views.AttendanceView("staff", "attendance")

    def test_hold_needs_consecutive_confirmations_then_survives_a_dropped_frame(self):
        view = self.view()
        result = analysis()
        first = view._hold_identity(match(similarity=0.90), result)
        self.assertIsNone(view._held_match)
        self.assertEqual(first.similarity, 0.90)
        view._hold_identity(match(similarity=0.92), result)
        self.assertIsNotNone(view._held_match)
        dropped = view._hold_identity(None, result)
        self.assertIs(dropped, view._held_match)
        self.assertEqual(dropped.similarity, 0.92)
        view.close()

    def test_hold_is_dropped_on_track_change_identity_change_and_timeout(self):
        view = self.view()
        for _ in range(view.HOLD_CONFIRMATIONS):
            view._hold_identity(match(), analysis())
        self.assertIsNotNone(view._held_match)
        view._hold_identity(None, analysis(tracking_id=8))
        self.assertIsNone(view._held_match)

        for _ in range(view.HOLD_CONFIRMATIONS):
            view._hold_identity(match(person_id=1), analysis())
        self.assertEqual(view._held_match.person_id, 1)
        held = view._hold_identity(match(person_id=2), analysis())
        self.assertEqual(held.person_id, 2)
        self.assertIsNone(view._held_match)

        for _ in range(view.HOLD_CONFIRMATIONS):
            view._hold_identity(match(), analysis())
        view._held_at = time.monotonic() - view.HOLD_SECONDS - 1
        view._hold_identity(None, analysis())
        self.assertIsNone(view._held_match)
        view.close()

    def test_release_hold_clears_every_field(self):
        view = self.view()
        for _ in range(view.HOLD_CONFIRMATIONS):
            view._hold_identity(match(), analysis())
        view._release_hold()
        self.assertIsNone(view._held_match)
        self.assertIsNone(view._held_track)
        self.assertIsNone(view._held_at)
        self.assertEqual(view._match_streak, 0)
        view.close()

    def test_hold_never_enables_attendance_without_a_fresh_face_and_proof(self):
        view = self.view()
        view._development_t6_mode = False
        for _ in range(view.HOLD_CONFIRMATIONS):
            view._hold_identity(match(), analysis())
        view._last_analysis = analysis()
        view._last_analysis_at = time.monotonic()
        view._set_attendance_match(view._held_match)
        self.assertFalse(any(button.isEnabled() for _a, button in view._attendance_buttons))
        view.close()

    def test_clearing_the_date_filters_removes_both_bounds(self):
        view = self.view()
        view._attendance_from_date.set_value("2026-09-01")
        view._attendance_to_date.set_value("2026-09-30")
        self.assertEqual(view._attendance_filters()["from_date"], "2026-09-01")
        view._clear_attendance_dates()
        filters = view._attendance_filters()
        self.assertIsNone(filters["from_date"])
        self.assertIsNone(filters["to_date"])
        view.close()


class ChangePasswordTests(unittest.TestCase):
    """The self-service dialog must reach AuthenticationService and reject bad input."""

    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def run_dialog(self, current, new, again, *, service_error=None):
        from app.ui.common import dialogs as D

        calls = []

        class Service:
            def change_password(self, username, current_password, new_password):
                calls.append((username, current_password, new_password))
                if service_error is not None:
                    raise service_error

        captured = {}

        class Recorder:
            def __init__(self, dialog): self.dialog = dialog

        def fake_exec(dialog_self):
            captured["dialog"] = dialog_self
            widgets = captured["widgets"]
            for widget, value in zip(widgets, (current, new, again)):
                widget.setText(value)
            captured["save"].click()
            return 0

        original_form = D.form

        def spy_form(fields, cols=2):
            grid = original_form(fields, cols=cols)
            captured["widgets"] = grid.field_widgets
            return grid

        original_footer = D.Dialog.footer

        def spy_footer(dialog_self, *args, **kwargs):
            button = original_footer(dialog_self, *args, **kwargs)
            captured["save"] = button
            return button

        with patch("app.services.authentication_service.AuthenticationService",
                   return_value=Service()), \
             patch.object(D, "form", spy_form), \
             patch.object(D.Dialog, "footer", spy_footer), \
             patch.object(D.Dialog, "exec", fake_exec), \
             patch.object(D, "confirm", lambda *a, **k: None):
            D.change_password(None, "admin")
        return calls, captured["dialog"]

    def test_valid_input_reaches_the_service(self):
        calls, _dialog = self.run_dialog("OldPassword12", "BrandNewPass34", "BrandNewPass34")
        self.assertEqual(calls, [("admin", "OldPassword12", "BrandNewPass34")])

    def test_blank_short_mismatched_and_unchanged_passwords_are_rejected(self):
        for current, new, again in (("", "BrandNewPass34", "BrandNewPass34"),
                                    ("OldPassword12", "", ""),
                                    ("OldPassword12", "short", "short"),
                                    ("OldPassword12", "BrandNewPass34", "Different12345"),
                                    ("OldPassword12", "OldPassword12", "OldPassword12")):
            calls, _dialog = self.run_dialog(current, new, again)
            self.assertEqual(calls, [], f"service must not be called for {new!r}")

    def test_service_error_is_shown_without_closing_the_dialog(self):
        calls, _dialog = self.run_dialog("WrongPassword1", "BrandNewPass34", "BrandNewPass34",
                                         service_error=ValueError("Mật khẩu hiện tại không đúng."))
        self.assertEqual(len(calls), 1)


class ChangePasswordServiceTests(unittest.TestCase):
    """AuthenticationService must verify the current password and persist a new hash."""

    def service(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        from app.database import database
        from app.services.authentication_service import AuthenticationService
        temp = tempfile.mkdtemp()
        path = Path(temp) / "attendance.db"
        source = sqlite3.connect(str(database.DEFAULT_DATABASE_PATH))
        target = sqlite3.connect(str(path))
        source.backup(target)
        source.close(); target.close()
        return AuthenticationService(database_path=path), path

    def test_wrong_current_password_is_rejected_and_the_hash_is_unchanged(self):
        import sqlite3
        service, path = self.service()
        with sqlite3.connect(str(path)) as conn:
            before = conn.execute("SELECT password_hash FROM accounts WHERE username='admin'").fetchone()
        if before is None:
            self.skipTest("no bootstrap admin account in the database copy")
        with self.assertRaises(Exception):
            service.change_password("admin", "definitely-not-the-password", "BrandNewPass34")
        with sqlite3.connect(str(path)) as conn:
            after = conn.execute("SELECT password_hash FROM accounts WHERE username='admin'").fetchone()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
