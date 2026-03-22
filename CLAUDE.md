# AstroSER Player

跨平台天文 SER 视频播放器 + 分析工具。作者：國产电灯泡

## 技术栈

- **Python 3.10+** / PySide6 (Qt6) / OpenGL 3.3 / NumPy / SciPy
- **GPU 渲染**: GLSL shader 实现 Bayer demosaic、亮度/对比度/伽马调整
- **MP4 导出**: imageio-ffmpeg (H.264 baseline + yuv420p)
- **i18n**: 10 语言（中/英/俄/日/法/德/西/葡/韩/阿）

## 启动方式

```bash
# 直接运行
python run.py

# 或
python -c "
import sys
from PySide6.QtWidgets import QApplication
from astroser.ui.main_window import MainWindow
from astroser.ui.theme import apply_dark_theme
app = QApplication(sys.argv)
apply_dark_theme(app)
win = MainWindow()
win.show()
sys.exit(app.exec())
"
```

注意：主题函数是 `apply_dark_theme`，不是 `apply_theme`。

## 打包

```bash
pyinstaller astroser_player.spec
```

输出: `dist/AstroSER Player/AstroSER Player.exe`

## 项目结构

```
astroser/
├── core/                # 核心逻辑（无 UI 依赖）
│   ├── ser_parser.py        # SER 格式解析，内存映射帧访问
│   ├── frame_pipeline.py    # 帧处理管线，LRU 缓存，预取
│   ├── debayer.py           # Bayer demosaic（CPU 路径）
│   ├── image_adjust.py      # 亮度/对比度/伽马 LUT
│   ├── playback_engine.py   # QTimer 播放控制
│   ├── statistics.py        # 帧统计（均值/标差/锐度）
│   ├── mp4_export.py        # MP4 导出（ffmpeg subprocess pipe）
│   ├── timestamp_analysis.py # 时间戳质量分析
│   ├── tracking_log.py      # space-tracker tracking.log 解析
│   └── delay_analysis.py    # 闭环延迟 + 赤道仪响应分析
├── ui/                  # 界面组件
│   ├── main_window.py       # 主窗口（菜单/布局/信号连接）
│   ├── gl_viewer_widget.py  # OpenGL 查看器 + GLSL shader
│   ├── viewer_widget.py     # QGraphicsView 软件回退查看器
│   ├── transport_bar.py     # 播放控制栏 + 裁切
│   ├── trim_timeline.py     # 可视化时间线 + 拖拽 in/out
│   ├── adjustments_panel.py # 调整滑块面板
│   ├── histogram_widget.py  # 直方图
│   ├── file_info_panel.py   # 文件信息面板
│   ├── statistics_panel.py  # 统计面板
│   ├── chart_widget.py      # 通用 QPainter 折线图
│   ├── timestamp_panel.py   # 时间戳分析面板
│   ├── tracking_panel.py    # 跟踪数据叠加面板
│   ├── mount_panel.py       # 赤道仪响应面板
│   ├── lucky_panel.py       # Lucky 选帧面板
│   ├── roi_selector.py      # ROI 选区
│   ├── theme.py             # 暗色主题
│   └── i18n.py              # 国际化字符串注册表
├── resources/icons/     # 图标资源
├── app.py               # 入口点
└── __init__.py
```

## 代码规范

- **PySide6**，不是 PyQt6（信号/槽语法不同）
- QPen 不支持关键字参数，用 `pen = QPen(...); pen.setCapStyle(...)` 分步设置
- `setEnabled()` 参数必须是 `bool`，不能传 list 等 truthy 值
- 图表用 QPainter 手绘（不用 matplotlib），避免打包体积膨胀
- i18n 字符串在 `i18n.py` 的 `_STRINGS` 字典统一管理，每个 key 需要 10 种语言
- 右侧面板样式：monospace Cascadia Mono，12px，weight 500，#e0e0e0 值标签

## 依赖

```
PySide6>=6.5
numpy>=1.24
scipy>=1.10
PyOpenGL>=3.1
imageio-ffmpeg>=0.4
```

## Git 仓库

- 远程: https://github.com/bulb888/AstroSER-Player
- 主分支: master
- 提交信息不加 Co-Authored-By
