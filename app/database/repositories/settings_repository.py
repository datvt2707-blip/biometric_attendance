"""Persistent key/value settings scoped to the application area."""
from .base import BaseRepository


class SettingsRepository(BaseRepository):
    def get(self, scope, key):
        return self.connection.execute("SELECT * FROM system_settings WHERE scope = ? AND setting_key = ?", (scope, key)).fetchone()
    def list(self, scope=None):
        return self._list("system_settings", "scope = ?" if scope else "1 = 1", (scope,) if scope else (), "scope, setting_key")
    def set(self, scope, key, value, updated_by_account_id=None):
        self.connection.execute(
            """INSERT INTO system_settings(scope, setting_key, setting_value, updated_by_account_id)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(scope, setting_key) DO UPDATE SET
                 setting_value = excluded.setting_value,
                 updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                 updated_by_account_id = excluded.updated_by_account_id""",
            (scope, key, str(value), updated_by_account_id),
        )
    def delete(self, scope, key):
        return self.connection.execute("DELETE FROM system_settings WHERE scope = ? AND setting_key = ?", (scope, key)).rowcount > 0
