"""Closed-loop delay measurement and mount response analysis.

Analyzes the delay between MoveAxis commands (from tracking log) and
the actual target displacement visible in SER frames.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .tracking_log import TrackingLog, TrackingEntry


@dataclass
class DelayStats:
    """System control delay statistics."""
    avg_delay_ms: float
    max_delay_ms: float
    p95_delay_ms: float
    median_delay_ms: float
    sample_count: int


@dataclass
class MountResponse:
    """Mount response data for command vs response curves."""
    # Time arrays (seconds from start)
    time_sec: np.ndarray
    # Command values (rate_primary/secondary from log)
    cmd_primary: np.ndarray
    cmd_secondary: np.ndarray
    # Response values (actual err_dx/dy change)
    resp_dx: np.ndarray
    resp_dy: np.ndarray
    # Detected backlash (dead zone in pixels)
    backlash_primary: float
    backlash_secondary: float
    # Mount info string
    mount_info: str


def compute_delay(entries: list[TrackingEntry],
                  frame_interval_ms: float = 33.0) -> Optional[DelayStats]:
    """Estimate closed-loop delay from tracking entries.

    Looks for sign changes in rate_primary/secondary (command direction reversal)
    and measures how many frames until err_dx/dy shows corresponding change.
    """
    if len(entries) < 20:
        return None

    delays = []

    # Analyze primary axis (rate_primary → err_dx response)
    for axis_cmd, axis_err in [
        (np.array([e.rate_primary for e in entries]),
         np.array([e.err_dx for e in entries])),
        (np.array([e.rate_secondary for e in entries]),
         np.array([e.err_dy for e in entries])),
    ]:
        # Find command sign changes (direction reversals)
        cmd_signs = np.sign(axis_cmd)
        sign_changes = np.where(np.diff(cmd_signs) != 0)[0]

        for sc in sign_changes:
            if sc < 2 or sc + 10 >= len(entries):
                continue

            # Look for error response inflection point within next 10 entries
            err_before = axis_err[sc]
            cmd_direction = np.sign(axis_cmd[sc + 1])

            for offset in range(1, min(10, len(entries) - sc)):
                err_now = axis_err[sc + offset]
                err_change = err_now - err_before

                # Response detected when error starts changing in expected direction
                if cmd_direction != 0 and np.sign(err_change) == -cmd_direction:
                    delay_ms = offset * frame_interval_ms
                    delays.append(delay_ms)
                    break

    if not delays:
        return None

    arr = np.array(delays)
    return DelayStats(
        avg_delay_ms=float(np.mean(arr)),
        max_delay_ms=float(np.max(arr)),
        p95_delay_ms=float(np.percentile(arr, 95)),
        median_delay_ms=float(np.median(arr)),
        sample_count=len(arr),
    )


def compute_mount_response(log: TrackingLog) -> Optional[MountResponse]:
    """Compute mount response curves from tracking log."""
    entries = log.entries
    if len(entries) < 10:
        return None

    t0 = entries[0].timestamp.timestamp()
    time_sec = np.array([(e.timestamp - entries[0].timestamp).total_seconds() for e in entries])
    cmd_pri = np.array([e.rate_primary for e in entries])
    cmd_sec = np.array([e.rate_secondary for e in entries])
    err_dx = np.array([e.err_dx for e in entries])
    err_dy = np.array([e.err_dy for e in entries])

    # Compute response as derivative of error (position change per step)
    resp_dx = np.gradient(err_dx)
    resp_dy = np.gradient(err_dy)

    # Estimate backlash: dead zone around command direction reversals
    backlash_pri = _estimate_backlash(cmd_pri, err_dx)
    backlash_sec = _estimate_backlash(cmd_sec, err_dy)

    return MountResponse(
        time_sec=time_sec,
        cmd_primary=cmd_pri,
        cmd_secondary=cmd_sec,
        resp_dx=resp_dx,
        resp_dy=resp_dy,
        backlash_primary=backlash_pri,
        backlash_secondary=backlash_sec,
        mount_info=log.mount_info,
    )


def _estimate_backlash(commands: np.ndarray, errors: np.ndarray) -> float:
    """Estimate backlash as average dead pixels after direction reversal."""
    signs = np.sign(commands)
    reversals = np.where(np.diff(signs) != 0)[0]

    dead_zones = []
    for r in reversals:
        if r + 5 >= len(errors):
            continue
        # Measure how many pixels of error accumulate before response
        baseline = errors[r]
        for offset in range(1, min(5, len(errors) - r)):
            if abs(errors[r + offset] - baseline) > 0.5:
                dead_zone = abs(errors[r + offset] - baseline)
                dead_zones.append(dead_zone)
                break

    return float(np.mean(dead_zones)) if dead_zones else 0.0
