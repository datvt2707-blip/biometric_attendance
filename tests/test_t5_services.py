"""T5 database service tests against isolated temporary SQLite databases."""
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path

from app.database.database import connect, initialize_database
from app.database.models.class_model import Class, Enrollment
from app.database.models.user import Employee, Person, Student
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.user_repository import UserRepository
from app.services.attendance_service import AttendanceService
from app.services.account_service import AccountService
from app.services.class_service import ClassService
from app.services.dashboard_service import DashboardService
from app.services.employee_service import EmployeeService
from app.services.leave_service import LeaveService
from app.services.settings_service import SettingsService
from app.services.student_service import StudentService
from auth_test_helpers import login_admin, logout
from app.ui.common import dialogs
from PySide6.QtWidgets import QApplication, QWidget


class T5ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite"
        initialize_database(self.db)
        con = connect(self.db)
        users = UserRepository(con)
        _, self.employee = users.create_employee_with_person(
            Person(None, "Test Employee"), Employee(None, 0, "T-001")
        )
        _, self.student = users.create_student_with_person(
            Person(None, "Test Student"), Student(None, 0, "S-001")
        )
        classes = ClassRepository(con)
        self.class_id = classes.create_class(Class(None, "Test Class", "2026"))
        self.enrollment_id = classes.create_enrollment(
            Enrollment(None, self.student, self.class_id, date.today().isoformat())
        )
        con.execute("INSERT INTO accounts(username,password_hash,password_scheme) VALUES(?,?,?)",
                    ("reviewer", "pbkdf2_sha256$" + "a" * 64, "pbkdf2_sha256"))
        self.reviewer = con.execute("SELECT account_id FROM accounts WHERE username='reviewer'").fetchone()[0]
        con.commit()
        con.close()
        login_admin(self.db)
        self.attendance = AttendanceService(self.db)
        self.leave = LeaveService(self.db)
        self.dev_mode = patch.dict(os.environ, {
            "APP_ENV": "development", "BIOMETRIC_ATTENDANCE_T6_DEV_MODE": "1",
        })
        self.dev_mode.start()

    def tearDown(self):
        self.dev_mode.stop()
        logout()
        self.temp.cleanup()

    def test_employee_check_in_then_checkout_and_duplicate_protection(self):
        matched = {"status": "matched", "person_id": 1, "person_type": "employee"}
        first = self.attendance.check_in(matched)
        self.assertEqual(first.status, "success")
        self.assertEqual(self.attendance.check_in(matched).status, "rejected")
        closed = self.attendance.check_out(matched)
        self.assertEqual(closed.status, "success")
        self.assertEqual(self.attendance.check_out(matched).status, "rejected")

    def test_unknown_match_cannot_write_attendance(self):
        result = self.attendance.check_in({"status": "ambiguous", "person_id": 1, "person_type": "employee"})
        self.assertEqual(result.status, "rejected")
        con = connect(self.db)
        try: self.assertEqual(con.execute("SELECT count(*) FROM employee_attendance").fetchone()[0], 0)
        finally: con.close()

    def test_production_attendance_requires_fresh_consumable_mediapipe_proof(self):
        with patch.dict(os.environ, {
            "APP_ENV": "production", "BIOMETRIC_ATTENDANCE_T6_DEV_MODE": "1",
        }):
            result = self.attendance.check_in({
                "status": "matched", "person_id": 1, "person_type": "employee",
            })
        self.assertEqual(result.status, "rejected")
        self.assertIn("MediaPipe", result.message)

    def test_student_attendance_requires_unique_active_class_and_blocks_duplicate(self):
        matched = {"status": "matched", "person_id": 2, "person_type": "student"}
        self.assertEqual(self.attendance.check_in(matched).status, "success")
        self.assertEqual(self.attendance.check_in(matched).status, "rejected")
        self.assertEqual(self.attendance.check_out(matched).status, "rejected")

    def _employee_request(self):
        return self.leave.create_employee_request(self.employee, {
            "leave_type": "personal", "start_date": "2026-09-25", "end_date": "2026-09-25",
            "reason": "Personal request",
        })

    def test_leave_create_is_idempotent_and_validates_dates(self):
        values = {
            "leave_type": "personal", "start_date": "2026-09-25", "end_date": "2026-09-25",
            "reason": "Personal request",
        }
        leave_id = self.leave.create_employee_request(self.employee, values)
        self.assertEqual(len(self.leave.list_requests("staff", query="T-001")), 1)
        self.assertEqual(self.leave.create_employee_request(self.employee, values), leave_id)
        with self.assertRaises(ValueError):
            self.leave.create_employee_request(self.employee, values | {"start_date": "2026-02-30"})

    def test_leave_approval_records_reviewer_and_blocks_re_review(self):
        leave_id = self._employee_request()
        self.assertEqual(self.leave.review("staff", leave_id, "approved", note="Đồng ý"), "approved")
        con = connect(self.db)
        try:
            row = con.execute(
                "SELECT status, reviewed_by_account_id, reviewed_at, review_note "
                "FROM employee_leave_requests WHERE leave_request_id=?", (leave_id,)).fetchone()
            self.assertEqual(row["status"], "approved")
            self.assertEqual(row["review_note"], "Đồng ý")
            self.assertIsNotNone(row["reviewed_at"])
            self.assertEqual(
                con.execute("SELECT username FROM accounts WHERE account_id=?",
                            (row["reviewed_by_account_id"],)).fetchone()["username"], "admin")
            self.assertEqual(con.execute("SELECT count(*) FROM employee_attendance").fetchone()[0], 0)
        finally:
            con.close()
        with self.assertRaises(ValueError):
            self.leave.review("staff", leave_id, "rejected", note="Đổi ý")

    def test_leave_rejection_requires_a_note_and_leaves_request_pending(self):
        leave_id = self._employee_request()
        with self.assertRaises(ValueError):
            self.leave.review("staff", leave_id, "rejected")
        con = connect(self.db)
        try:
            self.assertEqual(con.execute(
                "SELECT status FROM employee_leave_requests WHERE leave_request_id=?",
                (leave_id,)).fetchone()["status"], "pending")
        finally:
            con.close()
        self.assertEqual(self.leave.review("staff", leave_id, "rejected", note="Không đủ nhân sự"), "rejected")

    def test_leave_review_validates_kind_decision_and_request(self):
        leave_id = self._employee_request()
        for args in (("payroll", leave_id, "approved"), ("staff", leave_id, "cancelled")):
            with self.assertRaises(ValueError):
                self.leave.review(*args)
        with self.assertRaises(ValueError):
            self.leave.review("staff", leave_id + 999, "approved")
        with self.assertRaises(ValueError):
            self.leave.review("staff", leave_id, "approved", reviewer_account_id=99999)

    def test_student_leave_review_requires_the_student_review_permission(self):
        request_id = self.leave.create_student_request(self.student, {
            "class_id": self.class_id, "leave_date": "2026-09-25",
            "submitted_by_type": "guardian", "reason": "Ốm",
        })
        from auth_test_helpers import PASSWORDS
        from app.services.authentication_service import AuthenticationService
        from app.ui import session
        session.establish(AuthenticationService(self.db).login("hr", PASSWORDS["HR"]))
        with self.assertRaises(PermissionError):
            self.leave.review("student", request_id, "approved")
        session.establish(AuthenticationService(self.db).login("student_support", PASSWORDS["STUDENT_SUPPORT"]))
        self.assertEqual(self.leave.review("student", request_id, "approved"), "approved")

    def test_attendance_history_pages_validate_filters_and_use_stable_order(self):
        con = connect(self.db)
        first_day = date.today().isoformat()
        previous_day = (date.today().replace(day=1)).isoformat()
        con.execute("INSERT INTO employee_attendance(employee_id,work_date,check_in_at,status) VALUES(?,?,?,?)",
                    (self.employee, first_day, first_day + "T08:00:00Z", "present"))
        con.execute("INSERT INTO employee_attendance(employee_id,work_date,check_in_at,status) VALUES(?,?,?,?)",
                    (self.employee, first_day, first_day + "T09:00:00Z", "late"))
        con.execute("INSERT INTO employee_attendance(employee_id,work_date,check_in_at,status) VALUES(?,?,?,?)",
                    (self.employee, previous_day, previous_day + "T08:00:00Z", "present"))
        con.commit()
        con.close()
        page1 = self.attendance.list_history("staff", from_date=first_day, to_date=first_day, limit=1, offset=0)
        page2 = self.attendance.list_history("staff", from_date=first_day, to_date=first_day, limit=1, offset=1)
        self.assertEqual(len(page1), 1)
        self.assertEqual(len(page2), 1)
        self.assertNotEqual(page1[0][6], page2[0][6])
        self.assertEqual(self.attendance.list_history("staff", from_date=first_day, to_date=first_day, status="late")[0][-1], "late")
        self.assertEqual(self.attendance.count_history(
            "staff", from_date=first_day, to_date=first_day, query="T-001", status="late"), 1)
        self.assertEqual(self.attendance.count_history(
            "staff", from_date=first_day, to_date=first_day, status="absent"), 0)
        with self.assertRaises(ValueError):
            self.attendance.list_history("staff", from_date="2026-02-30")
        with self.assertRaises(ValueError):
            self.attendance.list_history("staff", from_date=first_day, to_date=previous_day)
        with self.assertRaises(ValueError):
            self.attendance.list_history("staff", status="pending")

    def test_dashboard_values_are_database_aggregates(self):
        result = self.attendance.check_in({"status": "matched", "person_id": 1, "person_type": "employee"})
        self.assertEqual(result.status, "success")
        overview = DashboardService(self.db).overview("staff", today=date.today())
        self.assertEqual(overview["stats"][0][1], 1)
        self.assertEqual(overview["stats"][1][1], 1)

    def test_employee_and_student_services_search_update_and_deactivate(self):
        employees = EmployeeService(self.db)
        students = StudentService(self.db)
        self.assertEqual(employees.search_directory("T-001")[1], 1)
        self.assertEqual(students.search_directory("S-001")[1], 1)
        con = connect(self.db)
        try:
            con.execute("UPDATE employees SET employment_status='on_leave' WHERE employee_id=?", (self.employee,))
            con.execute("UPDATE students SET student_status='graduated' WHERE student_id=?", (self.student,))
            con.commit()
        finally:
            con.close()
        self.assertEqual(employees.search_directory(status=("on_leave", "terminated", "inactive"))[1], 1)
        self.assertEqual(students.search_directory(status=("reserved", "graduated", "inactive"))[1], 1)
        employee = employees.get_by_code("T-001")
        employees.save(employee["person"] | {"full_name": "Updated Employee"},
                       {"employee_code": "T-001"}, employee_id=employee["employee"]["employee_id"])
        self.assertEqual(employees.get_by_code("T-001")["person"]["full_name"], "Updated Employee")
        with self.assertRaises(ValueError):
            employees.save({"full_name": "Duplicate"}, {"employee_code": "T-001"})
        student = students.get_by_code("S-001")
        students.save(student["person"], {"student_code": "S-001"}, student_id=student["student"]["student_id"], class_id=self.class_id)
        con = connect(self.db)
        enrollment = ClassRepository(con).list_enrollments(student_id=self.student, active_only=True)[0]
        con.execute("INSERT INTO student_attendance(student_id,class_id,enrollment_id,attendance_date,status) VALUES(?,?,?,?,?)",
                    (self.student, self.class_id, enrollment["enrollment_id"], date.today().isoformat(), "present"))
        con.commit()
        con.close()
        self.assertTrue(students.deactivate(student["student"]["student_id"]))
        self.assertEqual(students.search_directory("S-001", "inactive")[1], 1)
        con = connect(self.db)
        try:
            enrollment = con.execute("SELECT enrollment_status,end_date FROM enrollments WHERE enrollment_id=?",
                                     (self.enrollment_id,)).fetchone()
            self.assertEqual((enrollment["enrollment_status"], enrollment["end_date"]), ("withdrawn", date.today().isoformat()))
            self.assertEqual(con.execute("SELECT count(*) FROM student_attendance WHERE student_id=?", (self.student,)).fetchone()[0], 1)
        finally:
            con.close()

    def test_employee_directory_offset_pages_are_disjoint_and_ordered(self):
        service = EmployeeService(self.db)
        for index in range(2, 5):
            service.save({"full_name": f"Employee {index}"}, {"employee_code": f"T-{index:03d}"})
        first, total = service.search_directory("T-", limit=2, offset=0)
        second, second_total = service.search_directory("T-", limit=2, offset=2)
        self.assertEqual(total, 4)
        self.assertEqual(second_total, 4)
        self.assertEqual([row[0] for row in first], sorted(row[0] for row in first))
        self.assertFalse({row[0] for row in first} & {row[0] for row in second})
        self.assertEqual(len(first) + len(second), 4)

    def test_class_crud_and_roster_use_real_enrollment(self):
        service = ClassService(self.db)
        rows = service.list_classes()
        self.assertEqual(rows[0]["active_students"], 1)
        roster = service.roster(self.class_id, date.today().isoformat())
        self.assertEqual(roster[0][0:2], ("S-001", "Test Student"))
        with self.assertRaises(ValueError):
            service.save({"class_name": "Test Class", "academic_year": "2026"})

    def test_account_directory_is_read_only_until_authenticated_permissions_exist(self):
        service = AccountService(self.db)
        accounts, _roles, _permissions, _assignments = service.directory()
        self.assertEqual(len(accounts), 4)
        self.assertNotIn("password_hash", accounts[0])
        self.assertTrue(service.set_status(accounts[0]["account_id"], "locked"))
        accounts, *_ = service.directory()
        self.assertEqual(accounts[0]["account_status"], "locked")

    def test_class_enrollment_add_and_withdraw_write_real_rows(self):
        service = ClassService(self.db)
        students = StudentService(self.db)
        students.save({"full_name": "Second Student"}, {"student_code": "S-002"})
        candidates = service.enrollable_students(self.class_id)
        self.assertEqual([row["student_code"] for row in candidates], ["S-002"])
        second = candidates[0]["student_id"]
        enrollment_id = service.enroll_student(self.class_id, second)
        self.assertEqual(len(service.enrolled_students(self.class_id)), 2)
        with self.assertRaises(ValueError):
            service.enroll_student(self.class_id, second)
        with self.assertRaises(ValueError):
            service.enroll_student(self.class_id, second, "2026-02-30")
        con = connect(self.db)
        try:
            row = con.execute("SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
            self.assertEqual((row["enrollment_status"], row["start_date"], row["end_date"]),
                             ("active", date.today().isoformat(), None))
        finally:
            con.close()
        service.withdraw_student(self.class_id, second)
        self.assertEqual([row["student_code"] for row in service.enrolled_students(self.class_id)], ["S-001"])
        con = connect(self.db)
        try:
            row = con.execute("SELECT * FROM enrollments WHERE enrollment_id=?", (enrollment_id,)).fetchone()
            self.assertEqual((row["enrollment_status"], row["end_date"]), ("withdrawn", date.today().isoformat()))
        finally:
            con.close()
        with self.assertRaises(ValueError):
            service.withdraw_student(self.class_id, second)

    def test_class_enrollment_enforces_capacity_only_when_defined(self):
        service = ClassService(self.db)
        students = StudentService(self.db)
        students.save({"full_name": "Third Student"}, {"student_code": "S-003"})
        third = service.enrollable_students(self.class_id)[0]["student_id"]
        service.save({"class_name": "Test Class", "academic_year": "2026", "capacity": 1},
                     class_id=self.class_id)
        with self.assertRaises(ValueError):
            service.enroll_student(self.class_id, third)
        service.save({"class_name": "Test Class", "academic_year": "2026", "capacity": None},
                     class_id=self.class_id)
        self.assertTrue(service.enroll_student(self.class_id, third))

    def test_account_creation_hashes_password_and_supports_lock_unlock(self):
        service = AccountService(self.db)
        roles = {row["role_code"] for row in service.assignable_roles()}
        self.assertTrue({"ADMIN", "HR", "STUDENT_SUPPORT"} <= roles)
        created = service.create_account("new.operator", "HR")
        self.assertGreaterEqual(len(created["password"]), 12)
        con = connect(self.db)
        try:
            row = con.execute("SELECT * FROM accounts WHERE username='new.operator'").fetchone()
            self.assertEqual(row["password_scheme"], "scrypt")
            self.assertNotIn(created["password"], row["password_hash"])
            self.assertEqual(con.execute(
                "SELECT r.role_code FROM account_roles ar JOIN roles r USING(role_id) WHERE ar.account_id=?",
                (row["account_id"],)).fetchone()["role_code"], "HR")
        finally:
            con.close()
        from app.services.authentication_service import AuthenticationService
        identity = AuthenticationService(self.db).login("new.operator", created["password"])
        self.assertEqual(identity.username, "new.operator")
        for bad in ("new.operator", "ab", "has space"):
            with self.assertRaises(ValueError):
                service.create_account(bad, "HR")
        with self.assertRaises(ValueError):
            service.create_account("another.operator", "NOT_A_ROLE")
        service.set_status(created["account_id"], "locked")
        with self.assertRaises(Exception):
            AuthenticationService(self.db).login("new.operator", created["password"])
        service.set_status(created["account_id"], "active")
        self.assertEqual(
            AuthenticationService(self.db).login("new.operator", created["password"]).username, "new.operator")

    def test_change_password_rejects_wrong_current_password(self):
        from app.services.authentication_service import AuthenticationError, AuthenticationService
        service = AuthenticationService(self.db)
        created = AccountService(self.db).create_account("pw.operator", "HR")
        with self.assertRaises(AuthenticationError):
            service.change_password("pw.operator", "wrong-password", "Another-Password-2026!")
        service.change_password("pw.operator", created["password"], "Another-Password-2026!")
        with self.assertRaises(AuthenticationError):
            service.login("pw.operator", created["password"])
        self.assertEqual(service.login("pw.operator", "Another-Password-2026!").username, "pw.operator")

    def test_t6_thresholds_are_validated_persisted_and_reloadable(self):
        from app.services import settings_service as module
        settings = SettingsService(self.db)
        settings.initialize_liveness_config()
        before = settings.load_liveness_config()
        generation = module.liveness_config_generation()
        with self.assertRaises(ValueError):
            settings.set_liveness_config({"turn_frames": "not-a-number"})
        with self.assertRaises(ValueError):
            settings.set_liveness_config({"unknown_threshold": 1})
        with self.assertRaises(Exception):
            settings.set_liveness_config({"blink_open_ear_min": before["blink_closed_ear_max"] - 0.1})
        self.assertEqual(settings.load_liveness_config(), before)
        self.assertEqual(module.liveness_config_generation(), generation)
        saved = settings.set_liveness_config({"turn_frames": 5, "timeout_seconds": 25.0})
        self.assertEqual((saved["turn_frames"], saved["timeout_seconds"]), (5, 25.0))
        self.assertEqual(settings.get_scope("global")["t6_turn_frames"], "5")
        self.assertEqual(settings.load_liveness_config()["turn_frames"], 5)
        self.assertGreater(module.liveness_config_generation(), generation)

    def test_settings_are_scoped_and_backup_does_not_overwrite(self):
        settings = SettingsService(self.db)
        settings.set_values("staff", {"notify_test": "true"})
        self.assertEqual(settings.get_scope("staff")["notify_test"], "true")
        target = Path(self.temp.name) / "backup.sqlite"
        settings.backup_to(target)
        self.assertTrue(target.exists())
        with self.assertRaises(FileExistsError): settings.backup_to(target)
        failed_target = Path(self.temp.name) / "failed.sqlite"
        invalid_source = Path(self.temp.name) / "source_directory.sqlite"
        invalid_source.mkdir()
        with self.assertRaises(Exception):
            settings.backup_to(failed_target, source_path=invalid_source)
        self.assertFalse(failed_target.exists())



class T5UiExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_csv_export_writes_filtered_rows_and_refuses_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "people.csv"
            parent = QWidget()
            with patch.object(dialogs.QFileDialog, "getSaveFileName", return_value=(str(target), "CSV UTF-8 (*.csv)")), \
                 patch.object(dialogs, "confirm") as confirm:
                self.assertTrue(dialogs.export_rows(parent, ["Code", "Name"], [("E-1", "Person")]))
            self.assertIn("Code,Name", target.read_text(encoding="utf-8-sig"))
            self.assertIn("E-1,Person", target.read_text(encoding="utf-8-sig"))
            target.write_text("preserve", encoding="utf-8")
            with patch.object(dialogs.QFileDialog, "getSaveFileName", return_value=(str(target), "CSV UTF-8 (*.csv)")), \
                 patch.object(dialogs, "confirm"):
                self.assertFalse(dialogs.export_rows(parent, ["Code"], [("E-2",)]))
            self.assertEqual(target.read_text(encoding="utf-8"), "preserve")
            partial = Path(temp) / "partial.csv"
            def failing_rows():
                yield ("first",)
                raise OSError("source read failed")
            with patch.object(dialogs.QFileDialog, "getSaveFileName", return_value=(str(partial), "CSV UTF-8 (*.csv)")), \
                 patch.object(dialogs, "confirm"):
                self.assertFalse(dialogs.export_rows(parent, ["Code"], failing_rows()))
            self.assertFalse(partial.exists())
            parent.close()

    def test_attendance_ui_filters_and_csv_export_use_same_service_filters(self):
        from PySide6.QtCore import QObject, Signal
        from app.ui.common import views as ui_views

        class PreviewController(QObject):
            face_analysis_ready = Signal(object, object)
            face_analysis_error = Signal(str)
            def __init__(self, *_args, **_kwargs): super().__init__()

        class HistoryService:
            calls = []
            def list_history(self, kind, **kwargs):
                self.calls.append((kind, kwargs.copy()))
                row = ("E-001", "Test Person", "Operations", "2026-09-25",
                       "2026-09-25T08:00:00Z", None, "late")
                return [row] if kwargs.get("offset", 0) == 0 else []
            def count_history(self, kind, **kwargs):
                self.calls.append((kind, kwargs.copy()))
                return 1

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "attendance.csv"
            service = HistoryService()
            with patch.object(ui_views, "CameraPreviewController", PreviewController), \
                 patch.object(ui_views, "user_chip", return_value=QWidget()), \
                 patch("app.services.attendance_service.AttendanceService", return_value=service):
                view = ui_views.AttendanceView("staff", "attendance")
                view._attendance_from_date.setText("2026-09-01")
                view._attendance_to_date.setText("2026-09-30")
                view._attendance_query.setText("E-001")
                view._attendance_status.setCurrentIndex(2)
                view._refresh_attendance_history()
                self.assertEqual(service.calls[-1][1]["from_date"], "2026-09-01")
                self.assertEqual(service.calls[-1][1]["to_date"], "2026-09-30")
                self.assertEqual(service.calls[-1][1]["query"], "E-001")
                self.assertEqual(service.calls[-1][1]["status"], "late")
                with patch.object(dialogs.QFileDialog, "getSaveFileName", return_value=(str(target), "CSV UTF-8 (*.csv)")), \
                     patch.object(dialogs, "confirm"):
                    view._export_attendance()
                output = target.read_text(encoding="utf-8-sig")
                self.assertIn("Test Person", output)
                self.assertIn("Đi muộn", output)
                self.assertEqual(service.calls[-1][1]["status"], "late")
                view.close()
                view.deleteLater()
                self.app.processEvents()


class T5T6UiWiringTests(unittest.TestCase):
    """Offscreen Qt checks that the new T5/T6 controls call the real services."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "ui.sqlite"
        initialize_database(self.db)
        con = connect(self.db)
        users = UserRepository(con)
        _, self.employee = users.create_employee_with_person(
            Person(None, "UI Employee"), Employee(None, 0, "U-001"))
        con.commit(); con.close()
        login_admin(self.db)
        self.patches = [
            patch("app.services.settings_service.SettingsService", lambda *_a, **_k: SettingsService(self.db)),
            patch("app.services.leave_service.LeaveService", lambda *_a, **_k: LeaveService(self.db)),
            patch("app.services.account_service.AccountService", lambda *_a, **_k: AccountService(self.db)),
        ]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in self.patches: item.stop()
        logout(); self.temp.cleanup()

    def test_settings_view_edits_and_saves_real_t6_thresholds(self):
        from app.ui.common import views as ui_views
        SettingsService(self.db).initialize_liveness_config()
        with patch.object(ui_views, "user_chip", return_value=QWidget()):
            view = ui_views.SettingsView("staff", "settings")
        try:
            self.assertEqual(len(view._t6_inputs), 10)
            self.assertEqual(view._t6_inputs["turn_frames"].text(),
                             str(SettingsService(self.db).load_liveness_config()["turn_frames"]))
            view._t6_inputs["turn_frames"].setText("7")
            view._save_t6()
            self.assertEqual(SettingsService(self.db).load_liveness_config()["turn_frames"], 7)
            self.assertIn("Đã lưu", view._t6_status.text())
            view._t6_inputs["turn_frames"].setText("không phải số")
            view._save_t6()
            self.assertIn("Không lưu được", view._t6_status.text())
            self.assertEqual(SettingsService(self.db).load_liveness_config()["turn_frames"], 7)
            self.assertIn(str(self.db.name), " ".join(value for _key, value in view._database_rows()))
        finally:
            view.close(); view.deleteLater(); self.app.processEvents()

    def test_leave_view_shows_review_actions_only_for_pending_rows(self):
        from app.ui.common import views as ui_views
        leave_id = LeaveService(self.db).create_employee_request(self.employee, {
            "leave_type": "personal", "start_date": "2026-09-25", "end_date": "2026-09-25",
            "reason": "UI request"})
        with patch.object(ui_views, "user_chip", return_value=QWidget()):
            view = ui_views.LeaveView("staff", "leave")
        try:
            reviewed = []
            with patch.object(ui_views.D, "leave_review",
                              side_effect=lambda *args, **kwargs: reviewed.append(args[:3])):
                actions = view._leave_actions(view._leave_rows_by_id[leave_id])
                self.assertEqual([item[0] for item in actions], ["Xem", "Duyệt", "Từ chối"])
                actions[1][2]()
                actions[2][2]()
            self.assertEqual(reviewed, [("staff", leave_id, "approved"), ("staff", leave_id, "rejected")])
            LeaveService(self.db).review("staff", leave_id, "approved")
            view._refresh_leaves()
            self.assertEqual([item[0] for item in view._leave_actions(view._leave_rows_by_id[leave_id])], ["Xem"])
        finally:
            view.close(); view.deleteLater(); self.app.processEvents()

    def test_accounts_view_locks_and_unlocks_through_the_service(self):
        from app.ui.common import views as ui_views
        with patch.object(ui_views, "user_chip", return_value=QWidget()):
            view = ui_views.AccountsView("staff", "accounts")
        try:
            with patch.object(ui_views.D, "confirm", return_value=True):
                view._set_account_status(
                    AccountService(self.db).directory()[0][0]["account_id"], "locked")
            self.assertEqual(AccountService(self.db).directory()[0][0]["account_status"], "locked")
        finally:
            view.close(); view.deleteLater(); self.app.processEvents()


class T5LoginFailClosedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_session_starts_and_logout_end_without_authorized_role(self):
        from app.ui import session
        from main import Flow
        session.logout()
        with self.assertRaises(PermissionError):
            session.role()
        flow = Flow()
        flow.after_login("admin")
        with self.assertRaises(PermissionError):
            session.role()

    def test_login_does_not_grant_role_from_nonempty_credentials_or_role_selector(self):
        from app.ui.login_view import LoginView
        from app.services.authentication_service import AuthenticationError
        view = LoginView()
        emitted = []
        view.logged_in.connect(emitted.append)
        view.u.setText("anything")
        view.p.setText("anything")
        view.role.setCurrentIndex(0)
        with patch("app.services.authentication_service.AuthenticationService.login",
                   side_effect=AuthenticationError("invalid")):
            view._submit()
        self.assertEqual(emitted, [])
        self.assertIn("không chính xác", view.err.text())
        view.close()


class T5PeoplePaginationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "ui.sqlite"
        initialize_database(self.db)
        con = connect(self.db)
        users = UserRepository(con)
        for index in range(101):
            person_id = users.create_person(Person(None, f"Person {index:03d}"))
            users.create_employee(Employee(None, person_id, f"E-{index:03d}"))
        con.commit()
        con.close()
        login_admin(self.db)
        from app.ui.common.views import PeopleView
        from app.services.employee_service import EmployeeService
        self.service = EmployeeService(self.db)
        self.patch = patch("app.services.employee_service.EmployeeService", return_value=self.service)
        self.patch.start()
        with patch("app.ui.common.views.user_chip", return_value=QWidget()):
            self.view = PeopleView("staff", "test_people")

    def tearDown(self):
        logout()
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()
        self.patch.stop()
        self.temp.cleanup()

    def test_next_page_and_search_reset_use_the_same_database_filter(self):
        self.assertEqual(self.view._people_table.rowCount(), 100)
        self.assertTrue(self.view._people_next.isEnabled())
        self.view._people_next.click()
        self.assertEqual(self.view._people_page, 1)
        self.assertEqual(self.view._people_table.rowCount(), 1)
        self.assertIn("2 / 2", self.view._people_page_label.text())
        self.view._people_search.setText("E-000")
        self.assertEqual(self.view._people_page, 0)
        self.assertEqual(self.view._people_table.rowCount(), 1)
        self.assertFalse(self.view._people_next.isEnabled())
        self.assertIn("1 / 1", self.view._people_page_label.text())


class T5DashboardRefreshUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dashboard_reloads_database_values_when_page_is_shown_again(self):
        from app.ui.common.views import DashboardView
        values = {
            "stats": [("Metric", 1)] * 4,
            "extra": [("Extra", 0)] * 3,
            "trend": [0] * 7,
            "trend_labels": ["-"] * 7,
            "bars": [],
            "group_title": "Groups",
            "activities": [],
        }
        service = unittest.mock.Mock()
        service.overview.return_value = values
        view = None
        try:
            with patch("app.services.dashboard_service.DashboardService", return_value=service), \
                 patch("app.ui.common.views.user_chip", return_value=QWidget()):
                view = DashboardView("staff", "test_dashboard")
                view.show()
                self.app.processEvents()
                view.hide()
                self.app.processEvents()
                view.show()
                self.app.processEvents()
            self.assertGreaterEqual(service.overview.call_count, 3)
        finally:
            if view is not None:
                view.close()
                view.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
