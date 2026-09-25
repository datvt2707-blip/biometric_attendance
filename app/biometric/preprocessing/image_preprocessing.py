"""Configurable OpenCV preprocessing; no model-specific defaults are assumed."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class PreprocessingConfig:
    output_size: Optional[tuple[int, int]] = None  # require an explicit model size before resizing
    grayscale: bool = False
    equalization: str = "none"  # none | histogram | clahe
    color_order: str = "bgr"  # OpenCV capture order; model callers must choose if different
    normalize: bool = False
    scale: float = 1.0 / 255.0
    mean: Optional[tuple[float, ...]] = None
    std: Optional[tuple[float, ...]] = None
    crop_padding: float = 0.0
    clahe_clip_limit: float = 2.0
    clahe_grid_size: tuple[int, int] = (8, 8)


def crop_face(image: np.ndarray, bbox: Sequence[float], *, padding: float = 0.0) -> np.ndarray:
    """Return a clipped copy of a face crop; bbox uses x1,y1,x2,y2 pixel coords."""
    _validate_image(image)
    if len(bbox) != 4:
        raise ValueError("bbox must be (x1, y1, x2, y2)")
    height, width = image.shape[:2]
    x1, y1, x2, y2 = map(float, bbox)
    if x2 <= x1 or y2 <= y1 or padding < 0:
        raise ValueError("bbox or padding is invalid")
    pad_x, pad_y = (x2 - x1) * padding, (y2 - y1) * padding
    left = max(0, int(np.floor(x1 - pad_x)))
    top = max(0, int(np.floor(y1 - pad_y)))
    right = min(width, int(np.ceil(x2 + pad_x)))
    bottom = min(height, int(np.ceil(y2 + pad_y)))
    if right <= left or bottom <= top:
        raise ValueError("bbox does not intersect the image")
    return image[top:bottom, left:right].copy()


def align_face(image: np.ndarray, source_points: Sequence[Sequence[float]],
               target_points: Sequence[Sequence[float]], *, output_size) -> np.ndarray:
    """Align landmarks to caller-provided target points; no ArcFace template assumed."""
    _validate_image(image)
    source = np.asarray(source_points, dtype=np.float32)
    target = np.asarray(target_points, dtype=np.float32)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 2 or source.shape[0] < 3:
        raise ValueError("source_points and target_points must be matching Nx2 arrays with N >= 3")
    matrix, _ = cv2.estimateAffinePartial2D(source, target, method=cv2.LMEDS)
    if matrix is None:
        raise ValueError("Could not estimate face alignment transform")
    width, height = _size(output_size)
    return cv2.warpAffine(image.copy(), matrix, (width, height), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def preprocess_face(image: np.ndarray, bbox: Optional[Sequence[float]] = None, *,
                    config: PreprocessingConfig = PreprocessingConfig(),
                    source_points=None, target_points=None) -> np.ndarray:
    """Create a model-input candidate while leaving the captured image untouched.

    Model input order and normalization are explicit settings. Equalization is
    opt-in because it changes image statistics and can harm some recognition models.
    """
    _validate_image(image)
    if config.equalization not in {"none", "histogram", "clahe"}:
        raise ValueError("equalization must be none, histogram, or clahe")
    if config.color_order not in {"rgb", "bgr", "gray"}:
        raise ValueError("color_order must be rgb, bgr, or gray")
    if source_points is not None or target_points is not None:
        if source_points is None or target_points is None:
            raise ValueError("source_points and target_points must be provided together")
        if config.output_size is None:
            raise ValueError("output_size must match the actual model when aligning a face")
        width, height = _size(config.output_size)
        face = align_face(image, source_points, target_points, output_size=(width, height))
    else:
        crop_box = bbox if bbox is not None else (0, 0, image.shape[1], image.shape[0])
        face = crop_face(image, crop_box, padding=config.crop_padding)
        if config.output_size is not None:
            width, height = _size(config.output_size)
            face = cv2.resize(face, (width, height), interpolation=cv2.INTER_AREA if face.shape[1] > width else cv2.INTER_LINEAR)

    if config.grayscale or config.color_order == "gray":
        if face.ndim == 3:
            face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        if config.equalization == "histogram":
            face = cv2.equalizeHist(face)
        elif config.equalization == "clahe":
            face = _clahe(config).apply(face)
    elif config.equalization != "none":
        # Equalize luminance only, preserving chroma as much as OpenCV's
        # YCrCb/LAB transforms allow.
        if config.equalization == "histogram":
            ycrcb = cv2.cvtColor(face, cv2.COLOR_BGR2YCrCb)
            ycrcb[:, :, 0] = cv2.equalizeHist(ycrcb[:, :, 0])
            face = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
        else:
            lab = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
            lab[:, :, 0] = _clahe(config).apply(lab[:, :, 0])
            face = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if config.color_order == "gray":
        if face.ndim == 3:
            face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    elif config.color_order == "rgb" and face.ndim == 3:
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)

    if config.normalize:
        face = face.astype(np.float32) * float(config.scale)
        if config.mean is not None:
            face = face - _channel_values(config.mean, face)
        if config.std is not None:
            std = _channel_values(config.std, face)
            if np.any(std == 0):
                raise ValueError("std values must be non-zero")
            face = face / std
        return np.ascontiguousarray(face, dtype=np.float32)
    return np.ascontiguousarray(face)


def _validate_image(image):
    if not isinstance(image, np.ndarray) or image.size == 0 or image.ndim not in (2, 3):
        raise ValueError("image must be a non-empty grayscale or color NumPy array")
    if image.ndim == 3 and image.shape[2] not in (3, 4):
        raise ValueError("color image must have 3 (BGR) or 4 (BGRA) channels")


def _size(value):
    if len(value) != 2 or int(value[0]) <= 0 or int(value[1]) <= 0:
        raise ValueError("output_size must contain positive (width, height)")
    return int(value[0]), int(value[1])


def _clahe(config):
    return cv2.createCLAHE(clipLimit=config.clahe_clip_limit, tileGridSize=config.clahe_grid_size)


def _channel_values(values, image):
    values = np.asarray(values, dtype=np.float32)
    channels = image.shape[2] if image.ndim == 3 else 1
    if values.ndim == 0:
        return values
    if values.size != channels:
        raise ValueError(f"normalization expects {channels} mean/std value(s)")
    return values.reshape((1, 1, channels)) if image.ndim == 3 else values.reshape(())
