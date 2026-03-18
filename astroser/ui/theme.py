"""Clean modern dark theme for AstroSER Player.

Neutral dark gray tones, subtle blue accent, no gimmicks.
Focused on readability and professional feel.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication


# ── Neutral palette ────────────────────────────────────────────
BG_0 = "#1a1a1a"   # darkest (viewer bg)
BG_1 = "#222222"   # main window
BG_2 = "#2a2a2a"   # panels / groups
BG_3 = "#333333"   # elevated (buttons, inputs)
BG_4 = "#3c3c3c"   # hover
BG_5 = "#1e1e1e"   # pressed

BORDER   = "#3a3a3a"
BORDER_F = "#555555"  # focus / hover border

TEXT_0 = "#eeeeee"  # bright
TEXT_1 = "#cccccc"  # normal
TEXT_2 = "#888888"  # secondary
TEXT_3 = "#444444"  # disabled

ACCENT   = "#4c9fe6"  # calm blue
ACCENT_H = "#6cb3f0"  # hover
ACCENT_D = "#2a5a8a"  # dimmed bg


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,         QColor(BG_1))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_1))
    p.setColor(QPalette.ColorRole.Base,            QColor(BG_0))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_2))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(BG_3))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT_0))
    p.setColor(QPalette.ColorRole.Text,            QColor(TEXT_1))
    p.setColor(QPalette.ColorRole.Button,          QColor(BG_2))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_1))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(TEXT_0))
    p.setColor(QPalette.ColorRole.Link,            QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT_0))
    p.setColor(QPalette.ColorRole.Light,           QColor(BG_3))
    p.setColor(QPalette.ColorRole.Midlight,        QColor(BG_2))
    p.setColor(QPalette.ColorRole.Dark,            QColor(BG_0))
    p.setColor(QPalette.ColorRole.Mid,             QColor(BG_2))
    p.setColor(QPalette.ColorRole.Shadow,          QColor("#000000"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(TEXT_3))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(TEXT_3))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_3))
    app.setPalette(p)

    font = QFont("Segoe UI", 9)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    app.setStyleSheet(f"""
        QToolTip {{
            color: {TEXT_0};
            background: {BG_3};
            border: 1px solid {BORDER_F};
            padding: 4px 6px;
        }}

        QMenuBar {{
            background: {BG_1};
            border-bottom: 1px solid {BORDER};
        }}
        QMenuBar::item:selected {{
            background: {BG_4};
        }}
        QMenu {{
            background: {BG_2};
            border: 1px solid {BORDER_F};
            padding: 4px 0;
        }}
        QMenu::item {{
            padding: 5px 24px 5px 16px;
        }}
        QMenu::item:selected {{
            background: {ACCENT_D};
        }}
        QMenu::separator {{
            height: 1px;
            background: {BORDER};
            margin: 3px 8px;
        }}

        QPushButton {{
            background: {BG_3};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 4px 12px;
        }}
        QPushButton:hover {{
            background: {BG_4};
            border-color: {BORDER_F};
        }}
        QPushButton:pressed {{
            background: {BG_5};
        }}
        QPushButton:disabled {{
            color: {TEXT_3};
        }}
        QPushButton:checked {{
            background: {ACCENT_D};
            border-color: {ACCENT};
            color: {TEXT_0};
        }}

        QGroupBox {{
            background: {BG_2};
            border: 1px solid {BORDER};
            border-radius: 6px;
            margin-top: 12px;
            padding: 14px 8px 8px 8px;
            font-weight: 600;
            font-size: 11px;
            color: {TEXT_2};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: {ACCENT};
        }}

        /* --- Right panel form styling --- */
        QScrollArea QFormLayout QLabel {{
            font-size: 11px;
        }}

        QComboBox {{
            background: {BG_3};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 3px 8px;
            min-height: 20px;
        }}
        QComboBox:hover {{
            border-color: {BORDER_F};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 18px;
        }}
        QComboBox QAbstractItemView {{
            background: {BG_2};
            border: 1px solid {BORDER_F};
            selection-background-color: {ACCENT_D};
        }}

        QCheckBox::indicator {{
            width: 15px; height: 15px;
            border: 1px solid {BORDER_F};
            border-radius: 3px;
            background: {BG_3};
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT};
            border-color: {ACCENT};
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {BORDER};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT};
            width: 12px; height: 12px;
            margin: -4px 0;
            border-radius: 6px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT};
            border-radius: 2px;
        }}

        QScrollArea {{
            background: {BG_1};
            border: none;
            border-left: 1px solid {BORDER};
        }}
        QScrollArea > QWidget > QWidget {{
            background: {BG_1};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 7px;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER_F};
            border-radius: 3px;
            min-height: 24px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

        QSplitter::handle {{ background: {BORDER}; width: 1px; }}

        QStatusBar {{
            background: {BG_0};
            border-top: 1px solid {BORDER};
            font-size: 12px;
        }}
        QStatusBar QLabel {{
            color: {TEXT_2};
            font-size: 12px;
        }}
    """)
