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
    centroids: Optional[list[tuple[float, float]]] = None,
    deconv: Optional[tuple[float, int]] = None,
    progress_cb: Optional[Callable[[int, int], bool]] = None,
) -> int:
    """Export SER frames to MP4.

    Args:
        ser_file: Open SER file.
        pipeline: Frame pipeline for processing.
        output_path: Output .mp4 path.
        start_frame: First frame index (0-based).
        end_frame: Last frame index (inclusive). -1 = last frame.
        fps: Output frame rate.
        quality: CRF value (lower = better quality, bigger file).
        crop_roi: Optional (x, y, w, h) crop region in image pixels.
        centroids: Optional per-frame (cx, cy) centroid positions for centering.
        deconv: Optional (psf_radius, iterations) for Richardson-Lucy deconvolution.
        progress_cb: Callback(current, total) -> bool. Return False to cancel.

    Returns:
        Number of frames written.
    """
    if end_frame < 0:
        end_frame = ser_file.frame_count - 1
    total = end_frame - start_frame + 1
    output_path = Path(output_path)

    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    # Pre-import deconvolution if needed
    rl_func = None
    if deconv:
        from .deconvolution import richardson_lucy
        rl_func = richardson_lucy
        rl_radius, rl_iters = deconv

    base_w, base_h = ser_file.width, ser_file.height

    # Determine output dimensions
    if crop_roi:
        _, _, cw, ch = crop_roi
        cw = cw - (cw % 2)
        ch = ch - (ch % 2)
        out_w, out_h = cw, ch
    else:
        out_w = base_w - (base_w % 2)
        out_h = base_h - (base_h % 2)

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

    count = 0
    try:
        for i in range(start_frame, end_frame + 1):
            # Get adjusted frame in float32 [0,1] — full 16-bit precision
            frame = pipeline.get_adjusted_frame_f32(i)

            # Apply Richardson-Lucy deconvolution in float domain
            if rl_func is not None:
                frame = rl_func(frame, rl_radius, rl_iters)

            # Ensure 3-channel
            if frame.ndim == 2:
                frame = np.stack([frame, frame, frame], axis=2)
            elif frame.shape[2] == 1:
                frame = np.repeat(frame, 3, axis=2)

            fh, fw = frame.shape[:2]

            # Apply crop
            if crop_roi:
                cx_roi, cy_roi, _, _ = crop_roi
                frame_idx = i - start_frame

                if centroids and frame_idx < len(centroids):
                    target_cx, target_cy = centroids[frame_idx]
                    x0 = int(round(target_cx - cw / 2))
                    y0 = int(round(target_cy - ch / 2))
                else:
                    x0 = cx_roi
                    y0 = cy_roi

                x0 = max(0, min(x0, fw - cw))
                y0 = max(0, min(y0, fh - ch))
                patch = frame[y0:y0 + ch, x0:x0 + cw, :]
            else:
                patch = frame[:out_h, :out_w, :]

            # Final conversion: float32 [0,1] → uint8 RGB24 for ffmpeg
            patch = np.clip(patch * 255.0, 0, 255).astype(np.uint8)

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
