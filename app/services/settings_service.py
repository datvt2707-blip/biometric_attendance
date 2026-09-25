"""Scoped persistent application settings and non-destructive SQLite backups."""
from app.database.database import backup_database, connect, transaction
from app.database.repositories.settings_repository import SettingsRepository
from app.biometric.liveness.active_liveness import DEFAULT_LIVENESS_CONFIG

_LIVENESS_SETTING_KEYS = {
    "blink_closed_ear_max": "t6_blink_closed_ear_max",
    "blink_open_ear_min": "t6_blink_open_ear_min",
    "blink_closed_frames": "t6_blink_closed_frames",
    "blink_open_frames": "t6_blink_open_frames",
    "neutral_frames": "t6_neutral_frames",
    "turn_threshold": "t6_turn_threshold",
    "turn_frames": "t6_turn_frames",
    "timeout_seconds": "t6_timeout_seconds",
    "proof_seconds": "t6_proof_seconds",
    "max_observation_gap": "t6_max_observation_gap",
}

# Bumped whenever a T6 threshold is written so running workers can reload in place.
_LIVENESS_GENERATION = {"value": 0}


def liveness_config_generation():
    return _LIVENESS_GENERATION["value"]


class SettingsService:
    def __init__(self,database_path=None): self.database_path=database_path
    def get_scope(self,scope):
        from app.services.authorization_service import require_permission
        require_permission("settings.read")
        connection=connect(self.database_path)
        try: return {row["setting_key"]:row["setting_value"] for row in SettingsRepository(connection).list(scope)}
        finally: connection.close()
    def set_values(self,scope,values,updated_by_account_id=None):
        from app.services.authorization_service import require_permission
        require_permission("settings.write")
        connection=connect(self.database_path)
        try:
            repo=SettingsRepository(connection)
            with transaction(connection,immediate=True):
                for key,value in values.items(): repo.set(scope,key,value,updated_by_account_id)
            if any(str(key).startswith("t6_") for key in values):
                _LIVENESS_GENERATION["value"] += 1
        finally: connection.close()

    def set_liveness_config(self, values, *, updated_by_account_id=None):
        """Validate candidate T6 thresholds against the challenge, then persist them."""
        from app.services.authorization_service import require_permission
        require_permission("settings.write")
        candidate = dict(self.load_liveness_config())
        parsed = {}
        for field, raw in values.items():
            if field not in _LIVENESS_SETTING_KEYS:
                raise ValueError(f"Tham số liveness không hợp lệ: {field}.")
            try:
                parsed[field] = int(raw) if field.endswith("_frames") else float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Giá trị của {field} phải là số.") from exc
        candidate.update(parsed)
        from app.biometric.liveness.active_liveness import ActiveLivenessChallenge
        ActiveLivenessChallenge(candidate)  # raises on any invalid combination
        self.set_values("global", {_LIVENESS_SETTING_KEYS[field]: value for field, value in parsed.items()},
                        updated_by_account_id)
        return candidate

    def load_liveness_config(self):
        """Load current thresholds from system_settings; return documented defaults if absent."""
        connection = connect(self.database_path)
        try:
            repo = SettingsRepository(connection)
            config = dict(DEFAULT_LIVENESS_CONFIG)
            for field, key in _LIVENESS_SETTING_KEYS.items():
                row = repo.get("global", key)
                if row is not None:
                    raw = row["setting_value"]
                    config[field] = int(raw) if field.endswith("_frames") else float(raw)
            # Apply the same validation as the challenge before exposing values.
            from app.biometric.liveness.active_liveness import ActiveLivenessChallenge
            ActiveLivenessChallenge(config)
            return config
        finally:
            connection.close()

    def initialize_liveness_config(self, *, updated_by_account_id=None):
        """Persist provisional defaults only for missing T6 keys; preserve edits."""
        connection = connect(self.database_path)
        try:
            repo = SettingsRepository(connection)
            with transaction(connection, immediate=True):
                for field, key in _LIVENESS_SETTING_KEYS.items():
                    if repo.get("global", key) is None:
                        repo.set("global", key, DEFAULT_LIVENESS_CONFIG[field], updated_by_account_id)
        finally:
            connection.close()

    def backup_to(self, destination, *, source_path=None):
        """Create a new consistent SQLite backup; never replace an existing file."""
        from app.services.authorization_service import require_permission
        require_permission("settings.read")
        return backup_database(destination, source_path or self.database_path)
