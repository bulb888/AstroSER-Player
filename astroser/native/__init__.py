"""Native C acceleration module for AstroSER Player.

Provides ctypes wrappers around fast_ops.dll for:
- Centroid detection (search window tracking)
- Frame crop to RGB24
- Unsharp mask sharpening
"""

import ctypes
import numpy as np
from pathlib import Path
from ctypes import c_int, c_float, c_uint8, POINTER

# Load DLL
_dll_path = Path(__file__).parent / "fast_ops.dll"
_lib = None

try:
    _lib = ctypes.CDLL(str(_dll_path))

    # centroid_region
    _lib.centroid_region.argtypes = [
        POINTER(c_uint8), c_int, c_int, c_int, c_int,
        c_float, POINTER(c_float), POINTER(c_float),
    ]
    _lib.centroid_region.restype = None

    # detect_centroids_batch
    _lib.detect_centroids_batch.argtypes = [
        POINTER(POINTER(c_uint8)), c_int,
        c_int, c_int, c_int, c_int,
        c_float, c_int,
        POINTER(c_float), POINTER(c_float),
    ]
    _lib.detect_centroids_batch.restype = c_int

    # crop_to_rgb24
    _lib.crop_to_rgb24.argtypes = [
        POINTER(c_uint8), c_int, c_int, c_int, c_int, c_int,
        c_int, c_int, c_int, c_int,
        POINTER(c_uint8),
    ]
    _lib.crop_to_rgb24.restype = None

    # sharpen_rgb24
    _lib.sharpen_rgb24.argtypes = [
        POINTER(c_uint8), c_int, c_int, c_float,
    ]
    _lib.sharpen_rgb24.restype = None

except OSError:
    _lib = None


def is_available() -> bool:
    """Check if native module is loaded."""
    return _lib is not None


def centroid(frame: np.ndarray, threshold_pct: float = 85.0) -> tuple[float, float]:
    """Detect centroid of brightest object in a frame.

    Args:
        frame: 2D grayscale array (uint8 or uint16).
        threshold_pct: Brightness percentile threshold.

    Returns:
        (cx, cy) centroid in pixel coordinates.
    """
    if _lib is None:
        raise RuntimeError("Native module not available")

    if frame.ndim == 3:
        # Convert to grayscale (fast mean)
        frame = np.mean(frame, axis=2).astype(np.uint8 if frame.dtype == np.uint8 else np.uint16)

    frame = np.ascontiguousarray(frame)
    h, w = frame.shape
    bpp = 2 if frame.dtype == np.uint16 else 1
    stride = frame.strides[0]

    cx = c_float()
    cy = c_float()

    _lib.centroid_region(
        frame.ctypes.data_as(POINTER(c_uint8)),
        w, h, stride, bpp,
        c_float(threshold_pct),
        ctypes.byref(cx), ctypes.byref(cy),
    )

    return cx.value, cy.value


def detect_centroids_batch(
    frames: list[np.ndarray],
    threshold_pct: float = 85.0,
    search_radius: int = 0,
) -> list[tuple[float, float]]:
    """Detect centroids for multiple frames with search window tracking.

    Args:
        frames: List of 2D grayscale arrays (all same size).
        threshold_pct: Brightness percentile threshold.
        search_radius: Search window half-size. 0 = auto.

    Returns:
        List of (cx, cy) per frame.
    """
    if _lib is None:
        raise RuntimeError("Native module not available")

    n = len(frames)
    if n == 0:
        return []

    # Convert to grayscale contiguous arrays
    processed = []
    for f in frames:
        if f.ndim == 3:
            f = np.mean(f, axis=2).astype(np.uint8 if f.dtype == np.uint8 else np.uint16)
        processed.append(np.ascontiguousarray(f))

    h, w = processed[0].shape
    bpp = 2 if processed[0].dtype == np.uint16 else 1
    stride = processed[0].strides[0]

    # Build pointer array
    FramePtrArray = POINTER(c_uint8) * n
    frame_ptrs = FramePtrArray()
    for i, f in enumerate(processed):
        frame_ptrs[i] = f.ctypes.data_as(POINTER(c_uint8))

    out_cx = (c_float * n)()
    out_cy = (c_float * n)()

    _lib.detect_centroids_batch(
        ctypes.cast(frame_ptrs, POINTER(POINTER(c_uint8))),
        n, w, h, stride, bpp,
        c_float(threshold_pct), search_radius,
        out_cx, out_cy,
    )

    return [(out_cx[i], out_cy[i]) for i in range(n)]


def crop_to_rgb24(
    frame: np.ndarray,
    crop_x: int, crop_y: int, crop_w: int, crop_h: int,
) -> np.ndarray:
    """Crop frame and convert to RGB24 uint8.

    Args:
        frame: Source frame (mono or RGB, uint8 or uint16).
        crop_x, crop_y, crop_w, crop_h: Crop rectangle.

    Returns:
        RGB24 uint8 array of shape (crop_h, crop_w, 3).
    """
    if _lib is None:
        raise RuntimeError("Native module not available")

    frame = np.ascontiguousarray(frame)
    h, w = frame.shape[:2]
    channels = 1 if frame.ndim == 2 else frame.shape[2]
    bpp = 2 if frame.dtype == np.uint16 else 1
    stride = frame.strides[0]

    dst = np.empty((crop_h, crop_w, 3), dtype=np.uint8)

    _lib.crop_to_rgb24(
        frame.ctypes.data_as(POINTER(c_uint8)),
        w, h, stride, channels, bpp,
        crop_x, crop_y, crop_w, crop_h,
        dst.ctypes.data_as(POINTER(c_uint8)),
    )

    return dst


def sharpen_rgb24(image: np.ndarray, strength: float) -> np.ndarray:
    """Apply unsharp mask sharpening to RGB24 image.

    Args:
        image: RGB24 uint8 array (H, W, 3).
        strength: Sharpening strength (0 = off).

    Returns:
        Sharpened image (modified in-place and returned).
    """
    if _lib is None:
        raise RuntimeError("Native module not available")

    if strength <= 0:
        return image

    image = np.ascontiguousarray(image)
    h, w = image.shape[:2]

    _lib.sharpen_rgb24(
        image.ctypes.data_as(POINTER(c_uint8)),
        w, h, c_float(strength),
    )

    return image
