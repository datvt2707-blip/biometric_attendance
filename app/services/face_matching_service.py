"""Read-only cosine matching against registered employee/student face samples."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Optional

import numpy as np

from app.database.database import DEFAULT_DATABASE_PATH, connect
from app.database.repositories.face_repository import FaceRepository
from app.database.repositories.user_repository import UserRepository


DEFAULT_MATCH_THRESHOLD = 0.60  # Provisional; must be calibrated on representative data.
DEFAULT_AMBIGUITY_MARGIN = 0.03  # Provisional safety margin between different identities.


@dataclass(frozen=True)
class FaceMatchResult:
    status: str
    person_id: Optional[int] = None
    person_type: Optional[str] = None
    display_name: Optional[str] = None
    person_code: Optional[str] = None
    similarity: Optional[float] = None
    samples_compared: int = 0
    reason: str = ""


class FaceMatchingService:
    """Compare an inferred vector to every valid sample, grouped by person ID.

    Scores are cosine similarities, not probabilities. The per-person score is
    the maximum across that person's stored samples to allow pose variation.
    """

    def __init__(self, database_path=None, *, threshold=DEFAULT_MATCH_THRESHOLD,
                 ambiguity_margin=DEFAULT_AMBIGUITY_MARGIN):
        self.database_path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
        self.threshold = float(threshold)
        self.ambiguity_margin = float(ambiguity_margin)
        if not -1.0 <= self.threshold <= 1.0:
            raise ValueError("cosine threshold must be between -1 and 1")
        if self.ambiguity_margin < 0:
            raise ValueError("ambiguity margin cannot be negative")

    def match(self, embedding, *, model_name="", model_version="") -> FaceMatchResult:
        query = self._normalize(embedding)
        if query is None:
            return FaceMatchResult("invalid_embedding", reason="embedding_empty_nonfinite_or_zero")
        connection = None
        try:
            connection = connect(self.database_path)
            users, faces = UserRepository(connection), FaceRepository(connection)
            candidates = {}
            for person_type, profiles, code_key in (
                ("employee", users.list_employees(status="active"), "employee_code"),
                ("student", users.list_students(status="active"), "student_code"),
            ):
                for profile in profiles:
                    person_id = int(profile["person_id"])
                    person = users.get_person(person_id)
                    if person is None or not bool(person["is_active"]):
                        continue
                    scores = []
                    for stored in faces.list_embeddings(person_id, active_only=True):
                        if model_name and stored["model_name"] != model_name:
                            continue
                        if model_version and stored["model_version"] != model_version:
                            continue
                        vector = self._decode(stored)
                        if vector is None or vector.shape != query.shape:
                            continue
                        scores.append(float(np.dot(query, vector)))
                    if scores:
                        candidate = {
                            "person_id": person_id,
                            "person_type": person_type,
                            "display_name": person["full_name"],
                            "person_code": profile[code_key],
                            "similarity": max(scores),
                            "samples_compared": len(scores),
                        }
                        old = candidates.get(person_id)
                        if old is None or candidate["similarity"] > old["similarity"]:
                            candidates[person_id] = candidate
        except Exception as exc:
            return FaceMatchResult("error", reason=f"matching_database_error: {exc}")
        finally:
            if connection is not None:
                connection.close()

        ranked = sorted(candidates.values(), key=lambda item: item["similarity"], reverse=True)
        if not ranked:
            return FaceMatchResult("no_match", reason="no_compatible_registered_samples")
        best = ranked[0]
        if best["similarity"] < self.threshold:
            return FaceMatchResult("no_match", similarity=best["similarity"],
                                   samples_compared=best["samples_compared"],
                                   reason="best_similarity_below_provisional_threshold")
        if len(ranked) > 1 and best["similarity"] - ranked[1]["similarity"] < self.ambiguity_margin:
            return FaceMatchResult("ambiguous", similarity=best["similarity"],
                                   reason="multiple_identities_with_similar_scores")
        return FaceMatchResult("matched", **best, reason="best_person_sample_cosine_meets_threshold")

    @staticmethod
    def _normalize(value):
        try:
            vector = np.asarray(value, dtype=np.float32)
        except (TypeError, ValueError):
            return None
        if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
            return None
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 0:
            return None
        return np.ascontiguousarray(vector / norm, dtype=np.float32)

    @classmethod
    def _decode(cls, row):
        try:
            dimension = int(row["dimension"])
            dtype = np.dtype(row["dtype"])
            if dimension <= 0 or dtype not in (np.dtype("float32"), np.dtype("float64")):
                return None
            data = bytes(row["vector_data"])
            if len(data) != dimension * dtype.itemsize:
                return None
            vector = np.frombuffer(data, dtype=dtype)
            if vector.ndim != 1 or vector.size != dimension or not np.isfinite(vector).all():
                return None
            normalized = cls._normalize(vector)
            return normalized
        except (TypeError, ValueError, OverflowError, BufferError):
            return None
