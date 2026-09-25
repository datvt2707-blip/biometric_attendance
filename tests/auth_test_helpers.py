"""Create an authenticated Admin context for service tests over isolated SQLite files."""
from app.services.authentication_service import AuthenticationService
from app.services.initial_account_bootstrap import bootstrap_initial_accounts
from app.ui import session


PASSWORDS = {
    "ADMIN": "Test-Only-Admin-Password-2026!",
    "HR": "Test-Only-HR-Password-2026!",
    "STUDENT_SUPPORT": "Test-Only-Student-Password-2026!",
}


def login_admin(database_path):
    session.logout()
    bootstrap_initial_accounts(PASSWORDS, database_path)
    identity = AuthenticationService(database_path).login("admin", PASSWORDS["ADMIN"])
    session.establish(identity)


def logout():
    session.logout()
