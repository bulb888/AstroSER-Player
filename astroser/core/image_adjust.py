"""Image adjustment functions for brightness, contrast, gamma, and histogram stretch."""

import numpy as np


def adjust_brightness_contrast(image: np.ndarray, brightness: float = 0.0,
                                contrast: float = 1.0) -> np.ndarray:
    """Apply brightness and contrast adjustment.

    Args:
        image: float32 array in [0, 1] range
        brightness: value to add (-1.0 to 1.0)
        contrast: multiplier (0.0 to 3.0, 1.0 = no change)
    """
    return image * contrast + brightness


def adjust_gamma(image: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """Apply gamma correction.

    Args:
        image: float32 array in [0, 1] range
        gamma: gamma value (>1 brightens, <1 darkens, 1.0 = no change)
    """
    if gamma == 1.0:
        return image
    safe = np.clip(image, 0.0, None)
    return np.power(safe, 1.0 / gamma)


def histogram_stretch(image: np.ndarray, low_pct: float = 0.1,
                       high_pct: float = 99.9) -> np.ndarray:
    """Stretch histogram to use full dynamic range.

    Args:
        image: float32 array in [0, 1] range
        low_pct: lower percentile clip point
        high_pct: upper percentile clip point
    """
    lo = np.percentile(image, low_pct)
    hi = np.percentile(image, high_pct)
    if hi <= lo:
        return image
    return (image - lo) / (hi - lo)


def auto_stretch(image: np.ndarray) -> np.ndarray:
    """Automatic histogram stretch using median +/- 2.8 MAD."""
    median = np.median(image)
    mad = np.median(np.abs(image - median))
    if mad < 1e-8:
        return histogram_stretch(image)
    lo = max(0.0, median - 2.8 * mad)
    hi = min(1.0, median + 2.8 * mad * 5)
    if hi <= lo:
        return image
    return (image - lo) / (hi - lo)
