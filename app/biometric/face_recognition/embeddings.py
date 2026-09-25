"""Embedding extraction from real InsightFace recognition inference results."""
from __future__ import annotations

import numpy as np


def embedding_from_face(face, *, normalize=True) -> np.ndarray:
    """Return the recognition vector attached by FaceAnalysis.get to a detected face."""
    value = getattr(face, "normed_embedding", None)
    if value is None:
        value = getattr(face, "embedding", None)
    if value is None:
        raise ValueError("FaceAnalysis result has no recognition embedding")
    vector = np.asarray(value, dtype=np.float32)
    if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError("InsightFace returned an invalid embedding")
    if normalize:
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError("InsightFace returned a zero or invalid embedding norm")
        vector = vector / norm
    return np.ascontiguousarray(vector, dtype=np.float32)


def embeddings_from_faces(faces, *, normalize=True):
    """Extract real model vectors from FaceAnalysis results; no synthetic fallback."""
    return tuple(embedding_from_face(face, normalize=normalize) for face in faces)
