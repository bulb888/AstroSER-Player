"""SER file format parser with memory-mapped frame access.

SER format specification:
  - 14-byte FileID: "LUCAM-RECORDER"
  - 164-byte header fields
  - Frame data (W * H * BytesPerPixel * Planes per frame)
  - Optional timestamp trailer (8 bytes per frame, Windows FILETIME)
"""

import struct
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional

import numpy as np

# Header constants
FILE_ID = b"LUCAM-RECORDER"
FILE_ID_SIZE = 14
HEADER_SIZE = 164
TOTAL_HEADER_SIZE = FILE_ID_SIZE + HEADER_SIZE  # 178 bytes

# struct format: FileID(14s) + LuID(i) + ColorID(i) + LittleEndian(i) +
#   Width(i) + Height(i) + PixelDepth(i) + FrameCount(i) +
#   Observer(40s) + Instrument(40s) + Telescope(40s) +
#   DateTime(q) + DateTimeUTC(q)
HEADER_FORMAT = "<14siiiiiii40s40s40sqq"
HEADER_STRUCT = struct.Struct(HEADER_FORMAT)

# .NET DateTime epoch: 0001-01-01 UTC
# SER uses .NET DateTime ticks (100ns intervals since 0001-01-01)
_DOTNET_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)


class ColorID(IntEnum):
    """SER color format identifiers."""
    MONO = 0
    BAYER_RGGB = 8
    BAYER_GRBG = 9
    BAYER_GBRG = 10
    BAYER_BGGR = 11
    BAYER_CYYM = 16
    BAYER_YCMY = 17
    BAYER_YMCY = 18
    BAYER_MYYC = 19
    RGB = 100
    BGR = 101

    @property
    def is_bayer(self) -> bool:
        return self in (
            ColorID.BAYER_RGGB, ColorID.BAYER_GRBG,
            ColorID.BAYER_GBRG, ColorID.BAYER_BGGR,
            ColorID.BAYER_CYYM, ColorID.BAYER_YCMY,
            ColorID.BAYER_YMCY, ColorID.BAYER_MYYC,
        )

    @property
    def is_color(self) -> bool:
        return self in (ColorID.RGB, ColorID.BGR)

    @property
    def planes(self) -> int:
        """Number of color planes (1 for mono/bayer, 3 for RGB/BGR)."""
        return 3 if self.is_color else 1

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ")


