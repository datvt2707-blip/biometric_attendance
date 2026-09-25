"""Dashboard query facade."""
from datetime import date, timedelta
from app.database.database import connect
from app.database.repositories.dashboard_repository import DashboardRepository
from app.services.authorization_service import require_permission

class DashboardService:
    def __init__(self, database_path=None): self.database_path = database_path
    def overview(self, block, today=None):
        require_permission("dashboard.staff.read" if block == "staff" else "dashboard.student.read")
        # Attendance work_date follows the workstation's local calendar day.
        today = today or date.today()
        dates = [today - timedelta(days=i) for i in range(6,-1,-1)]
        connection = connect(self.database_path)
        try:
            return DashboardRepository(connection).overview(
                block, today.isoformat(), [item.isoformat() for item in dates]
            )
        finally: connection.close()
