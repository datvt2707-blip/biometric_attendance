"""Persistence for local face image paths and serialized embeddings."""
from dataclasses import asdict
from pathlib import PurePosixPath, PureWindowsPath
from .base import BaseRepository


def _validate_relative_path(path: str) -> str:
    """Accept app-relative paths only; reject absolute paths and traversal."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("image_path must be a non-empty relative path")
    posix, windows = PurePosixPath(path), PureWindowsPath(path)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts or ".." in windows.parts:
        raise ValueError("image_path must stay inside the application-managed data directory")
    if "://" in path:
        raise ValueError("Internet URLs are not valid local image paths")
    return path.replace("\\", "/")


class FaceRepository(BaseRepository):
    def create_image(self, image):
        values = asdict(image); values.pop("image_id", None); values.pop("created_at", None)
        values["image_path"] = _validate_relative_path(values["image_path"])
        values["is_active"] = int(values["is_active"])
        return self._insert("face_images", values)
    def get_image(self, image_id): return self._get("face_images", "image_id", image_id)
    def list_images(self, person_id, active_only=True):
        return self._list("face_images", "person_id = ? AND (? = 0 OR is_active = 1)", (person_id, int(active_only)), "created_at DESC")
    def update_image(self, image_id, changes):
        changes = dict(changes)
        if "image_path" in changes: changes["image_path"] = _validate_relative_path(changes["image_path"])
        if "is_active" in changes: changes["is_active"] = int(changes["is_active"])
        return self._update("face_images", "image_id", image_id, changes, {"person_id", "image_path", "capture_label", "is_active"})

    def create_embedding(self, embedding):
        values = asdict(embedding); values.pop("embedding_id", None); values.pop("created_at", None)
        values["is_active"] = int(values["is_active"])
        return self._insert("face_embeddings", values)
    def get_embedding(self, embedding_id): return self._get("face_embeddings", "embedding_id", embedding_id)
    def list_embeddings(self, person_id, active_only=True):
        return self._list("face_embeddings", "person_id = ? AND (? = 0 OR is_active = 1)", (person_id, int(active_only)), "created_at DESC")
    def deactivate_embedding(self, embedding_id):
        return self._update("face_embeddings", "embedding_id", embedding_id, {"is_active": 0}, {"is_active"})
