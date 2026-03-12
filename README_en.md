**English** | [中文](README.md)

# AstroSER Player

Cross-platform SER astronomical video player, designed for SER format videos captured by planetary cameras (ZWO ASI, etc.).

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PySide6](https://img.shields.io/badge/UI-PySide6-green)
![OpenGL](https://img.shields.io/badge/Render-OpenGL-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Full SER format support** — MONO / Bayer (RGGB/GRBG/GBRG/BGGR) / RGB / BGR, 8–16 bit
- **OpenGL GPU accelerated rendering** — Brightness/contrast/gamma adjustments run entirely in GPU shaders; automatic CPU fallback when GPU is unavailable
- **Solar false color** — H-alpha style warm toning for solar observation
- **Real-time image adjustments** — Brightness, contrast, gamma sliders with auto histogram stretch
- **Frame statistics & histogram** — Min/Max/Mean/Std/Sharpness with live histogram display
- **ROI selection** — Draggable rectangle region with independent statistics
- **Smooth playback** — Frame skipping, LRU cache, background prefetch, adaptive time budget
- **10 languages** — 中文, English, 日本語, 한국어, Français, Deutsch, Español, Português, Русский, العربية
- **Drag & drop** — Drop `.ser` files directly to play

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Space` | Play / Pause |
| `←` `→` | Step backward / forward |
| `Home` `End` | Jump to first / last frame |
| `+` `-` | Zoom in / out |
| `Ctrl+0` | Fit to window |
| `Ctrl+1` `Ctrl+2` | 100% / 200% zoom |
| `Ctrl+O` | Open file |
| `Ctrl+R` | Toggle ROI |
| `Ctrl+S` | Toggle solar colorize |
| Double-click | Fit to window |
| Scroll wheel | Zoom |

## Installation

### Download Executable

Go to the [Releases](https://github.com/bulb888/AstroSER-Player/releases) page and download `AstroSER Player.exe` — double-click to run (Windows 10/11).

### Run from Source

```bash
# Clone the repository
git clone https://github.com/bulb888/AstroSER-Player.git
cd AstroSER-Player

# Install dependencies
pip install PySide6 numpy scipy PyOpenGL

# Run
python run.py
```

## Build

```bash
pip install pyinstaller
pyinstaller --windowed --onefile --name "AstroSER Player" \
    --icon astroser/resources/icons/app_icon.ico \
    --add-data "astroser/resources/icons;astroser/resources/icons" \
    --hidden-import OpenGL.platform.win32 \
    --hidden-import OpenGL.GL \
    run.py
```

## Architecture

```
astroser/
├── core/
│   ├── ser_parser.py        # SER file parser (memmap frame access)
│   ├── frame_pipeline.py    # Frame pipeline (debayer → LUT → QImage)
│   ├── debayer.py           # Bayer demosaicing (scipy / NumPy)
│   ├── playback_engine.py   # QTimer playback state machine
│   └── statistics.py        # Frame statistics & sharpness
├── ui/
│   ├── gl_viewer_widget.py  # OpenGL renderer (GLSL shaders)
│   ├── viewer_widget.py     # Software renderer (QGraphicsView)
│   ├── main_window.py       # Main window
│   ├── transport_bar.py     # Playback controls
│   ├── adjustments_panel.py # Image adjustment panel
│   ├── histogram_widget.py  # Histogram
│   ├── statistics_panel.py  # Statistics display
│   └── i18n.py              # Internationalization (10 languages)
└── resources/icons/         # App icon
```

## Dependencies

| Package | Purpose |
|---------|---------|
| PySide6 ≥ 6.5 | GUI framework |
| NumPy ≥ 1.24 | Frame data processing |
| SciPy ≥ 1.10 | Fast demosaicing convolution (optional, falls back to pure NumPy) |
| PyOpenGL ≥ 3.1 | GPU rendering (optional, falls back to CPU software rendering) |

## Author

**國产电灯泡** ([@bulb888](https://github.com/bulb888))

## License

MIT
