[English](README_en.md) | **中文**

# AstroSER Player

跨平台 SER 天文视频文件播放器，专为行星相机（ZWO ASI 等）拍摄的 SER 格式视频设计。


## 功能

- **完整 SER 格式支持** — MONO / Bayer (RGGB/GRBG/GBRG/BGGR) / RGB / BGR，8-16bit
- **OpenGL GPU 加速渲染** — 亮度/对比度/Gamma 调整全部在 GPU 着色器中完成，无 GPU 时自动回退 CPU 软渲染
- **太阳假彩色** — H-alpha 风格暖色调着色，适合太阳观测
- **实时图像调整** — 亮度、对比度、Gamma 滑块，自动直方图拉伸
- **帧统计与直方图** — Min/Max/Mean/Std/锐度，实时直方图显示
- **ROI 区域选择** — 可拖拽矩形区域，独立统计
- **流畅播放** — 帧跳跃、LRU 缓存、后台预取、自适应时间预算
- **10 种语言** — 中文、English、日本語、한국어、Français、Deutsch、Español、Português、Русский、العربية
- **拖放打开** — 直接拖入 .ser 文件即可播放

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Space` | 播放 / 暂停 |
| `←` `→` | 逐帧后退 / 前进 |
| `Home` `End` | 跳到首帧 / 末帧 |
| `+` `-` | 放大 / 缩小 |
| `Ctrl+0` | 适应窗口 |
| `Ctrl+1` `Ctrl+2` | 100% / 200% 缩放 |
| `Ctrl+O` | 打开文件 |
| `Ctrl+R` | 切换 ROI |
| `Ctrl+S` | 切换太阳着色 |
| 双击 | 适应窗口 |
| 滚轮 | 缩放 |

## 安装与运行

### 下载可执行文件

前往 [Releases](https://github.com/bulb888/AstroSER-Player/releases) 页面下载 `AstroSER Player.exe`，双击即可运行（Windows 10/11）。

### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/bulb888/AstroSER-Player.git
cd AstroSER-Player

# 安装依赖
pip install PySide6 numpy scipy PyOpenGL

# 运行
python run.py
```

## 打包

```bash
pip install pyinstaller
pyinstaller --windowed --onefile --name "AstroSER Player" \
    --icon astroser/resources/icons/app_icon.ico \
    --add-data "astroser/resources/icons;astroser/resources/icons" \
    --hidden-import OpenGL.platform.win32 \
    --hidden-import OpenGL.GL \
    run.py
```

## 技术架构

```
astroser/
├── core/
│   ├── ser_parser.py        # SER 文件解析（memmap 帧访问）
│   ├── frame_pipeline.py    # 帧处理管线（debayer → LUT → QImage）
│   ├── debayer.py           # Bayer 去马赛克（scipy / NumPy）
│   ├── playback_engine.py   # QTimer 播放状态机
│   └── statistics.py        # 帧统计与锐度评估
├── ui/
│   ├── gl_viewer_widget.py  # OpenGL 渲染器（GLSL 着色器）
│   ├── viewer_widget.py     # 软件渲染备选（QGraphicsView）
│   ├── main_window.py       # 主窗口
│   ├── transport_bar.py     # 播放控制条
│   ├── adjustments_panel.py # 图像调整面板
│   ├── histogram_widget.py  # 直方图
│   ├── statistics_panel.py  # 统计信息
│   └── i18n.py              # 多语言支持
└── resources/icons/         # 应用图标
```

## 依赖

| 包 | 用途 |
|----|------|
| PySide6 ≥ 6.5 | GUI 框架 |
| NumPy ≥ 1.24 | 帧数据处理 |
| SciPy ≥ 1.10 | 快速去马赛克卷积（可选，无则用纯 NumPy） |
| PyOpenGL ≥ 3.1 | GPU 渲染（可选，无则用 CPU 软渲染） |

## 作者

**國产电灯泡** ([@bulb888](https://github.com/bulb888))

## License

MIT
