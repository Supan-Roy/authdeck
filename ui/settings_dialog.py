from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """Settings dialog for theme and backup actions."""

    theme_changed = pyqtSignal(str)
    export_requested = pyqtSignal()
    import_requested = pyqtSignal()
    pin_setup_requested = pyqtSignal()
    pin_remove_requested = pyqtSignal()
    pin_forgot_requested = pyqtSignal()
    update_requested = pyqtSignal()
    about_requested = pyqtSignal()

    def __init__(self, current_theme: str, pin_enabled: bool, parent=None) -> None:
        super().__init__(parent)
        self._theme = current_theme.lower()
        self._pin_enabled = pin_enabled
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(460, 320)

        root_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.theme_combo = QComboBox(self)
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(current_theme.capitalize())
        self.theme_combo.currentTextChanged.connect(self._emit_theme)
        form_layout.addRow("Theme", self.theme_combo)

        self.export_button = QPushButton("Export Backup", self)
        self.export_button.clicked.connect(self.export_requested.emit)
        form_layout.addRow("", self.export_button)

        self.import_button = QPushButton("Import Backup", self)
        self.import_button.clicked.connect(self.import_requested.emit)
        form_layout.addRow("", self.import_button)

        self.pin_status_label = QLabel(self)
        self.pin_status_label.setObjectName("pinStatus")
        form_layout.addRow("PIN Lock", self.pin_status_label)

        self.pin_setup_button = QPushButton(self)
        self.pin_setup_button.clicked.connect(self.pin_setup_requested.emit)
        form_layout.addRow("", self.pin_setup_button)

        self.pin_remove_button = QPushButton("Remove PIN", self)
        self.pin_remove_button.clicked.connect(self.pin_remove_requested.emit)
        form_layout.addRow("", self.pin_remove_button)

        self.pin_forgot_button = QPushButton("Forgot PIN (Wipe All Accounts)", self)
        self.pin_forgot_button.clicked.connect(self.pin_forgot_requested.emit)
        form_layout.addRow("", self.pin_forgot_button)

        root_layout.addLayout(form_layout)

        footer_layout = QHBoxLayout()
        self.update_button = QPushButton("Check for Updates", self)
        self.update_button.setObjectName("updateMiniButton")
        self.update_button.clicked.connect(self.update_requested.emit)
        footer_layout.addWidget(self.update_button, 0)

        self.about_button = QPushButton("About", self)
        self.about_button.setObjectName("aboutMiniButton")
        self.about_button.clicked.connect(self.about_requested.emit)
        footer_layout.addWidget(self.about_button, 0)
        footer_layout.addStretch(1)

        close_button = QPushButton("Close", self)
        close_button.setObjectName("closeMiniButton")
        close_button.clicked.connect(self.reject)
        footer_layout.addWidget(close_button, 0)
        root_layout.addLayout(footer_layout)

        self._update_pin_controls()
        self._apply_theme(self._theme)

    def _emit_theme(self, selected_theme: str) -> None:
        self._theme = selected_theme.lower()
        self._apply_theme(self._theme)
        self.theme_changed.emit(self._theme)

    def set_pin_enabled(self, is_enabled: bool) -> None:
        self._pin_enabled = is_enabled
        self._update_pin_controls()

    def _update_pin_controls(self) -> None:
        self.pin_status_label.setText("Enabled" if self._pin_enabled else "Not configured")
        self.pin_setup_button.setText("Change PIN" if self._pin_enabled else "Set 4-digit PIN")
        self.pin_remove_button.setEnabled(self._pin_enabled)

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog { background-color: #ffffff; color: #1f2a35; border: 1px solid #d7e1eb; border-radius: 12px; }
                QLabel { color: #1f2a35; font-weight: 600; }
                QComboBox, QPushButton {
                    background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 9px;
                    padding: 7px 10px; color: #1f2a35;
                }
                QLabel#pinStatus { color: #255ea8; font-weight: 700; }
                QComboBox::drop-down { border: none; }
                QComboBox QAbstractItemView {
                    background-color: #ffffff;
                    color: #1f2a35;
                    border: 1px solid #cfddea;
                    selection-background-color: #e8f0fb;
                    selection-color: #1f2a35;
                    outline: 0;
                }
                QPushButton:hover { background-color: #e5edf8; }
                QPushButton#updateMiniButton, QPushButton#aboutMiniButton, QPushButton#closeMiniButton {
                    padding: 6px 12px;
                    min-width: 72px;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; color: #eef4ff; border: 1px solid #22344d; border-radius: 12px; }
                QLabel { color: #e6eefc; font-weight: 600; }
                QComboBox, QPushButton {
                    background-color: #132135; border: 1px solid #2c4870; border-radius: 9px;
                    padding: 7px 10px; color: #eef4ff;
                }
                QLabel#pinStatus { color: #8fbaff; font-weight: 700; }
                QComboBox::drop-down { border: none; }
                QComboBox QAbstractItemView {
                    background-color: #05070a;
                    color: #e6eefc;
                    border: 1px solid #2c4870;
                    selection-background-color: #1b314d;
                    selection-color: #eef4ff;
                    outline: 0;
                }
                QPushButton:hover { background-color: #1b314d; }
                QPushButton#updateMiniButton, QPushButton#aboutMiniButton, QPushButton#closeMiniButton {
                    padding: 6px 12px;
                    min-width: 72px;
                }
                """
            )
