"""Class roster and class-management use cases."""
from datetime import date
from app.database.database import connect, transaction
from app.database.models.class_model import Class
from app.database.repositories.class_repository import ClassRepository
from app.database.repositories.attendance_repository import AttendanceRepository
from app.database.repositories.user_repository import UserRepository
from app.services.authorization_service import require_permission

class ClassService:
    def __init__(self, database_path=None): self.database_path = database_path
    def list_classes(self, status=None):
        require_permission("class.read")
        connection=connect(self.database_path)
        try:
            classes,users=ClassRepository(connection),UserRepository(connection)
            output=[]
            today=date.today().isoformat()
            for row in classes.list_classes(status):
                active=[]
                for enrollment in classes.list_enrollments(class_id=row["class_id"],active_only=True):
                    if enrollment["start_date"] > today or (enrollment["end_date"] and enrollment["end_date"] < today):
                        continue
                    student=users.get_student(enrollment["student_id"])
                    person=users.get_person(student["person_id"]) if student else None
                    if student and student["student_status"] == "active" and person and bool(person["is_active"]):
                        active.append(student["student_id"])
                output.append({**dict(row),"active_students":len(active)})
            return output
        finally: connection.close()
    def save(self, values, class_id=None):
        require_permission("class.write")
        values=dict(values); name=(values.get("class_name") or "").strip(); year=(values.get("academic_year") or "").strip()
        if not name or not year: raise ValueError("Tên lớp và năm học là bắt buộc.")
        if values.get("capacity") is not None:
            try: values["capacity"]=int(values["capacity"])
            except (TypeError, ValueError) as exc: raise ValueError("Sĩ số tối đa phải là số nguyên dương.") from exc
            if values["capacity"] <= 0: raise ValueError("Sĩ số tối đa phải là số nguyên dương.")
        if values.get("start_date"):
            try:
                parsed=date.fromisoformat(str(values["start_date"]))
                if parsed.isoformat()!=values["start_date"]: raise ValueError
            except ValueError as exc: raise ValueError("Ngày khai giảng phải có định dạng YYYY-MM-DD.") from exc
        if values.get("class_status","active") not in ("active","completed","cancelled","inactive"):
            raise ValueError("Trạng thái lớp không hợp lệ.")
        connection=connect(self.database_path)
        try:
            repo=ClassRepository(connection)
            with transaction(connection,immediate=True):
                duplicate=[r for r in repo.list_classes() if r["class_name"]==name and r["academic_year"]==year and r["class_id"]!=class_id]
                if duplicate: raise ValueError("Lớp cùng tên và năm học đã tồn tại.")
                record=Class(class_id=class_id,class_name=name,academic_year=year,
                    teacher_name=values.get("teacher_name"),room=values.get("room"),
                    schedule_text=values.get("schedule_text"),time_text=values.get("time_text"),
                    capacity=values.get("capacity"),start_date=values.get("start_date"),
                    notes=values.get("notes"),class_status=values.get("class_status","active"))
                if class_id is None: return repo.create_class(record)
                if not repo.update_class(class_id,{k:v for k,v in values.items() if k in {"class_name","academic_year","teacher_name","room","schedule_text","time_text","capacity","start_date","notes","class_status"}}):
                    raise ValueError("Không tìm thấy lớp cần sửa.")
                return int(class_id)
        finally: connection.close()
    def enrollable_students(self,class_id):
        """Active students without an active enrollment in this class."""
        require_permission("class.read")
        connection=connect(self.database_path)
        try:
            classes,users=ClassRepository(connection),UserRepository(connection)
            if classes.get_class(class_id) is None: raise ValueError("Không tìm thấy lớp.")
            enrolled={int(row["student_id"]) for row in classes.list_enrollments(class_id=class_id,active_only=True)}
            output=[]
            for student in users.list_students(status="active"):
                if int(student["student_id"]) in enrolled: continue
                person=users.get_person(student["person_id"])
                if person is None or not bool(person["is_active"]): continue
                output.append({"student_id":int(student["student_id"]),"student_code":student["student_code"],
                               "display":f"{student['student_code']} · {person['full_name']}"})
            return output
        finally: connection.close()
    def enrolled_students(self,class_id):
        """Students holding an active enrollment in this class."""
        require_permission("class.read")
        connection=connect(self.database_path)
        try:
            classes,users=ClassRepository(connection),UserRepository(connection)
            if classes.get_class(class_id) is None: raise ValueError("Không tìm thấy lớp.")
            output=[]
            for enrollment in classes.list_enrollments(class_id=class_id,active_only=True):
                student=users.get_student(enrollment["student_id"])
                person=users.get_person(student["person_id"]) if student else None
                if student is None or person is None: continue
                output.append({"student_id":int(student["student_id"]),"student_code":student["student_code"],
                               "display":f"{student['student_code']} · {person['full_name']}",
                               "start_date":enrollment["start_date"]})
            return output
        finally: connection.close()
    def enroll_student(self,class_id,student_id,start_date=None):
        """Add one active enrollment; capacity is enforced only when the class defines it."""
        require_permission("class.write")
        day=start_date or date.today().isoformat()
        try:
            if date.fromisoformat(day).isoformat()!=day: raise ValueError
        except (TypeError,ValueError) as exc: raise ValueError("Ngày bắt đầu phải có định dạng YYYY-MM-DD.") from exc
        connection=connect(self.database_path)
        try:
            classes,users=ClassRepository(connection),UserRepository(connection)
            with transaction(connection,immediate=True):
                class_row=classes.get_class(class_id)
                if class_row is None: raise ValueError("Không tìm thấy lớp.")
                if class_row["class_status"]!="active": raise ValueError("Chỉ thêm học viên vào lớp đang hoạt động.")
                student=users.get_student(student_id)
                if student is None or student["student_status"]!="active":
                    raise ValueError("Học viên không tồn tại hoặc không hoạt động.")
                active=classes.list_enrollments(class_id=class_id,active_only=True)
                if any(int(row["student_id"])==int(student_id) for row in active):
                    raise ValueError("Học viên đã có đăng ký đang hoạt động trong lớp này.")
                capacity=class_row["capacity"]
                if capacity is not None and len(active)>=int(capacity):
                    raise ValueError(f"Lớp đã đủ sĩ số tối đa ({int(capacity)}).")
                from app.database.models.class_model import Enrollment
                return classes.create_enrollment(Enrollment(enrollment_id=None,student_id=int(student_id),
                    class_id=int(class_id),start_date=day,enrollment_status="active"))
        finally: connection.close()
    def withdraw_student(self,class_id,student_id,end_date=None):
        """Close the active enrollment instead of deleting historical rows."""
        require_permission("class.write")
        day=end_date or date.today().isoformat()
        try:
            if date.fromisoformat(day).isoformat()!=day: raise ValueError
        except (TypeError,ValueError) as exc: raise ValueError("Ngày kết thúc phải có định dạng YYYY-MM-DD.") from exc
        connection=connect(self.database_path)
        try:
            classes=ClassRepository(connection)
            with transaction(connection,immediate=True):
                active=[row for row in classes.list_enrollments(class_id=class_id,active_only=True)
                        if int(row["student_id"])==int(student_id)]
                if not active: raise ValueError("Học viên không có đăng ký đang hoạt động trong lớp này.")
                row=active[0]
                if row["start_date"]>day: raise ValueError("Ngày kết thúc không được trước ngày bắt đầu đăng ký.")
                if not classes.update_enrollment(int(row["enrollment_id"]),
                        {"end_date":day,"enrollment_status":"withdrawn"}):
                    raise ValueError("Không cập nhật được đăng ký.")
                return int(row["enrollment_id"])
        finally: connection.close()
    def roster(self,class_id,attendance_date=None):
        require_permission("class.read")
        day=attendance_date or date.today().isoformat()
        try:
            if date.fromisoformat(day).isoformat()!=day: raise ValueError
        except (TypeError,ValueError) as exc: raise ValueError("Ngày roster phải có định dạng YYYY-MM-DD.") from exc
        connection=connect(self.database_path)
        try:
            repo,users,attendance=ClassRepository(connection),UserRepository(connection),AttendanceRepository(connection)
            if repo.get_class(class_id) is None: raise ValueError("Không tìm thấy lớp.")
            output=[]
            for enrollment in repo.list_enrollments(class_id=class_id):
                if enrollment["start_date"] > day or (enrollment["end_date"] and enrollment["end_date"] < day): continue
                student=users.get_student(enrollment["student_id"])
                person=users.get_person(student["person_id"]) if student else None
                if person is None: continue
                att=attendance.get_student_attendance_for_day(student["student_id"], class_id, day)
                output.append((student["student_code"],person["full_name"],att["status"] if att else "not_recorded",att["check_in_at"] if att else None,att["note"] if att else None))
            return output
        finally: connection.close()
