"""Bayer pattern demosaicing. Uses scipy if available, falls back to pure NumPy."""

import numpy as np
from .ser_parser import ColorID

# Try scipy for fastest convolution, fall back to pure NumPy
try:
    from scipy.ndimage import convolve as _scipy_convolve
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def debayer(raw: np.ndarray, color_id: ColorID) -> np.ndarray:
    """Convert single-plane Bayer CFA data to RGB."""
    pattern_map = {
        ColorID.BAYER_RGGB: "RGGB",
        ColorID.BAYER_GRBG: "GRBG",
        ColorID.BAYER_GBRG: "GBRG",
        ColorID.BAYER_BGGR: "BGGR",
    }
    pattern = pattern_map.get(color_id)
    if pattern is None:
        return np.stack([raw, raw, raw], axis=-1)
    return _debayer_bilinear(raw, pattern)


def _conv3x3(src: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """3x3 convolution: scipy if available, else separable NumPy."""
    if _HAS_SCIPY:
        return _scipy_convolve(src, kernel, mode='reflect')

    # Separable decomposition: kernel = [0.5,1,0.5]^T * [0.5,1,0.5]
    # This works for the bilinear kernel specifically
    h, w = src.shape
    k1d = np.array([0.5, 1.0, 0.5], dtype=np.float32)

    # Horizontal pass
    p = np.pad(src, ((0, 0), (1, 1)), mode='reflect')
    tmp = k1d[0] * p[:, :-2] + k1d[1] * p[:, 1:-1] + k1d[2] * p[:, 2:]

    # Vertical pass
    p2 = np.pad(tmp, ((1, 1), (0, 0)), mode='reflect')
    return k1d[0] * p2[:-2, :] + k1d[1] * p2[1:-1, :] + k1d[2] * p2[2:, :]


def _debayer_bilinear(raw: np.ndarray, pattern: str) -> np.ndarray:
    """Bilinear interpolation demosaicing."""
    h, w = raw.shape
    h2 = h - (h % 2)
    w2 = w - (w % 2)
    raw = raw[:h2, :w2]
    h, w = raw.shape

    if pattern == "RGGB":
        r_row, r_col = 0, 0
        b_row, b_col = 1, 1
    elif pattern == "GRBG":
        r_row, r_col = 0, 1
        b_row, b_col = 1, 0
    elif pattern == "GBRG":
        r_row, r_col = 1, 0
        b_row, b_col = 0, 1
    elif pattern == "BGGR":
        r_row, r_col = 1, 1
        b_row, b_col = 0, 0
    else:
        raise ValueError(f"Unknown Bayer pattern: {pattern}")

    g1_row, g1_col = r_row, 1 - r_col
    g2_row, g2_col = 1 - r_row, r_col

    raw_f = raw.astype(np.float32)

    r_ch = np.zeros((h, w), dtype=np.float32)
    g_ch = np.zeros((h, w), dtype=np.float32)
    b_ch = np.zeros((h, w), dtype=np.float32)
    r_mask = np.zeros((h, w), dtype=np.float32)
    g_mask = np.zeros((h, w), dtype=np.float32)
    b_mask = np.zeros((h, w), dtype=np.float32)

    r_ch[r_row::2, r_col::2] = raw_f[r_row::2, r_col::2]
    r_mask[r_row::2, r_col::2] = 1.0
    b_ch[b_row::2, b_col::2] = raw_f[b_row::2, b_col::2]
    b_mask[b_row::2, b_col::2] = 1.0
    g_ch[g1_row::2, g1_col::2] = raw_f[g1_row::2, g1_col::2]
    g_ch[g2_row::2, g2_col::2] = raw_f[g2_row::2, g2_col::2]
    g_mask[g1_row::2, g1_col::2] = 1.0
    g_mask[g2_row::2, g2_col::2] = 1.0

    kernel = np.array([
        [0.25, 0.5, 0.25],
        [0.5,  1.0, 0.5],
        [0.25, 0.5, 0.25],
    ], dtype=np.float32)

    r_ch = _interpolate(r_ch, r_mask, kernel)
    g_ch = _interpolate(g_ch, g_mask, kernel)
    b_ch = _interpolate(b_ch, b_mask, kernel)

    max_val = np.iinfo(raw.dtype).max if np.issubdtype(raw.dtype, np.integer) else 1.0
    out = np.empty((h, w, 3), dtype=raw.dtype)
    out[:, :, 0] = np.clip(r_ch, 0, max_val).astype(raw.dtype)
    out[:, :, 1] = np.clip(g_ch, 0, max_val).astype(raw.dtype)
    out[:, :, 2] = np.clip(b_ch, 0, max_val).astype(raw.dtype)
    return out


def _interpolate(channel: np.ndarray, mask: np.ndarray,
                 kernel: np.ndarray) -> np.ndarray:
    """Interpolate missing values using convolution."""
    value_sum = _conv3x3(channel, kernel)
    weight_sum = _conv3x3(mask, kernel)
    weight_sum = np.maximum(weight_sum, 1e-6)
    return np.where(mask > 0, channel, value_sum / weight_sum)
