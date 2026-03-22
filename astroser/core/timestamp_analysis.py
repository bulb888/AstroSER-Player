"""Timestamp quality analysis for SER files."""

import struct
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

# .NET DateTime epoch offset to Unix epoch (in 100ns ticks)
UNIX_EPOCH_TICKS = 621355968000000000


@dataclass
class TimestampReport:
    """Summary statistics for frame timestamps."""
    frame_count: int
    has_timestamps: bool
    avg_fps: float
    avg_delta_ms: float
    min_delta_ms: float
    max_delta_ms: float
    std_delta_ms: float
    zero_delta_count: int
    zero_delta_pct: float
    anomaly_count: int       # delta=0 or >2x average
    anomaly_pct: float
    first_utc: Optional[datetime]
    last_utc: Optional[datetime]
    duration_sec: float


def ticks_to_utc(ticks: int) -> Optional[datetime]:
    """Convert .NET DateTime ticks to Python UTC datetime."""
    if ticks <= 0:
        return None
    try:
        utc_seconds = (ticks - UNIX_EPOCH_TICKS) / 10_000_000
        return datetime.fromtimestamp(utc_seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def analyze_timestamps(timestamps: np.ndarray) -> TimestampReport:
    """Analyze an array of .NET DateTime ticks (int64).

    Returns a TimestampReport with statistics.
    """
    n = len(timestamps)
    if n == 0:
        return TimestampReport(
            frame_count=0, has_timestamps=False, avg_fps=0, avg_delta_ms=0,
            min_delta_ms=0, max_delta_ms=0, std_delta_ms=0,
            zero_delta_count=0, zero_delta_pct=0,
            anomaly_count=0, anomaly_pct=0,
            first_utc=None, last_utc=None, duration_sec=0,
        )

    first_utc = ticks_to_utc(int(timestamps[0]))
    last_utc = ticks_to_utc(int(timestamps[-1]))

    # Compute deltas in milliseconds (ticks are 100ns units)
    deltas_ticks = np.diff(timestamps.astype(np.int64))
    deltas_ms = deltas_ticks / 10_000.0  # 100ns -> ms

    avg_delta = float(np.mean(deltas_ms)) if len(deltas_ms) > 0 else 0
    min_delta = float(np.min(deltas_ms)) if len(deltas_ms) > 0 else 0
    max_delta = float(np.max(deltas_ms)) if len(deltas_ms) > 0 else 0
    std_delta = float(np.std(deltas_ms)) if len(deltas_ms) > 0 else 0

    zero_count = int(np.sum(deltas_ms == 0))
    anomaly_mask = (deltas_ms == 0) | (deltas_ms > 2 * avg_delta) if avg_delta > 0 else (deltas_ms == 0)
    anomaly_count = int(np.sum(anomaly_mask))

    avg_fps = 1000.0 / avg_delta if avg_delta > 0 else 0
    duration = float(timestamps[-1] - timestamps[0]) / 10_000_000.0 if n > 1 else 0

    return TimestampReport(
        frame_count=n,
        has_timestamps=True,
        avg_fps=avg_fps,
        avg_delta_ms=avg_delta,
        min_delta_ms=min_delta,
        max_delta_ms=max_delta,
        std_delta_ms=std_delta,
        zero_delta_count=zero_count,
        zero_delta_pct=100.0 * zero_count / max(1, n - 1),
        anomaly_count=anomaly_count,
        anomaly_pct=100.0 * anomaly_count / max(1, n - 1),
        first_utc=first_utc,
        last_utc=last_utc,
        duration_sec=duration,
    )


def get_deltas_ms(timestamps: np.ndarray) -> np.ndarray:
    """Return frame-to-frame deltas in milliseconds."""
    deltas_ticks = np.diff(timestamps.astype(np.int64))
    return deltas_ticks / 10_000.0


def get_utc_times(timestamps: np.ndarray) -> list[Optional[datetime]]:
    """Convert all timestamps to UTC datetimes."""
    return [ticks_to_utc(int(t)) for t in timestamps]


def export_csv(filepath: Path, timestamps: np.ndarray) -> None:
    """Export timestamp report as CSV."""
    deltas = get_deltas_ms(timestamps)
    avg_delta = float(np.mean(deltas)) if len(deltas) > 0 else 0

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("frame,utc_time,delta_ms,anomaly\n")
        for i, ticks in enumerate(timestamps):
            utc = ticks_to_utc(int(ticks))
            utc_str = utc.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if utc else ""
            if i == 0:
                f.write(f"{i + 1},{utc_str},,\n")
            else:
                d = float(deltas[i - 1])
                is_anomaly = "Y" if (d == 0 or (avg_delta > 0 and d > 2 * avg_delta)) else ""
                f.write(f"{i + 1},{utc_str},{d:.3f},{is_anomaly}\n")
