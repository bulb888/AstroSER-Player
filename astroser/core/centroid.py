"""Target centroid detection for PIPP-style object centering.

Uses native C module (fast_ops.dll) when available for ~10x speedup.
Falls back to numpy implementation otherwise.
"""

from typing import Optional, Callable
import numpy as np

from .ser_parser import SERFile

# Try native module
try:
    from ..native import is_available as _native_available, detect_centroids_batch as _native_batch, centroid as _native_centroid
    _HAS_NATIVE = _native_available()
except ImportError:
    _HAS_NATIVE = False


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return np.mean(frame, axis=2).astype(frame.dtype)


def _centroid_py(gray: np.ndarray, threshold_pct: float) -> tuple[float, float]:
    """Pure numpy centroid fallback."""
    gray_f = gray.astype(np.float32)
    thresh = np.percentile(gray_f, threshold_pct)
    mask = gray_f >= thresh
    weighted = np.where(mask, gray_f, 0.0)
    total = weighted.sum()
    if total == 0:
        return float(gray.shape[1] / 2), float(gray.shape[0] / 2)
    rows = np.arange(gray.shape[0], dtype=np.float32)
    cols = np.arange(gray.shape[1], dtype=np.float32)
    cy = float(np.dot(rows, weighted.sum(axis=1)) / total)
    cx = float(np.dot(cols, weighted.sum(axis=0)) / total)
    return cx, cy


def detect_all_centroids(
    ser_file: SERFile,
    start_frame: int = 0,
    end_frame: int = -1,
    threshold_pct: float = 85.0,
    search_radius: int = 0,
    progress_cb: Optional[Callable[[int, int], bool]] = None,
) -> list[tuple[float, float]]:
    """Detect centroids for a range of frames.

    Uses native C batch detection when available (~10x faster).
    """
    if end_frame < 0:
        end_frame = ser_file.frame_count - 1
    total = end_frame - start_frame + 1

    # Native batch path: read all frames, pass to C
    if _HAS_NATIVE:
        return _detect_native(ser_file, start_frame, end_frame, threshold_pct,
                              search_radius, progress_cb)

    # Python fallback
    return _detect_python(ser_file, start_frame, end_frame, threshold_pct,
                          search_radius, progress_cb)


def _detect_native(ser_file, start_frame, end_frame, threshold_pct,
                   search_radius, progress_cb):
    """Native C batch centroid detection."""
    total = end_frame - start_frame + 1
    img_h, img_w = ser_file.height, ser_file.width

    # Process in batches to allow progress updates and cancellation
    BATCH = 100
    centroids = []

    for batch_start in range(start_frame, end_frame + 1, BATCH):
        batch_end = min(batch_start + BATCH - 1, end_frame)
        batch_size = batch_end - batch_start + 1

        # Read frames
        frames = []
        for i in range(batch_start, batch_end + 1):
            raw = ser_file.get_frame(i)
            if raw.ndim == 3:
                raw = np.mean(raw, axis=2).astype(raw.dtype)
            frames.append(np.ascontiguousarray(raw))

        # If not first batch, prepend search hint from last known position
        batch_centroids = _native_batch(frames, threshold_pct, search_radius)

        # Adjust first frame of non-first batches to use last known position
        if centroids and batch_centroids:
            # The C function starts from center for first frame in batch.
            # Re-detect first frame with search window around last known pos.
            last_cx, last_cy = centroids[-1]
            sr = search_radius if search_radius > 0 else max(img_w, img_h) // 5
            x0 = max(0, int(last_cx) - sr)
            y0 = max(0, int(last_cy) - sr)
            x1 = min(img_w, int(last_cx) + sr)
            y1 = min(img_h, int(last_cy) + sr)

            region = frames[0][y0:y1, x0:x1]
            if region.size > 0:
                rcx, rcy = _native_centroid(np.ascontiguousarray(region), threshold_pct)
                batch_centroids[0] = (x0 + rcx, y0 + rcy)

        centroids.extend(batch_centroids)

        if progress_cb:
            done = len(centroids)
            if not progress_cb(done, total):
                # Fill remaining
                last = centroids[-1]
                centroids.extend([last] * (total - len(centroids)))
                break

    if progress_cb:
        progress_cb(total, total)

    return centroids


def _detect_python(ser_file, start_frame, end_frame, threshold_pct,
                   search_radius, progress_cb):
    """Pure Python/numpy fallback."""
    total = end_frame - start_frame + 1
    img_h, img_w = ser_file.height, ser_file.width
    if search_radius <= 0:
        search_radius = max(img_w, img_h) // 5

    centroids = []
    last_cx, last_cy = float(img_w / 2), float(img_h / 2)

    for i in range(start_frame, end_frame + 1):
        raw = ser_file.get_frame(i)
        gray = _to_gray(raw)
        frame_idx = i - start_frame

        if frame_idx == 0:
            sub = 4 if gray.size > 2_000_000 else (2 if gray.size > 500_000 else 1)
            if sub > 1:
                sampled = gray[::sub, ::sub]
                cx, cy = _centroid_py(sampled, threshold_pct)
                cx *= sub
                cy *= sub
            else:
                cx, cy = _centroid_py(gray, threshold_pct)
        else:
            x0 = max(0, int(last_cx) - search_radius)
            y0 = max(0, int(last_cy) - search_radius)
            x1 = min(img_w, int(last_cx) + search_radius)
            y1 = min(img_h, int(last_cy) + search_radius)
            region = gray[y0:y1, x0:x1]
            rcx, rcy = _centroid_py(region, threshold_pct)
            cx = x0 + rcx
            cy = y0 + rcy

        last_cx, last_cy = cx, cy
        centroids.append((cx, cy))

        if progress_cb and (frame_idx + 1) % 20 == 0:
            if not progress_cb(frame_idx + 1, total):
                last = centroids[-1]
                centroids.extend([last] * (total - len(centroids)))
                break

    if progress_cb:
        progress_cb(total, total)

    return centroids
