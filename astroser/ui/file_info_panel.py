"""SER file info panel for the right sidebar."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QGroupBox,
)

from ..core.ser_parser import SERFile
from .i18n import tr, I18n


class FileInfoPanel(QWidget):
    """Inline panel showing SER file metadata."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        I18n.instance().language_changed.connect(self.retranslate)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # File info group
        self._img_group = QGroupBox()
        self._img_form = QFormLayout(self._img_group)
        self._img_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._img_form.setVerticalSpacing(3)

        self._file_label = QLabel("-")
        self._file_label.setWordWrap(True)
        self._dim_label = QLabel("-")
        self._depth_label = QLabel("-")
        self._color_label = QLabel("-")
        self._frames_label = QLabel("-")
        self._size_label = QLabel("-")

        self._img_row_labels = []
        for val_label in (self._file_label, self._dim_label, self._depth_label,
                          self._color_label, self._frames_label, self._size_label):
            rl = QLabel()
            self._img_row_labels.append(rl)
            self._img_form.addRow(rl, val_label)

        layout.addWidget(self._img_group)

        # Observation group
        self._obs_group = QGroupBox()
        self._obs_form = QFormLayout(self._obs_group)
        self._obs_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._obs_form.setVerticalSpacing(3)

        self._observer_label = QLabel("-")
        self._camera_label = QLabel("-")
        self._telescope_label = QLabel("-")
        self._time_local_label = QLabel("-")
        self._time_utc_label = QLabel("-")

        self._obs_row_labels = []
        for val_label in (self._observer_label, self._camera_label, self._telescope_label,
                          self._time_local_label, self._time_utc_label):
            rl = QLabel()
            self._obs_row_labels.append(rl)
            self._obs_form.addRow(rl, val_label)

        layout.addWidget(self._obs_group)
        self.retranslate()

    def retranslate(self) -> None:
        self._img_group.setTitle(tr("group_file_info"))
        img_keys = ["info_file", "info_resolution", "info_depth",
                    "info_format", "info_total_frames", "info_frame_size"]
        for label, key in zip(self._img_row_labels, img_keys):
            label.setText(tr(key))

        self._obs_group.setTitle(tr("group_observation"))
        obs_keys = ["info_observer", "info_camera", "info_telescope",
                    "info_local_time", "info_utc"]
        for label, key in zip(self._obs_row_labels, obs_keys):
            label.setText(tr(key))

    def update_info(self, ser_file: SERFile) -> None:
        info = ser_file.info_dict()
        self._file_label.setText(ser_file.filepath.name)
        self._dim_label.setText(f"{info['width']} \u00d7 {info['height']}")
        self._depth_label.setText(f"{info['pixel_depth']} bit")
        self._color_label.setText(info["color_id"])
        self._frames_label.setText(str(info["frame_count"]))
        self._size_label.setText(tr("info_bytes").format(info["frame_size_bytes"]))

        self._observer_label.setText(info["observer"] or "-")
        self._camera_label.setText(info["instrument"] or "-")
        self._telescope_label.setText(info["telescope"] or "-")
        self._time_local_label.setText(info["datetime_local"] or "-")
        self._time_utc_label.setText(info["datetime_utc"] or "-")

    def clear(self) -> None:
        for label in (self._file_label, self._dim_label, self._depth_label,
                      self._color_label, self._frames_label, self._size_label,
                      self._observer_label, self._camera_label, self._telescope_label,
                      self._time_local_label, self._time_utc_label):
            label.setText("-")