def _ticks_to_datetime(ticks: int) -> Optional[datetime]:
    """Convert .NET DateTime ticks (100ns intervals since 0001-01-01) to datetime."""
    if ticks <= 0:
        return None
    try:
        return _DOTNET_EPOCH + timedelta(microseconds=ticks // 10)
    except (OverflowError, OSError, ValueError):
        return None


def _decode_string(raw: bytes) -> str:
    """Decode a null-terminated string from SER header."""
    null_pos = raw.find(b'\x00')
    if null_pos >= 0:
        raw = raw[:null_pos]
    try:
        return raw.decode('utf-8').strip()
    except UnicodeDecodeError:
        return raw.decode('latin-1').strip()


class SERFile:
    """Memory-mapped SER file reader.

    Usage:
        with SERFile("capture.ser") as ser:
            print(f"{ser.width}x{ser.height}, {ser.frame_count} frames")
            frame = ser.get_frame(0)
    """

    def __init__(self, filepath: str | Path):
        self._filepath = Path(filepath)
        self._mmap: Optional[np.memmap] = None
        self._timestamps: Optional[np.ndarray] = None

        # Header fields
        self._lu_id = 0
        self._color_id = ColorID.MONO
        self._little_endian_flag = 0
        self._width = 0
        self._height = 0
        self._pixel_depth = 0
        self._frame_count = 0
        self._observer = ""
        self._instrument = ""
        self._telescope = ""
        self._datetime_local: Optional[datetime] = None
        self._datetime_utc: Optional[datetime] = None

    def open(self) -> "SERFile":
        """Open and parse the SER file."""
        if not self._filepath.exists():
            raise FileNotFoundError(f"SER file not found: {self._filepath}")

        file_size = self._filepath.stat().st_size
        if file_size < TOTAL_HEADER_SIZE:
            raise ValueError(f"File too small to be a valid SER file: {file_size} bytes")

        with open(self._filepath, "rb") as f:
            header_data = f.read(TOTAL_HEADER_SIZE)

        self._parse_header(header_data)
        self._validate_header(file_size)
        self._setup_memmap()
        self._load_timestamps(file_size)

        return self

    def close(self) -> None:
        """Close the file and release resources."""
        if self._mmap is not None:
            del self._mmap
            self._mmap = None
        self._timestamps = None

    def __enter__(self) -> "SERFile":
        return self.open()

    def __exit__(self, *args) -> None:
        self.close()

    def _parse_header(self, data: bytes) -> None:
        """Parse the 178-byte SER header."""
        fields = HEADER_STRUCT.unpack(data)

        file_id = fields[0]
        if file_id != FILE_ID:
            raise ValueError(
                f"Invalid SER file ID: {file_id!r} (expected {FILE_ID!r})"
            )

        self._lu_id = fields[1]
        try:
            self._color_id = ColorID(fields[2])
        except ValueError:
            raise ValueError(f"Unknown ColorID: {fields[2]}")

        self._little_endian_flag = fields[3]
        self._width = fields[4]
        self._height = fields[5]
        self._pixel_depth = fields[6]
        self._frame_count = fields[7]
        self._observer = _decode_string(fields[8])
        self._instrument = _decode_string(fields[9])
        self._telescope = _decode_string(fields[10])
        self._datetime_local = _ticks_to_datetime(fields[11])
        self._datetime_utc = _ticks_to_datetime(fields[12])

    def _validate_header(self, file_size: int) -> None:
        """Validate header values are reasonable."""
        if self._width <= 0 or self._height <= 0:
            raise ValueError(f"Invalid dimensions: {self._width}x{self._height}")
        if self._pixel_depth < 1 or self._pixel_depth > 16:
            raise ValueError(f"Invalid pixel depth: {self._pixel_depth}")
        if self._frame_count <= 0:
            raise ValueError(f"Invalid frame count: {self._frame_count}")

        available = file_size - TOTAL_HEADER_SIZE
        actual_frames = available // self.frame_size_bytes
        if actual_frames <= 0:
            raise ValueError(
                f"File too small: need {self.frame_size_bytes} bytes per frame, "
                f"have {available}"
            )
        if actual_frames != self._frame_count:
            self._frame_count = actual_frames

    def _setup_memmap(self) -> None:
        """Create memory-mapped array for frame data."""
        dtype = np.uint8 if self.bytes_per_pixel == 1 else np.uint16
        total_pixels_per_frame = self._width * self._height * self._color_id.planes

        self._mmap = np.memmap(
            self._filepath,
            dtype=dtype,
            mode='r',
            offset=TOTAL_HEADER_SIZE,
            shape=(self._frame_count, total_pixels_per_frame),
        )

    def _load_timestamps(self, file_size: int) -> None:
        """Load optional timestamp trailer if present."""
        trailer_offset = TOTAL_HEADER_SIZE + self._frame_count * self.frame_size_bytes
        trailer_size = self._frame_count * 8

        if file_size >= trailer_offset + trailer_size:
            self._timestamps = np.memmap(
                self._filepath,
                dtype=np.int64,
                mode='r',
                offset=trailer_offset,
                shape=(self._frame_count,),
            )

    # --- Properties ---

    @property
    def filepath(self) -> Path:
        return self._filepath

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def pixel_depth(self) -> int:
        """Bits per pixel per plane."""
        return self._pixel_depth

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def color_id(self) -> ColorID:
        return self._color_id

    @property
    def is_little_endian(self) -> bool:
        """Whether pixel data is little-endian.

        Note: The LittleEndian field meaning is inverted in practice.
        0 = little-endian (common), 1 = big-endian.
        """
        return self._little_endian_flag == 0

    @property
    def bytes_per_pixel(self) -> int:
        """Bytes per pixel per plane."""
        return 1 if self._pixel_depth <= 8 else 2

    @property
    def frame_size_bytes(self) -> int:
        """Size of one frame in bytes."""
        return self._width * self._height * self.bytes_per_pixel * self._color_id.planes

    @property
    def observer(self) -> str:
        return self._observer

    @property
    def instrument(self) -> str:
        return self._instrument

    @property
    def telescope(self) -> str:
        return self._telescope

    @property
    def datetime_local(self) -> Optional[datetime]:
        return self._datetime_local

    @property
    def datetime_utc(self) -> Optional[datetime]:
        return self._datetime_utc

    @property
    def has_timestamps(self) -> bool:
        return self._timestamps is not None

    # --- Frame Access ---

    def get_frame(self, index: int) -> np.ndarray:
        """Get a single frame as a numpy array.

        Returns:
            For MONO/Bayer: shape (H, W), dtype uint8 or uint16
            For RGB/BGR: shape (H, W, 3), dtype uint8 or uint16
        """
        if not 0 <= index < self._frame_count:
            raise IndexError(f"Frame index {index} out of range [0, {self._frame_count})")

        if self._mmap is None:
            raise RuntimeError("SER file is not open")

        raw = np.array(self._mmap[index])  # copy from memmap

        # Handle endianness for 16-bit data
        if self.bytes_per_pixel == 2 and not self.is_little_endian:
            raw = raw.byteswap()

        # Reshape
        planes = self._color_id.planes
        if planes == 1:
            return raw.reshape(self._height, self._width)
        else:
            return raw.reshape(self._height, self._width, planes)

    def get_timestamp(self, index: int) -> Optional[datetime]:
        """Get the timestamp for a specific frame."""
        if self._timestamps is None:
            return None
        if not 0 <= index < self._frame_count:
            raise IndexError(f"Frame index {index} out of range [0, {self._frame_count})")
        return _ticks_to_datetime(int(self._timestamps[index]))

    # --- Info ---

    def info_dict(self) -> dict:
        """Return a dictionary with all file metadata."""
        return {
            "filepath": str(self._filepath),
            "width": self._width,
            "height": self._height,
            "pixel_depth": self._pixel_depth,
            "frame_count": self._frame_count,
            "color_id": self._color_id.display_name,
            "little_endian": self.is_little_endian,
            "bytes_per_pixel": self.bytes_per_pixel,
            "frame_size_bytes": self.frame_size_bytes,
            "observer": self._observer,
            "instrument": self._instrument,
            "telescope": self._telescope,
            "datetime_local": self._datetime_local.strftime("%Y-%m-%d %H:%M:%S") if self._datetime_local else "",
            "datetime_utc": self._datetime_utc.strftime("%Y-%m-%d %H:%M:%S") if self._datetime_utc else "",
            "has_timestamps": self.has_timestamps,
        }

    def save_trimmed(self, output_path: str | Path, start: int, end: int) -> int:
        """Save a range of frames [start, end] to a new SER file (lossless).

        Copies the header (with updated frame count), raw frame data byte-for-byte,
        and the corresponding timestamps if present.

        Returns the number of frames written.
        """
        if self._mmap is None:
            raise RuntimeError("SER file is not open")
        if not (0 <= start <= end < self._frame_count):
            raise ValueError(
                f"Invalid range [{start}, {end}] for {self._frame_count} frames"
            )

        new_count = end - start + 1
        output_path = Path(output_path)

        with open(self._filepath, "rb") as src:
            header_data = bytearray(src.read(TOTAL_HEADER_SIZE))

        # Patch frame count in header (offset 14 + 4*3 = 26, 4 bytes little-endian)
        frame_count_offset = FILE_ID_SIZE + 6 * 4  # after FileID + LuID + ColorID + LE + W + H + PixelDepth
        # Actually: FileID(14) + LuID(4) + ColorID(4) + LE(4) + W(4) + H(4) + PixelDepth(4) = 38
        # FrameCount is at offset 38
        frame_count_offset = FILE_ID_SIZE + 6 * 4  # 14 + 24 = 38
        struct.pack_into("<i", header_data, frame_count_offset, new_count)

        with open(output_path, "wb") as out:
            # Write header
            out.write(header_data)

            # Write frame data byte-for-byte (lossless)
            frame_bytes = self.frame_size_bytes
            with open(self._filepath, "rb") as src:
                src.seek(TOTAL_HEADER_SIZE + start * frame_bytes)
                remaining = new_count * frame_bytes
                chunk_size = 1024 * 1024  # 1 MB chunks
                while remaining > 0:
                    to_read = min(chunk_size, remaining)
                    data = src.read(to_read)
                    if not data:
                        break
                    out.write(data)
                    remaining -= len(data)

            # Write timestamps for the trimmed range if present
            if self._timestamps is not None:
                trimmed_ts = np.array(self._timestamps[start:end + 1], dtype=np.int64)
                out.write(trimmed_ts.tobytes())

        return new_count

    def __repr__(self) -> str:
        return (
            f"SERFile({self._filepath.name!r}, "
            f"{self._width}x{self._height}, "
            f"{self._color_id.display_name}, "
            f"{self._pixel_depth}bit, "
            f"{self._frame_count} frames)"
        )
