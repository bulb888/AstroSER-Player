"""Dark theme for AstroSER Player."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def apply_dark_theme(app: QApplication) -> None:
    """Apply a dark Fusion theme suitable for astronomy software."""
    app.setStyle("Fusion")

    palette = QPalette()

    # Base colors
    dark = QColor(30, 30, 30)
    mid_dark = QColor(42, 42, 42)
    mid = QColor(55, 55, 55)
    light = QColor(80, 80, 80)
    text_color = QColor(210, 210, 210)
    bright_text = QColor(255, 255, 255)
    accent = QColor(60, 140, 180)
    disabled_text = QColor(120, 120, 120)

    palette.setColor(QPalette.ColorRole.Window, mid_dark)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, dark)
    palette.setColor(QPalette.ColorRole.AlternateBase, mid_dark)
    palette.setColor(QPalette.ColorRole.ToolTipBase, mid)
    palette.setColor(QPalette.ColorRole.ToolTipText, text_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, mid_dark)
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.BrightText, bright_text)
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, bright_text)
    palette.setColor(QPalette.ColorRole.Light, light)
    palette.setColor(QPalette.ColorRole.Midlight, mid)
    palette.setColor(QPalette.ColorRole.Dark, dark)
    palette.setColor(QPalette.ColorRole.Mid, mid)
    palette.setColor(QPalette.ColorRole.Shadow, QColor(0, 0, 0))

    # Disabled state
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)

    app.setPalette(palette)

    # Additional stylesheet tweaks
    app.setStyleSheet("""
        QToolTip {
            color: #d2d2d2;
            background-color: #373737;
            border: 1px solid #505050;
            padding: 4px;
        }
        QGroupBox {
            border: 1px solid #505050;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 8px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QSlider::groove:horizontal {
            height: 4px;
            background: #505050;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #3c8cb4;
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        QSlider::sub-page:horizontal {
            background: #3c8cb4;
            border-radius: 2px;
        }
        QStatusBar {
            border-top: 1px solid #505050;
        }
    """)
