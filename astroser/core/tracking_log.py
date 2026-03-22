"""Parser for space-tracker tracking.log files."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class TrackingEntry:
    """One tracking data line."""
    timestamp: datetime         # UTC from log timestamp
    correction_num: int = 0
    detected: bool = False
    err_dx: float = 0.0
    err_dy: float = 0.0
    pixel_err: float = 0.0
    vt_x: float = 0.0
    vt_y: float = 0.0
    vp_x: float = 0.0
    vp_y: float = 0.0
    vi_x: float = 0.0
    vi_y: float = 0.0
    rate_primary: float = 0.0
    rate_secondary: float = 0.0
    c1: float = 0.0
    lost_count: int = 0


@dataclass
class TrackingLog:
    """Parsed tracking log with session info."""
    entries: list[TrackingEntry] = field(default_factory=list)
    session_header: str = ""
    mount_info: str = ""


# Regex for the data line (after timestamp prefix)
# Format: "   42 |Y|  +3.2   -1.5|  123| +1.23456 +2.34567| +0.12345 +0.23456| +0.01234 +0.02345| +12.34567 +3.45678|+45|  0"
_DATA_RE = re.compile(
    r'\s*(\d+)\s*\|'           # correction_count
    r'([YN])\|'                 # det
    r'\s*([+\-\d.]+)\s+([+\-\d.]+)\|'  # err_dx, err_dy
    r'\s*([+\-\d.]+)\|'        # pixel_err
    r'\s*([+\-\d.]+)\s+([+\-\d.]+)\|'  # vt_x, vt_y
    r'\s*([+\-\d.]+)\s+([+\-\d.]+)\|'  # vp_x, vp_y
    r'\s*([+\-\d.]+)\s+([+\-\d.]+)\|'  # vi_x, vi_y
    r'\s*([+\-\d.]+)\s+([+\-\d.]+)\|'  # rate_primary, rate_secondary
    r'\s*([+\-\d.]+)\|'        # c1
    r'\s*(\d+)'                 # lost_count
)

# Timestamp prefix: "HH:MM:SS.fff "
_TS_RE = re.compile(r'^(\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)$')


def parse_tracking_log(filepath: Path, reference_date: Optional[datetime] = None) -> TrackingLog:
    """Parse a tracking.log file.

    Args:
        filepath: Path to tracking.log
        reference_date: Date to use for timestamps (log only has time, no date).
                       If None, uses today's date.
    """
    log = TrackingLog()

    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    base_date = reference_date.date()

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    prev_hour = -1
    for line in lines:
        line = line.rstrip()
        if not line:
            continue

        # Check for session header
        if "闭环跟踪启动" in line or "等候观测启动" in line or "模拟跟踪启动" in line:
            log.session_header = line
            continue

        # Check for separator lines
        if line.startswith("===") or line.startswith("---"):
            continue

        # Check for mount info
        if "赤道仪" in line or "mount" in line.lower() or "经纬仪" in line:
            log.mount_info = line

        # Parse timestamp prefix
        ts_match = _TS_RE.match(line)
        if not ts_match:
            continue

        time_str = ts_match.group(1)
        rest = ts_match.group(2)

        # Parse time
        try:
            t = datetime.strptime(time_str, "%H:%M:%S.%f").time()
        except ValueError:
            continue

        # Handle day rollover
        if t.hour < prev_hour and prev_hour >= 23:
            base_date = base_date + timedelta(days=1)
        prev_hour = t.hour

        ts = datetime.combine(base_date, t, tzinfo=timezone.utc)

        # Try to match data line
        data_match = _DATA_RE.match(rest)
        if data_match:
            g = data_match.groups()
            entry = TrackingEntry(
                timestamp=ts,
                correction_num=int(g[0]),
                detected=(g[1] == 'Y'),
                err_dx=float(g[2]),
                err_dy=float(g[3]),
                pixel_err=float(g[4]),
                vt_x=float(g[5]),
                vt_y=float(g[6]),
                vp_x=float(g[7]),
                vp_y=float(g[8]),
                vi_x=float(g[9]),
                vi_y=float(g[10]),
                rate_primary=float(g[11]),
                rate_secondary=float(g[12]),
                c1=float(g[13]),
                lost_count=int(g[14]),
            )
            log.entries.append(entry)

    return log


def match_log_to_frames(log: TrackingLog, frame_utc_times: list[Optional[datetime]],
                        tolerance_ms: float = 50.0) -> list[Optional[TrackingEntry]]:
    """Match tracking log entries to frame timestamps.

    For each frame, find the closest log entry within ±tolerance_ms.
    Returns a list the same length as frame_utc_times.
    """
    result: list[Optional[TrackingEntry]] = [None] * len(frame_utc_times)
    if not log.entries or not frame_utc_times:
        return result

    # Build sorted array of entry timestamps (as Unix seconds)
    entry_times = np.array([e.timestamp.timestamp() for e in log.entries])
    tolerance_sec = tolerance_ms / 1000.0

    for i, ft in enumerate(frame_utc_times):
        if ft is None:
            continue
        ft_sec = ft.timestamp()
        # Binary search for nearest
        idx = np.searchsorted(entry_times, ft_sec)

        best_idx = -1
        best_diff = tolerance_sec + 1

        for candidate in (idx - 1, idx):
            if 0 <= candidate < len(entry_times):
                diff = abs(entry_times[candidate] - ft_sec)
                if diff < best_diff:
                    best_diff = diff
                    best_idx = candidate

        if best_idx >= 0 and best_diff <= tolerance_sec:
            result[i] = log.entries[best_idx]

    return result
