"""SER file metadata dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QPushButton, QGroupBox,
)

from ..core.ser_parser import SERFile


class FileInfoDialog(QDialog):
    """Dialog showing SER file metadata."""

    def __init__(self, ser_file: SERFile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SER \u6587\u4ef6\u4fe1\u606f")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        info = ser_file.info_dict()

        # File info group
        file_group = QGroupBox("\u6587\u4ef6")
        file_form = QFormLayout(file_group)
        file_form.addRow("\u8def\u5f84:", QLabel(info["filepath"]))
        file_form.addRow("\u603b\u5e27\u6570:", QLabel(str(info["frame_count"])))
        file_form.addRow("\u5305\u542b\u65f6\u95f4\u6233:", QLabel("\u662f" if info["has_timestamps"] else "\u5426"))
        layout.addWidget(file_group)

        # Image info group
        img_group = QGroupBox("\u56fe\u50cf")
        img_form = QFormLayout(img_group)
        img_form.addRow("\u5206\u8fa8\u7387:", QLabel(f"{info['width']} \u00d7 {info['height']}"))
        img_form.addRow("\u50cf\u7d20\u4f4d\u6df1:", QLabel(f"{info['pixel_depth']} bit"))
        img_form.addRow("\u989c\u8272\u683c\u5f0f:", QLabel(info["color_id"]))
        img_form.addRow("\u5b57\u8282\u5e8f:", QLabel("\u5c0f\u7aef" if info["little_endian"] else "\u5927\u7aef"))
        img_form.addRow("\u5e27\u5927\u5c0f:", QLabel(f"{info['frame_size_bytes']:,} \u5b57\u8282"))
        layout.addWidget(img_group)

        # Observation info group
        obs_group = QGroupBox("\u89c2\u6d4b\u4fe1\u606f")
        obs_form = QFormLayout(obs_group)
        obs_form.addRow("\u89c2\u6d4b\u8005:", QLabel(info["observer"] or "-"))
        obs_form.addRow("\u76f8\u673a:", QLabel(info["instrument"] or "-"))
        obs_form.addRow("\u671b\u8fdc\u955c:", QLabel(info["telescope"] or "-"))
        obs_form.addRow("\u672c\u5730\u65f6\u95f4:", QLabel(info["datetime_local"] or "-"))
        obs_form.addRow("UTC\u65f6\u95f4:", QLabel(info["datetime_utc"] or "-"))
        layout.addWidget(obs_group)

        close_btn = QPushButton("\u5173\u95ed")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
