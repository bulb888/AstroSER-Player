"""Export SER frames to universally compatible MP4 (H.264 baseline, yuv420p).

Works on iPhone, Android, Windows, macOS — any modern device.
Uses imageio-ffmpeg (bundled ffmpeg binary, no system install needed).
"""

from pathlib import Path
from typing import Optional, Callable
import subprocess

import numpy as np
import imageio_ffmpeg

from .ser_parser import SERFile
from .frame_pipeline import FramePipeline


def export_mp4(
    ser_file: SERFile,
    pipeline: FramePipeline,
    output_path: str | Path,
    start_frame: int = 0,
    end_frame: int = -1,
    fps: float = 25.0,
    quality: int = 23,
    crop_roi: Optional[tuple[int, int, int, int]] = None,
    tracking_offsets: Optional[list[Optional[tuple[float, float]]]] = None,
    progress_cb: Optional[Callable[[int, int], bool]] = None,
) -> int:
    """Export SER frames to MP4.

    Args:
        ser_file: Open SER file.
        pipeline: Frame pipeline for processing (debayer, adjustments).
        output_path: Output .mp4 path.
        start_frame: First frame index (0-based).
        end_frame: Last frame index (inclusive). -1 = last frame.
        fps: Output frame rate.
        quality: CRF value (lower = better quality, bigger file).
        crop_roi: Optional (x, y, w, h) crop region in image pixels.
        tracking_offsets: Optional per-frame (dx, dy) offsets for auto-centering.
            Index matches frame index. Crop window shifts by -dx, -dy each frame.
        progress_cb: Callback(current, total) -> bool. Return False to cancel.

    Returns:
        Number of frames written.
    """
    if end_frame < 0:
        end_frame = ser_file.frame_count - 1
    total = end_frame - start_frame + 1
    output_path = Path(output_path)

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    # Determine output dimensions
    if crop_roi:
        cx, cy, cw, ch = crop_roi
        # Ensure even (H.264 requirement)
        cw = cw - (cw % 2)
        ch = ch - (ch % 2)
        out_w, out_h = cw, ch
    else:
        out_w, out_h = ser_file.width, ser_file.height
        if out_w % 2 != 0:
            out_w -= 1
        if out_h % 2 != 0:
            out_h -= 1

    cmd = [
        ffmpeg_path,
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{out_w}x{out_h}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-profile:v", "baseline",
        "-level", "3.1",
        "-pix_fmt", "yuv420p",
        "-crf", str(quality),
        "-preset", "medium",
        "-movflags", "+faststart",
        "-an",
        str(output_path),
    ]

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
    )

    img_h, img_w = ser_file.height, ser_file.width

    # Pre-compute base crop center for auto-centering
    if crop_roi and tracking_offsets:
        base_cx = cx + cw // 2
        base_cy = cy + ch // 2

    count = 0
    try:
        for i in range(start_frame, end_frame + 1):
            frame = pipeline.get_display_frame(i)

            # Convert to 8-bit RGB
            if frame.dtype == np.uint16:
                frame = (frame / 256).astype(np.uint8)

            # Ensure 3-channel RGB
            if frame.ndim == 2:
                frame = np.stack([frame, frame, frame], axis=2)
            elif frame.shape[2] == 1:
                frame = np.repeat(frame, 3, axis=2)

            # Apply crop
            if crop_roi:
                if tracking_offsets and i < len(tracking_offsets) and tracking_offsets[i] is not None:
                    # Auto-center: shift crop window by tracking error
                    dx, dy = tracking_offsets[i]
                    shift_cx = int(round(base_cx - dx))
                    shift_cy = int(round(base_cy - dy))
                else:
                    shift_cx = cx + cw // 2
                    shift_cy = cy + ch // 2

                # Compute crop rect centered on shifted position, clamped to frame
                x0 = max(0, min(shift_cx - cw // 2, img_w - cw))
                y0 = max(0, min(shift_cy - ch // 2, img_h - ch))
                patch = frame[y0:y0 + ch, x0:x0 + cw, :]
            else:
                patch = frame[:out_h, :out_w, :]

            if not patch.flags['C_CONTIGUOUS']:
                patch = np.ascontiguousarray(patch)

            proc.stdin.write(patch.tobytes())
            count += 1

            if progress_cb and count % 5 == 0:
                if not progress_cb(count, total):
                    break
    finally:
        proc.stdin.close()
        stderr_out = proc.communicate()[1]
        if proc.returncode != 0 and count > 0:
            raise RuntimeError(f"ffmpeg error: {stderr_out.decode('utf-8', errors='replace')[-500:]}")

    return count
