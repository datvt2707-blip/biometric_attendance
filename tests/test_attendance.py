# File: tests/test_attendance.py
"""T6 attendance gating: recognition alone never writes attendance without a live MediaPipe proof."""
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.biometric.liveness.active_liveness import ActiveLivenessChallenge
from app.database.database import connect, initialize_database
from app.database.models.user import Employee, Person, Student
from app.database.repositories.user_repository import UserRepository
from app.services.attendance_service import AttendanceService
from auth_test_helpers import login_admin, logout


MATCH = {"status": "matched", "person_id": 1, "person_type": "employee"}


class _Proof:
    """Minimal stand-in for a completed challenge, mirroring consume()'s contract."""

    def __init__(self, *, accepts=True):
        self.accepts, self.consumed = accepts, 0

    def consume(self, match, *, track_id):
        self.consumed += 1
        return self.accepts and self.consumed == 1 and track_id is not None


class AttendanceGatingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "attendance.sqlite"
        initialize_database(self.db)
        connection = connect(self.db)
        users = UserRepository(connection)
        users.create_employee_with_person(Person(None, "Gate Employee"), Employee(None, 0, "G-001"))
        users.create_student_with_person(Person(None, "Gate Student"), Student(None, 0, "G-S01"))
        connection.commit()
        connection.close()
        login_admin(self.db)
        self.service = AttendanceService(self.db)
        self.production = patch.dict(os.environ, {"APP_ENV": "production",
                                                  "BIOMETRIC_ATTENDANCE_T6_DEV_MODE": "0"})
        self.production.start()

    def tearDown(self):
        self.production.stop()
        logout()
        self.temp.cleanup()

    def _employee_rows(self):
        connection = connect(self.db)
        try:
            return connection.execute("SELECT * FROM employee_attendance").fetchall()
        finally:
            connection.close()

    def test_recognition_without_a_challenge_never_writes_attendance(self):
        result = self.service.check_in(MATCH)
        self.assertEqual(result.status, "rejected")
        self.assertIn("MediaPipe", result.message)
        self.assertEqual(self._employee_rows(), [])

    def test_a_foreign_object_is_not_accepted_as_a_liveness_proof(self):
        result = self.service.check_in(MATCH, liveness_challenge=_Proof(), track_id=7)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(self._employee_rows(), [])

    def test_a_real_challenge_is_consumed_once_and_records_one_session(self):
        challenge = ActiveLivenessChallenge()
        with patch.object(ActiveLivenessChallenge, "consume",
                          side_effect=_Proof().consume, autospec=False):
            first = self.service.check_in(MATCH, liveness_challenge=challenge, track_id=11)
            second = self.service.check_in(MATCH, liveness_challenge=challenge, track_id=11)
        self.assertEqual(first.status, "success")
        self.assertEqual(second.status, "rejected")
        rows = self._employee_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["check_in_method"], rows[0]["status"], rows[0]["work_date"]),
                         ("face", "present", date.today().isoformat()))
        self.assertIsNone(rows[0]["check_out_at"])

    def test_a_rejected_challenge_blocks_the_write(self):
        challenge = ActiveLivenessChallenge()
        with patch.object(ActiveLivenessChallenge, "consume", side_effect=_Proof(accepts=False).consume):
            result = self.service.check_in(MATCH, liveness_challenge=challenge, track_id=11)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(self._employee_rows(), [])

    def test_check_out_also_requires_a_fresh_proof(self):
        challenge = ActiveLivenessChallenge()
        with patch.object(ActiveLivenessChallenge, "consume", side_effect=_Proof().consume):
            self.assertEqual(self.service.check_in(MATCH, liveness_challenge=challenge, track_id=11).status,
                             "success")
        self.assertEqual(self.service.check_out(MATCH).status, "rejected")
        self.assertIsNone(self._employee_rows()[0]["check_out_at"])
        with patch.object(ActiveLivenessChallenge, "consume", side_effect=_Proof().consume):
            closed = self.service.check_out(MATCH, liveness_challenge=challenge, track_id=11)
        self.assertEqual(closed.status, "success")
        self.assertIsNotNone(self._employee_rows()[0]["check_out_at"])

    def test_unmatched_or_malformed_identities_are_refused_before_any_permission_check(self):
        for match in ({"status": "ambiguous", "person_id": 1, "person_type": "employee"},
                      {"status": "matched", "person_id": 0, "person_type": "employee"},
                      {"status": "matched", "person_id": 1, "person_type": "visitor"}):
            self.assertEqual(self.service.check_in(match).status, "rejected")
        self.assertEqual(self._employee_rows(), [])

    def test_attendance_requires_the_matching_record_permission(self):
        from app.ui import session
        from auth_test_helpers import PASSWORDS
        from app.services.authentication_service import AuthenticationService
        session.establish(AuthenticationService(self.db).login("student_support", PASSWORDS["STUDENT_SUPPORT"]))
        with self.assertRaises(PermissionError):
            self.service.check_in(MATCH)
        self.assertEqual(self._employee_rows(), [])

    def test_student_check_in_needs_exactly_one_eligible_class(self):
        student_match = {"status": "matched", "person_id": 2, "person_type": "student"}
        with patch.dict(os.environ, {"BIOMETRIC_ATTENDANCE_T6_DEV_MODE": "1", "APP_ENV": "development"}):
            result = self.service.check_in(student_match)
        self.assertEqual(result.status, "rejected")
        self.assertIn("lớp", result.message)


if __name__ == "__main__":
    unittest.main()
