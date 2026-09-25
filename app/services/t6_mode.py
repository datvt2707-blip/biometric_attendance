"""Explicit opt-in development policy for testing recognition-to-attendance."""
import os


def development_attendance_without_liveness_enabled():
    """Bypass only MediaPipe stage when APP_ENV is explicitly dev/test and opted in."""
    environment = os.environ.get("APP_ENV", "production").strip().lower()
    flag = os.environ.get("BIOMETRIC_ATTENDANCE_T6_DEV_MODE", "").strip().lower()
    return environment in {"development", "test"} and flag in {"1", "true", "yes"}
