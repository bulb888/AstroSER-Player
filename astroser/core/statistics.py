"""Frame statistics and quality metrics."""

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class FrameStats:
    """Statistics for a frame or ROI region."""
    min_val: float
    max_val: float
    mean_val: float
    std_val: float
    sharpness: float


def compute_stats(frame: np.ndarray,
                  roi: Optional[tuple[int, int, int, int]] = None,
                  fast: bool = False) -> FrameStats:
    """Compute statistics for a frame or ROI.

    Args:
        frame: 2D or 3D array (H, W) or (H, W, 3)
        roi: Optional (x, y, width, height) tuple
        fast: If True, subsample for speed (use during playback)
    """
    if roi is not None:
        x, y, w, h = roi
        frame = frame[y:y+h, x:x+w]

    # Subsample for fast mode
    if fast and frame.size > 500000:
        step = 4
        if frame.ndim == 3:
            sample = frame[::step, ::step, :]
        else:
            sample = frame[::step, ::step]
    else:
        sample = frame

    # Convert to grayscale for sharpness
    if sample.ndim == 3:
        gray = np.mean(sample, axis=2).astype(sample.dtype)
    else:
        gray = sample

    gray_f = gray.astype(np.float64)

    return FrameStats(
        min_val=float(np.min(sample)),
        max_val=float(np.max(sample)),
        mean_val=float(np.mean(sample)),
        std_val=float(np.std(sample)),
        sharpness=compute_sharpness(gray_f),
    )


def compute_sharpness(gray: np.ndarray) -> float:
    """Compute sharpness using variance of Laplacian.

    Higher values indicate sharper images.
    """
    # 3x3 Laplacian kernel applied manually with NumPy
    # kernel: [[0, 1, 0], [1, -4, 1], [0, 1, 0]]
    padded = np.pad(gray, 1, mode='reflect')
    laplacian = (
        padded[:-2, 1:-1] +   # top
        padded[2:, 1:-1] +    # bottom
        padded[1:-1, :-2] +   # left
        padded[1:-1, 2:] -    # right
        4 * padded[1:-1, 1:-1]  # center
    )
    return float(np.var(laplacian))


def compute_histogram(frame: np.ndarray, bins: int = 256) -> np.ndarray:
    """Compute histogram of frame data.

    Args:
        frame: image array (any shape)
        bins: number of bins

    Returns:
        1D array of histogram counts
    """
    flat = frame.ravel().astype(np.float64)
    hist, _ = np.histogram(flat, bins=bins)
    return hist
