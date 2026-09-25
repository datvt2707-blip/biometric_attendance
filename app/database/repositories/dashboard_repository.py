"""Read-only aggregations for existing dashboard widgets."""
class DashboardRepository:
    def __init__(self, connection): self.connection = connection

    def overview(self, block, today, days):
        if block == "staff":
            total = self.connection.execute("SELECT count(*) FROM employees").fetchone()[0]
            active = self.connection.execute("SELECT count(*) FROM employees WHERE employment_status='active'").fetchone()[0]
            enrolled = self.connection.execute("SELECT count(*) FROM employees e JOIN people p USING(person_id) WHERE EXISTS(SELECT 1 FROM face_embeddings f WHERE f.person_id=p.person_id AND f.is_active=1)").fetchone()[0]
            present = self.connection.execute("SELECT count(*) FROM employee_attendance WHERE work_date=? AND check_in_at IS NOT NULL", (today,)).fetchone()[0]
            late = self.connection.execute("SELECT count(*) FROM employee_attendance WHERE work_date=? AND status='late'", (today,)).fetchone()[0]
            absent = self.connection.execute("SELECT count(*) FROM employee_attendance WHERE work_date=? AND status='absent'", (today,)).fetchone()[0]
            checked_out = self.connection.execute("SELECT count(*) FROM employee_attendance WHERE work_date=? AND check_out_at IS NOT NULL", (today,)).fetchone()[0]
            groups = self.connection.execute("SELECT COALESCE(d.name,'Chưa phân phòng ban'),count(*) FROM employees e LEFT JOIN departments d USING(department_id) GROUP BY d.name ORDER BY count(*) DESC,d.name").fetchall()
            trend = self.connection.execute("SELECT work_date,count(*) FROM employee_attendance WHERE work_date BETWEEN ? AND ? AND check_in_at IS NOT NULL GROUP BY work_date", (days[0], days[-1])).fetchall()
            recent = self.connection.execute("SELECT p.full_name,e.employee_code,a.work_date,a.check_in_at,a.check_out_at,a.status FROM employee_attendance a JOIN employees e USING(employee_id) JOIN people p USING(person_id) ORDER BY a.work_date DESC,a.check_in_at DESC LIMIT 6").fetchall()
            stats = [("Tổng nhân viên",total),("Đã check-in hôm nay",present),("Đi muộn ghi nhận",late),("Vắng ghi nhận",absent)]
            extra = [("Nhân viên hoạt động",active),("Có embedding",enrolled),("Đã check-out hôm nay",checked_out)]
            group_title = "Tỷ trọng theo phòng ban"
        else:
            total = self.connection.execute("SELECT count(*) FROM students").fetchone()[0]
            active = self.connection.execute("SELECT count(*) FROM students WHERE student_status='active'").fetchone()[0]
            enrolled = self.connection.execute("SELECT count(*) FROM students s JOIN people p USING(person_id) WHERE EXISTS(SELECT 1 FROM face_embeddings f WHERE f.person_id=p.person_id AND f.is_active=1)").fetchone()[0]
            present = self.connection.execute("SELECT count(DISTINCT student_id) FROM student_attendance WHERE attendance_date=? AND status IN ('present','late')", (today,)).fetchone()[0]
            late = self.connection.execute("SELECT count(*) FROM student_attendance WHERE attendance_date=? AND status='late'", (today,)).fetchone()[0]
            absent = self.connection.execute("SELECT count(*) FROM student_attendance WHERE attendance_date=? AND status='absent'", (today,)).fetchone()[0]
            checked_out = 0
            groups = self.connection.execute("SELECT c.class_name,count(DISTINCT en.student_id) FROM classes c LEFT JOIN enrollments en ON en.class_id=c.class_id AND en.enrollment_status='active' WHERE c.class_status='active' GROUP BY c.class_id ORDER BY c.class_name").fetchall()
            trend = self.connection.execute("SELECT attendance_date,count(*) FROM student_attendance WHERE attendance_date BETWEEN ? AND ? AND status IN ('present','late') GROUP BY attendance_date", (days[0], days[-1])).fetchall()
            recent = self.connection.execute("SELECT p.full_name,s.student_code,a.attendance_date,a.check_in_at,NULL,a.status FROM student_attendance a JOIN students s USING(student_id) JOIN people p USING(person_id) ORDER BY a.attendance_date DESC,a.check_in_at DESC LIMIT 6").fetchall()
            stats = [("Tổng học viên",total),("Đã điểm danh hôm nay",present),("Đi muộn ghi nhận",late),("Vắng ghi nhận",absent)]
            extra = [("Học viên hoạt động",active),("Có embedding",enrolled),("Đã điểm danh hôm nay",present)]
            group_title = "Tỷ trọng học viên theo lớp"
        trend_map = {row[0]: int(row[1]) for row in trend}
        max_group = max((int(row[1]) for row in groups), default=0)
        bars = [(row[0], round(100 * int(row[1]) / max_group) if max_group else 0, "info") for row in groups[:6]]
        activities = []
        for name, code, work_date, check_in, check_out, state in recent:
            moment = check_out or check_in or "?"
            activities.append(("".join(x[0] for x in name.split())[:2], name,
                               f"{code} · {work_date} · {moment}", state))
        return {"stats": stats, "extra": extra, "trend": [trend_map.get(day,0) for day in days],
                "trend_labels": [day[5:] for day in days], "bars": bars,
                "group_title": group_title, "activities": activities}
