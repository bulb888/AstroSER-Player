"""Frame processing pipeline: raw SER data -> display-ready QImage."""

import numpy as np
from collections import OrderedDict
from threading import Thread, Lock
from PySide6.QtGui import QImage

from .ser_parser import SERFile, ColorID


class _LRUCache:
    """Simple thread-safe LRU cache for processed frames."""

    def __init__(self, maxsize: int = 32):
        self._maxsize = maxsize
        self._cache: OrderedDict[int, QImage] = OrderedDict()
        self._lock = Lock()

    def get(self, key: int) -> QImage | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: int, value: QImage) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                self._cache[key] = value
                if len(self._cache) > self._maxsize:
                    self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class FramePipeline:
    """Converts raw SER frame data into a display-ready QImage.

    Optimizations:
    - LUT-based adjustments (avoid per-pixel float math)
    - LRU cache for processed QImages
    - Background prefetch of upcoming frames
    """

    CACHE_SIZE = 64

    def __init__(self, ser_file: SERFile):
        self._ser = ser_file
        self._last_raw: np.ndarray | None = None
        self._last_index: int = -1

        # Adjustment parameters
        self.brightness: float = 0.0
        self.contrast: float = 1.0
        self.gamma: float = 1.0
        self.auto_stretch: bool = False
        self.stretch_low: float = 0.1
        self.stretch_high: float = 99.9
        self.solar_colorize: bool = False
        self.sharpen: float = 0.0

        # Solar colormap LUT (256 entries, RGB)
        self._solar_lut = self._build_solar_lut()

        # LUT cache
        self._lut: np.ndarray | None = None
        self._lut_params: tuple | None = None

        # Frame cache
        self._cache = _LRUCache(self.CACHE_SIZE)

        # Prefetch
        self._prefetch_lock = Lock()
        self._prefetch_thread: Thread | None = None

    def process_frame(self, index: int) -> QImage:
        """Process a frame and return a display-ready QImage."""
        # Check cache first
        cached = self._cache.get(index)
        if cached is not None:
            return cached

        raw = self._get_raw(index)
        img = self._to_display(raw)
        qimg = self._to_qimage(img)
        self._cache.put(index, qimg)
        return qimg

    def get_raw_frame(self, index: int) -> np.ndarray:
        """Get the raw frame data (for statistics)."""
        return self._get_raw(index)

    def get_adjusted_frame(self, index: int) -> np.ndarray:
        """Get fully adjusted frame as uint8 numpy array.

        Applies debayer + brightness/contrast/gamma/auto-stretch.
        Result matches what the user sees in the viewer.
        """
        raw = self._get_raw(index)
        return self._to_display(raw)

    def get_adjusted_frame_f32(self, index: int) -> np.ndarray:
        """Get fully adjusted frame as float32 [0..1] array.

        Full 16-bit precision preserved through the entire pipeline.
        No quantization to uint8 until the caller decides.
        Returns float32 (H,W) or (H,W,3), range [0,1].
        """
        raw = self._get_raw(index)
        color_id = self._ser.color_id

        # Debayer
        if color_id.is_bayer:
            from .debayer import debayer
            img = debayer(raw, color_id)
        elif color_id == ColorID.BGR:
            img = raw[:, :, ::-1].copy()
        else:
            img = raw

        max_val = (1 << self._ser.pixel_depth) - 1

        # Convert to float32 [0,1] — preserves full bit depth
        img_f = img.astype(np.float32) / max_val

        # Auto-stretch
        if self.auto_stretch:
            sample = img_f
            if img_f.size > 500000:
                if img_f.ndim == 2:
                    sample = img_f[::4, ::4]
                else:
                    sample = img_f[::4, ::4, :]
            auto_lo = float(np.percentile(sample, self.stretch_low))
            auto_hi = float(np.percentile(sample, self.stretch_high))
            if auto_hi > auto_lo:
                img_f = (img_f - auto_lo) / (auto_hi - auto_lo)

        # Contrast + brightness
        if self.contrast != 1.0 or self.brightness != 0.0:
            img_f = img_f * self.contrast + self.brightness

        # Gamma
        if self.gamma != 1.0:
            np.clip(img_f, 0.0, None, out=img_f)
            np.power(img_f, 1.0 / self.gamma, out=img_f)

        np.clip(img_f, 0.0, 1.0, out=img_f)

        # Sharpening (float domain)
        if self.sharpen > 0.0:
            from scipy.ndimage import uniform_filter
            blur = uniform_filter(img_f, size=3)
            img_f = img_f + self.sharpen * (img_f - blur)
            np.clip(img_f, 0.0, 1.0, out=img_f)

        return img_f

    def get_display_frame(self, index: int) -> np.ndarray:
        """Get debayered frame for GPU rendering (no LUT/adjustments).

        Returns the frame after debayer/BGR conversion but before
        brightness/contrast/gamma adjustments. The GPU shader handles those.
        """
        raw = self._get_raw(index)
        color_id = self._ser.color_id

        if color_id.is_bayer:
            from .debayer import debayer
            return debayer(raw, color_id)
        elif color_id == ColorID.BGR:
            return raw[:, :, ::-1].copy()
        return raw

    def prefetch(self, current: int, direction: int = 1, count: int = 4) -> None:
        """Prefetch upcoming frames in background."""
        if self._prefetch_thread is not None and self._prefetch_thread.is_alive():
            return  # Don't stack prefetch requests

        def _do_prefetch():
            for i in range(1, count + 1):
                idx = current + i * direction
                if 0 <= idx < self._ser.frame_count:
                    if self._cache.get(idx) is None:
                        try:
                            raw = self._ser.get_frame(idx)
                            img = self._to_display(raw)
                            qimg = self._to_qimage(img)
                            self._cache.put(idx, qimg)
                        except Exception:
                            break

        self._prefetch_thread = Thread(target=_do_prefetch, daemon=True)
        self._prefetch_thread.start()

    def _get_raw(self, index: int) -> np.ndarray:
        """Get raw frame, caching the last one."""
        if index != self._last_index:
            self._last_raw = self._ser.get_frame(index)
            self._last_index = index
        return self._last_raw

    def _build_lut(self, max_val: int, auto_lo: float = 0.0,
                   auto_hi: float = 1.0) -> np.ndarray:
        """Build a lookup table for brightness/contrast/gamma."""
        params = (self.brightness, self.contrast, self.gamma,
                  self.auto_stretch, auto_lo, auto_hi, max_val)
        if self._lut is not None and self._lut_params == params:
            return self._lut

        entries = max_val + 1
        x = np.arange(entries, dtype=np.float32) / max_val

        # Auto stretch
        if self.auto_stretch and auto_hi > auto_lo:
            x = (x - auto_lo) / (auto_hi - auto_lo)

        # Contrast and brightness
        if self.contrast != 1.0 or self.brightness != 0.0:
            x = x * self.contrast + self.brightness

        # Gamma
        if self.gamma != 1.0:
            np.clip(x, 0.0, None, out=x)
            np.power(x, 1.0 / self.gamma, out=x)

        np.clip(x, 0.0, 1.0, out=x)
        self._lut = (x * 255).astype(np.uint8)
        self._lut_params = params
        return self._lut

    def _to_display(self, raw: np.ndarray) -> np.ndarray:
        """Convert raw frame to display-ready uint8 array."""
        color_id = self._ser.color_id

        # Debayer if needed
        if color_id.is_bayer:
            from .debayer import debayer
            img = debayer(raw, color_id)
        elif color_id == ColorID.BGR:
            img = raw[:, :, ::-1].copy()
        else:
            img = raw

        max_val = (1 << self._ser.pixel_depth) - 1

        # Compute auto-stretch percentiles if needed
        auto_lo, auto_hi = 0.0, 1.0
        if self.auto_stretch:
            img_sample = img
            # Subsample for speed on large frames
            if img.size > 500000:
                if img.ndim == 2:
                    img_sample = img[::4, ::4]
                else:
                    img_sample = img[::4, ::4, :]
            sample_f = img_sample.astype(np.float32) / max_val
            auto_lo = float(np.percentile(sample_f, self.stretch_low))
            auto_hi = float(np.percentile(sample_f, self.stretch_high))

        # Use LUT for fast mapping
        lut = self._build_lut(max_val, auto_lo, auto_hi)

        # Apply LUT
        if max_val <= 65535:
            result = lut[img]
        else:
            img_f = img.astype(np.float32) / max_val
            img_f = self._apply_adjustments_float(img_f, auto_lo, auto_hi)
            np.clip(img_f, 0.0, 1.0, out=img_f)
            result = (img_f * 255).astype(np.uint8)

        # Apply sharpening (unsharp mask)
        if self.sharpen > 0.0:
            result = self._apply_sharpen(result, self.sharpen)

        return result

    def _apply_adjustments_float(self, img: np.ndarray,
                                  auto_lo: float, auto_hi: float) -> np.ndarray:
        """Fallback float-based adjustments."""
        if self.auto_stretch and auto_hi > auto_lo:
            img = (img - auto_lo) / (auto_hi - auto_lo)
        if self.contrast != 1.0 or self.brightness != 0.0:
            img = img * self.contrast + self.brightness
        if self.gamma != 1.0:
            img = np.clip(img, 0.0, None)
            img = np.power(img, 1.0 / self.gamma)
        return img

    @staticmethod
    def _apply_sharpen(img: np.ndarray, strength: float) -> np.ndarray:
        """Apply unsharp mask sharpening to uint8 image."""
        from scipy.ndimage import uniform_filter
        blur = uniform_filter(img.astype(np.float32), size=3)
        sharp = img.astype(np.float32) + strength * (img.astype(np.float32) - blur)
        return np.clip(sharp, 0, 255).astype(np.uint8)

    @staticmethod
    def _build_solar_lut() -> np.ndarray:
        """Build a solar false-color LUT (256x3 uint8).

        Produces warm orange/yellow tones typical of H-alpha solar imaging.
        Dark regions -> deep red/brown, bright regions -> yellow/white.
        """
        lut = np.zeros((256, 3), dtype=np.uint8)
        x = np.linspace(0, 1, 256)

        # Red: rises quickly, saturates early
        lut[:, 0] = np.clip(x * 1.8, 0, 1) * 255
        # Green: slower rise, gives orange in midtones
        lut[:, 1] = np.clip((x - 0.15) * 1.2, 0, 1) ** 0.9 * 255
        # Blue: only in highlights, gives warm white at peaks
        lut[:, 2] = np.clip((x - 0.5) * 1.5, 0, 1) ** 1.2 * 200

        return lut

    def _to_qimage(self, img: np.ndarray) -> QImage:
        """Convert a uint8 numpy array to QImage."""
        if self.solar_colorize:
            # Apply solar false color
            if img.ndim == 3:
                # Convert to grayscale first
                gray = np.mean(img, axis=2).astype(np.uint8)
            else:
                gray = img
            rgb = self._solar_lut[gray]  # LUT indexing: (H,W) -> (H,W,3)
            rgb = np.ascontiguousarray(rgb)
            h, w = gray.shape
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
            return qimg.copy()

        if img.ndim == 2:
            h, w = img.shape
            img = np.ascontiguousarray(img)
            qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8)
            return qimg.copy()
        else:
            h, w, c = img.shape
            img = np.ascontiguousarray(img)
            bytes_per_line = w * c
            qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            return qimg.copy()

    def invalidate_cache(self) -> None:
        """Force re-read of the current frame on next access."""
        self._last_index = -1
        self._last_raw = None
        self._lut = None
        self._lut_params = None
        self._cache.clear()
