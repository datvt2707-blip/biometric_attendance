"""Face image metadata and serialized recognition embedding records."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FaceImage:
    image_id: Optional[int]
    person_id: int
    image_path: str
    capture_label: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool = True


@dataclass
class FaceEmbedding:
    embedding_id: Optional[int]
    person_id: int
    model_name: str
    model_version: str
    dimension: int
    dtype: str
    vector_data: bytes
    image_id: Optional[int] = None
    created_at: Optional[str] = None
    is_active: bool = True
