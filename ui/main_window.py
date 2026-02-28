from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, QStandardPaths, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QClipboard, QCloseEvent, QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSystemTrayIcon,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.storage import StorageManager
from core.totp_manager import TOTPManager
from ui.scan_overlay import ScanOverlay
from ui.settings_dialog import SettingsDialog


def _format_service_name(name: Any) -> str:
    text = str(name or "Account")
    if len(text) <= 30:
        return text
    return f"{text[:30]}..."


MAX_TRAY_COPY_ITEMS = 25


class AccountItemWidget(QWidget):
    """Visual widget for an account in the sidebar list."""

    code_clicked = pyqtSignal()

    def __init__(self, account: dict[str, Any], parent=None) -> None:
        super().__init__(parent)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(6)

        self.name_label = QLabel(_format_service_name(account.get("name", "Account")), self)
        self.name_label.setObjectName("accountName")
        root_layout.addWidget(self.name_label)

        self.account_label = QLabel(account.get("account", ""), self)
        self.account_label.setObjectName("accountUser")
        root_layout.addWidget(self.account_label)

        self.code_label = QLabel("------", self)
        self.code_label.setObjectName("accountCode")
        self.code_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.code_label.mousePressEvent = self._on_code_label_pressed
        root_layout.addWidget(self.code_label)

        self.progress = SmoothProgressBar(self)
        self.progress.setObjectName("secondaryProgress")
        self.progress.setTextVisible(False)
        self.progress.setMaximum(30)
        self.progress.setValue(0)
        self.progress.setFixedHeight(20)
        root_layout.addWidget(self.progress)

    def update_values(self, account: dict[str, Any], code: str, remaining: int) -> None:
        period = int(account.get("period", 30) or 30)
        self.name_label.setText(_format_service_name(account.get("name", "Account")))
        self.account_label.setText(account.get("account", ""))
        self.code_label.setText(code)
        self.progress.setMaximum(period)
        self.progress.set_smooth_value(remaining)

    def _on_code_label_pressed(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.code_clicked.emit()
            event.accept()
            return
        QLabel.mousePressEvent(self.code_label, event)


class SmoothProgressBar(QProgressBar):
    """Progress bar with gentle value animation for smoother visual updates."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._animation = QPropertyAnimation(self, b"value", self)
        self._animation.setDuration(420)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_smooth_value(self, value: int) -> None:
        target = max(0, min(value, self.maximum()))
        current = self.value()

        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()

        # On period reset (e.g., 1 -> 30), set immediately.
        if target > current + 2:
            self.setValue(target)
            return

        self._animation.setStartValue(current)
        self._animation.setEndValue(target)
        self._animation.start()


class ReorderableAccountList(QListWidget):
    """Account list with drag-drop row reordering support."""

    rows_moved = pyqtSignal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._drag_start_row = -1

    def startDrag(self, supported_actions) -> None:
        self._drag_start_row = self.currentRow()
        super().startDrag(supported_actions)

    def dropEvent(self, event) -> None:
        original_row = self._drag_start_row
        super().dropEvent(event)
        target_row = self.currentRow()
        if original_row >= 0 and target_row >= 0 and original_row != target_row:
            self.rows_moved.emit(original_row, target_row)
        self._drag_start_row = -1


class CircularTimerWidget(QWidget):
    """Circular countdown timer for the main panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._period = 30
        self._remaining = 0
        self._bg_color = QColor("#1f3047")
        self._progress_color = QColor("#7eb4ff")
        self._text_color = QColor("#dce8fa")
        self.setMinimumSize(180, 180)
        self.setMaximumSize(240, 240)

    def set_countdown(self, period: int, remaining: int) -> None:
        self._period = max(1, period)
        self._remaining = max(0, min(remaining, self._period))
        self.update()

    def set_theme(self, theme: str) -> None:
        if theme == "light":
            self._bg_color = QColor("#d2deeb")
            self._progress_color = QColor("#5b8cc4")
            self._text_color = QColor("#1f2a35")
        else:
            self._bg_color = QColor("#1f3047")
            self._progress_color = QColor("#7eb4ff")
            self._text_color = QColor("#dce8fa")
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2
        diameter = min(self.width(), self.height()) - 18
        radius = diameter / 2
        rect_x = center_x - radius
        rect_y = center_y - radius

        base_pen = QPen(self._bg_color, 10)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(base_pen)
        painter.drawArc(int(rect_x), int(rect_y), int(diameter), int(diameter), 0, 360 * 16)

        ratio = self._remaining / float(self._period)
        span_angle = int(-360 * ratio * 16)
        progress_pen = QPen(self._progress_color, 10)
        progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(int(rect_x), int(rect_y), int(diameter), int(diameter), 90 * 16, span_angle)

        painter.setPen(self._text_color)
        font = painter.font()
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._remaining}s")


class AddAccountChoiceDialog(QDialog):
    """Polished choice dialog for adding accounts."""

    def __init__(self, theme: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Account")
        self.setModal(True)
        self.resize(420, 220)
        self.choice: str | None = None

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(12)

        title = QLabel("How would you like to add an account?", self)
        title.setObjectName("choiceTitle")
        root_layout.addWidget(title)

        self.scan_button = QPushButton("Scan QR Code", self)
        self.scan_button.clicked.connect(self._choose_scan)
        root_layout.addWidget(self.scan_button)

        self.manual_button = QPushButton("Manual Entry", self)
        self.manual_button.clicked.connect(self._choose_manual)
        root_layout.addWidget(self.manual_button)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        root_layout.addWidget(self.cancel_button)

        self._apply_theme(theme)

    def _choose_scan(self) -> None:
        self.choice = "scan"
        self.accept()

    def _choose_manual(self) -> None:
        self.choice = "manual"
        self.accept()

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog { background-color: #ffffff; color: #1f2a35; border: 1px solid #d7e1eb; border-radius: 14px; }
                QLabel#choiceTitle { font-size: 15px; font-weight: 700; color: #1f2a35; }
                QPushButton {
                    background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 10px;
                    padding: 9px 14px; color: #1f2a35; font-weight: 600;
                }
                QPushButton:hover { background-color: #e4edf8; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; color: #f2f6ff; border: 1px solid #22344d; border-radius: 14px; }
                QLabel#choiceTitle { font-size: 15px; font-weight: 700; color: #f3f7ff; }
                QPushButton {
                    background-color: #132135; border: 1px solid #2c4870; border-radius: 10px;
                    padding: 9px 14px; color: #f1f6ff; font-weight: 700;
                }
                QPushButton:hover { background-color: #1b314d; }
                """
            )


class DeleteConfirmDialog(QDialog):
    """Themed destructive-action confirmation for account deletion."""

    def __init__(self, account_name: str, theme: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Delete Account")
        self.setModal(True)
        self.resize(430, 210)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(12)

        title = QLabel("Delete this account?", self)
        title.setObjectName("deleteTitle")
        root_layout.addWidget(title)

        details = QLabel(account_name or "Selected account", self)
        details.setObjectName("deleteDetails")
        root_layout.addWidget(details)

        warning = QLabel("This action cannot be undone.", self)
        warning.setObjectName("deleteWarning")
        root_layout.addWidget(warning)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.clicked.connect(self.accept)
        buttons_layout.addWidget(self.delete_button)

        root_layout.addStretch(1)
        root_layout.addLayout(buttons_layout)

        self.cancel_button.setDefault(True)
        self.cancel_button.setAutoDefault(True)
        self._apply_theme(theme)

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog { background-color: #ffffff; border: 1px solid #d7e1eb; border-radius: 12px; }
                QLabel#deleteTitle { font-size: 20px; font-weight: 800; color: #1f2a35; }
                QLabel#deleteDetails { font-size: 14px; font-weight: 700; color: #2f3d4d; }
                QLabel#deleteWarning { font-size: 13px; color: #b42318; }
                QPushButton {
                    background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 10px;
                    padding: 8px 14px; color: #1f2a35; font-weight: 700;
                }
                QPushButton:hover { background-color: #e4edf8; }
                QPushButton[text="Delete"] {
                    background-color: #ef4444; border: 1px solid #dc2626; color: #ffffff;
                }
                QPushButton[text="Delete"]:hover { background-color: #dc2626; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel#deleteTitle { font-size: 20px; font-weight: 800; color: #f3f7ff; }
                QLabel#deleteDetails { font-size: 14px; font-weight: 700; color: #a9bfdb; }
                QLabel#deleteWarning { font-size: 13px; color: #ff7575; }
                QPushButton {
                    background-color: #132135; border: 1px solid #2c4870; border-radius: 10px;
                    padding: 8px 14px; color: #f1f6ff; font-weight: 700;
                }
                QPushButton:hover { background-color: #1b314d; }
                QPushButton[text="Delete"] {
                    background-color: #b42318; border: 1px solid #ef4444; color: #ffffff;
                }
                QPushButton[text="Delete"]:hover { background-color: #dc2626; }
                """
            )


class PinConfirmDialog(QDialog):
    """Themed PIN prompt used for destructive actions like account deletion."""

    def __init__(self, theme: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Delete")
        self.setModal(True)
        self.resize(390, 220)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("Enter unlock PIN", self)
        title.setObjectName("pinConfirmTitle")
        root.addWidget(title)

        self.pin_input = QLineEdit(self)
        self.pin_input.setPlaceholderText("4-digit PIN")
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setMaxLength(4)
        root.addWidget(self.pin_input)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("pinCancelButton")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.ok_button = QPushButton("Verify", self)
        self.ok_button.setObjectName("pinVerifyButton")
        self.ok_button.setAutoDefault(True)
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)
        buttons.addWidget(self.ok_button)

        root.addLayout(buttons)
        self.pin_input.returnPressed.connect(self.ok_button.click)
        self._apply_theme(theme)

    def pin_value(self) -> str:
        return self.pin_input.text().strip()

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog { background-color: #ffffff; border: 1px solid #d7e1eb; border-radius: 12px; }
                QLabel#pinConfirmTitle { color: #1f2a35; font-size: 18px; font-weight: 800; }
                QLineEdit { background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 9px; padding: 8px 10px; color: #1f2a35; }
                QPushButton { background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 10px; padding: 8px 14px; color: #1f2a35; font-weight: 700; }
                QPushButton:hover { background-color: #e4edf8; }
                QPushButton#pinVerifyButton { background-color: #3f7cc8; border: 1px solid #2f67ad; color: #ffffff; }
                QPushButton#pinVerifyButton:hover { background-color: #336eb8; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel#pinConfirmTitle { color: #f3f7ff; font-size: 18px; font-weight: 800; }
                QLineEdit { background-color: #132135; border: 1px solid #2c4870; border-radius: 9px; padding: 8px 10px; color: #eef4ff; }
                QPushButton { background-color: #132135; border: 1px solid #2c4870; border-radius: 10px; padding: 8px 14px; color: #eef4ff; font-weight: 700; }
                QPushButton:hover { background-color: #1b314d; }
                QPushButton#pinVerifyButton { background-color: #2f67ad; border: 1px solid #4f89ce; color: #ffffff; }
                QPushButton#pinVerifyButton:hover { background-color: #3b76c1; }
                """
            )


class PinSetupDialog(QDialog):
    """Dialog to set or change a 4-digit PIN."""

    def __init__(self, theme: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set PIN")
        self.setModal(True)
        self.resize(360, 210)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.pin_input = QLineEdit(self)
        self.pin_input.setPlaceholderText("4 digits")
        self.pin_input.setMaxLength(4)
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("PIN", self.pin_input)

        self.confirm_input = QLineEdit(self)
        self.confirm_input.setPlaceholderText("Re-enter 4 digits")
        self.confirm_input.setMaxLength(4)
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Confirm", self.confirm_input)

        layout.addLayout(form)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("pinError")
        layout.addWidget(self.error_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._apply_theme(theme)

    def pin_value(self) -> str:
        return self.pin_input.text().strip()

    def _validate_and_accept(self) -> None:
        pin = self.pin_input.text().strip()
        confirm = self.confirm_input.text().strip()
        if len(pin) != 4 or not pin.isdigit():
            self.error_label.setText("PIN must be exactly 4 digits")
            return
        if pin != confirm:
            self.error_label.setText("PIN entries do not match")
            return
        self.accept()

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog { background-color: #ffffff; border: 1px solid #d7e1eb; border-radius: 12px; }
                QLabel { color: #1f2a35; }
                QLabel#pinError { color: #b42318; font-weight: 700; }
                QLineEdit { background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 8px; padding: 7px 10px; }
                QPushButton { background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 8px; padding: 7px 10px; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel { color: #eef4ff; }
                QLabel#pinError { color: #ff7b7b; font-weight: 700; }
                QLineEdit { background-color: #132135; border: 1px solid #2c4870; border-radius: 8px; padding: 7px 10px; color: #eef4ff; }
                QPushButton { background-color: #132135; border: 1px solid #2c4870; border-radius: 8px; padding: 7px 10px; color: #eef4ff; }
                """
            )


class PinUnlockDialog(QDialog):
    """Dialog to unlock app using configured 4-digit PIN."""

    forgot_requested = pyqtSignal()

    def __init__(self, theme: str, parent=None) -> None:
        super().__init__(parent)
        self.forgot_triggered = False
        self.setWindowTitle("Unlock AuthDeck")
        self.setModal(True)
        self.resize(370, 210)

        layout = QVBoxLayout(self)
        prompt = QLabel("Enter your 4-digit PIN to continue", self)
        layout.addWidget(prompt)

        self.pin_input = QLineEdit(self)
        self.pin_input.setPlaceholderText("••••")
        self.pin_input.setMaxLength(4)
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pin_input)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("pinError")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        self.forgot_button = QPushButton("Forgot PIN", self)
        self.forgot_button.setObjectName("forgotPinButton")
        self.forgot_button.setAutoDefault(False)
        self.forgot_button.setDefault(False)
        self.forgot_button.clicked.connect(self.forgot_requested.emit)
        buttons.addWidget(self.forgot_button)

        self.unlock_button = QPushButton("Unlock", self)
        self.unlock_button.setObjectName("unlockPinButton")
        self.unlock_button.setAutoDefault(True)
        self.unlock_button.setDefault(True)
        self.unlock_button.clicked.connect(self.accept)
        buttons.addWidget(self.unlock_button)

        self.pin_input.returnPressed.connect(self.unlock_button.click)

        layout.addLayout(buttons)
        self._apply_theme(theme)

    def pin_value(self) -> str:
        return self.pin_input.text().strip()

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.pin_input.selectAll()
        self.pin_input.setFocus()

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #f7fafe, stop:1 #ecf2fa);
                    border: 1px solid #c8d5e6;
                    border-radius: 12px;
                }
                QLabel { color: #1f3147; font-weight: 600; }
                QLabel#pinError { color: #b42318; font-weight: 700; }
                QLineEdit {
                    background-color: #edf3fa;
                    border: 1px solid #b7cbe3;
                    border-radius: 8px;
                    padding: 8px 10px;
                    color: #24364a;
                    font-weight: 700;
                }
                QLineEdit:focus { border-color: #7ea5d2; }
                QPushButton {
                    background-color: #e3ecf8;
                    border: 1px solid #b7cbe3;
                    border-radius: 9px;
                    padding: 8px 10px;
                    color: #21354b;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #d8e5f4; border-color: #9fb8d7; }
                QPushButton#unlockPinButton {
                    background-color: #3f7cc8;
                    border: 1px solid #2f67ad;
                    color: #ffffff;
                }
                QPushButton#unlockPinButton:hover { background-color: #336eb8; }
                QPushButton#forgotPinButton {
                    background-color: #eef3f9;
                    border: 1px solid #c2d2e6;
                    color: #4c6280;
                }
                QPushButton#forgotPinButton:hover { background-color: #e2ebf6; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel { color: #eef4ff; }
                QLabel#pinError { color: #ff7b7b; font-weight: 700; }
                QLineEdit { background-color: #132135; border: 1px solid #2c4870; border-radius: 8px; padding: 8px 10px; color: #eef4ff; }
                QPushButton { background-color: #132135; border: 1px solid #2c4870; border-radius: 8px; padding: 8px 10px; color: #eef4ff; }
                QPushButton:hover { background-color: #1b314d; border-color: #406a9f; }
                QPushButton#unlockPinButton {
                    background-color: #2f67ad;
                    border: 1px solid #4f89ce;
                    color: #ffffff;
                }
                QPushButton#unlockPinButton:hover { background-color: #3b76c1; }
                QPushButton#forgotPinButton { color: #9ab2d0; }
                """
            )


class BackupPasswordDialog(QDialog):
    """Themed password dialog used for encrypted backup export/import."""

    def __init__(self, theme: str, title: str, confirm: bool, parent=None) -> None:
        super().__init__(parent)
        self._confirm = confirm
        self._password = ""

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(420, 220 if confirm else 180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        prompt = QLabel(
            "Set a backup password (min 8 chars)" if confirm else "Enter backup password",
            self,
        )
        layout.addWidget(prompt)

        self.password_input = QLineEdit(self)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Backup password")
        layout.addWidget(self.password_input)

        self.confirm_input: QLineEdit | None = None
        if confirm:
            self.confirm_input = QLineEdit(self)
            self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_input.setPlaceholderText("Confirm password")
            layout.addWidget(self.confirm_input)

        self.error_label = QLabel("", self)
        self.error_label.setObjectName("backupPasswordError")
        layout.addWidget(self.error_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)

        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_button)

        self.continue_button = QPushButton("Continue", self)
        self.continue_button.setObjectName("backupContinueButton")
        self.continue_button.clicked.connect(self._validate_and_accept)
        buttons_layout.addWidget(self.continue_button)
        layout.addLayout(buttons_layout)

        self.password_input.returnPressed.connect(self._validate_and_accept)
        if self.confirm_input is not None:
            self.confirm_input.returnPressed.connect(self._validate_and_accept)

        self._apply_theme(theme)

    def password_value(self) -> str:
        return self._password

    def _validate_and_accept(self) -> None:
        password = self.password_input.text()
        if len(password) < 8:
            self.error_label.setText("Password must be at least 8 characters")
            return

        if self._confirm and self.confirm_input is not None and password != self.confirm_input.text():
            self.error_label.setText("Passwords do not match")
            return

        self._password = password
        self.accept()

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            self.setStyleSheet(
                """
                QDialog { background-color: #f6f9fd; border: 1px solid #c8d5e6; border-radius: 12px; }
                QLabel { color: #1f3147; font-weight: 600; }
                QLabel#backupPasswordError { color: #b42318; font-weight: 700; }
                QLineEdit {
                    background-color: #edf3fa;
                    border: 1px solid #b7cbe3;
                    border-radius: 8px;
                    padding: 7px 10px;
                    color: #24364a;
                }
                QLineEdit:focus { border-color: #7ea5d2; }
                QPushButton {
                    background-color: #e3ecf8;
                    border: 1px solid #b7cbe3;
                    border-radius: 9px;
                    padding: 7px 12px;
                    color: #21354b;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #d8e5f4; border-color: #9fb8d7; }
                QPushButton#backupContinueButton {
                    background-color: #3f7cc8;
                    border: 1px solid #2f67ad;
                    color: #ffffff;
                }
                QPushButton#backupContinueButton:hover { background-color: #336eb8; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel { color: #e8f0ff; font-weight: 600; }
                QLabel#backupPasswordError { color: #ff7b7b; font-weight: 700; }
                QLineEdit {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 8px;
                    padding: 7px 10px;
                    color: #e8f0ff;
                }
                QLineEdit:focus { border-color: #6ea8fe; }
                QPushButton {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 9px;
                    padding: 7px 12px;
                    color: #f1f6ff;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #1b314d; border-color: #406a9f; }
                QPushButton#backupContinueButton {
                    background-color: #2f67ad;
                    border: 1px solid #4f89ce;
                    color: #ffffff;
                }
                QPushButton#backupContinueButton:hover { background-color: #3b76c1; }
                """
            )


class MainWindow(QMainWindow):
    """Primary AuthDeck window with sidebar, code view, and settings."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AuthDeck")
        self.resize(1080, 680)

        if getattr(sys, "frozen", False):
            bundle_dir = Path(getattr(sys, "_MEIPASS", Path.cwd()))
            app_data_root = Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppDataLocation
                )
            )
            storage_path = app_data_root / "data" / "accounts.json"
            asset_dir = bundle_dir / "assets"
        else:
            base_dir = Path(__file__).resolve().parent.parent
            storage_path = base_dir / "data" / "accounts.json"
            asset_dir = base_dir / "assets"

        self._storage = StorageManager(storage_path)
        self._totp = TOTPManager()
        self._current_theme = self._storage.get_theme()
        self._force_close = False
        self._scan_active = False
        self._scan_overlay: ScanOverlay | None = None
        self.codes_menu: QMenu | None = None
        self._asset_dir = asset_dir
        self._visible_account_indices: list[int] = []
        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(self._reset_copy_button_feedback)
        self._copy_pulse_animation: QPropertyAnimation | None = None

        icon_path = asset_dir / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._apply_theme(self._current_theme, persist=False)
        self._setup_tray(icon_path)
        self._load_accounts_to_list()
        self._setup_timers()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self.top_logo_label = QLabel(self)
        self.top_logo_label.setObjectName("windowLogo")
        self.top_logo_label.setFixedSize(34, 34)
        top_logo_path = self._asset_dir / "icon.png"
        if top_logo_path.exists():
            pixmap = QPixmap(str(top_logo_path)).scaled(
                28,
                28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.top_logo_label.setPixmap(pixmap)
        top_bar.addWidget(self.top_logo_label)
        top_bar.addStretch(1)

        self.settings_button = QPushButton("Settings", self)
        self.settings_button.setObjectName("topSettingsButton")
        self.settings_button.clicked.connect(self._open_settings)
        top_bar.addWidget(self.settings_button)
        root_layout.addLayout(top_bar)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)
        root_layout.addLayout(body_layout, 1)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("sidebar")
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(12)

        logo_label = QLabel("AuthDeck", self.sidebar)
        logo_label.setObjectName("logoLabel")
        side_layout.addWidget(logo_label)

        self.add_account_button = QPushButton("Add Account", self.sidebar)
        self.add_account_button.setObjectName("primaryAddButton")
        self.add_account_button.clicked.connect(self._show_add_account_menu)
        side_layout.addWidget(self.add_account_button)

        self.search_input = QLineEdit(self.sidebar)
        self.search_input.setPlaceholderText("Search services...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        side_layout.addWidget(self.search_input)

        self.account_list = ReorderableAccountList(self.sidebar)
        self.account_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.account_list.setDragEnabled(True)
        self.account_list.setAcceptDrops(True)
        self.account_list.setDropIndicatorShown(True)
        self.account_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.account_list.customContextMenuRequested.connect(self._show_account_context_menu)
        self.account_list.currentRowChanged.connect(self._sync_main_display)
        self.account_list.rows_moved.connect(self._on_account_rows_moved)
        side_layout.addWidget(self.account_list, 1)

        body_layout.addWidget(self.sidebar, 1)

        self.main_panel = QFrame(self)
        self.main_panel.setObjectName("mainPanel")
        main_layout = QVBoxLayout(self.main_panel)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(14)

        self.current_service_label = QLabel("Select an account", self.main_panel)
        self.current_service_label.setObjectName("selectedService")
        main_layout.addWidget(self.current_service_label)

        self.current_account_label = QLabel("", self.main_panel)
        self.current_account_label.setObjectName("selectedAccount")
        main_layout.addWidget(self.current_account_label)

        self.large_code_label = QLabel("------", self.main_panel)
        self.large_code_label.setObjectName("largeCode")
        self.large_code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.large_code_label)

        self.main_timer = CircularTimerWidget(self.main_panel)
        main_layout.addWidget(self.main_timer, alignment=Qt.AlignmentFlag.AlignHCenter)

        action_buttons_layout = QHBoxLayout()
        action_buttons_layout.setSpacing(10)
        action_buttons_layout.addStretch(1)

        self.copy_button = QPushButton("Copy Code", self.main_panel)
        self.copy_button.setObjectName("primaryCopyButton")
        self.copy_button.clicked.connect(self._copy_selected_code)
        self.copy_button.setFixedWidth(210)
        self.copy_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        action_buttons_layout.addWidget(self.copy_button)

        self._copy_pulse_animation = QPropertyAnimation(self.copy_button, b"geometry", self)
        self._copy_pulse_animation.setDuration(220)
        self._copy_pulse_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.delete_button = QPushButton("Delete Code", self.main_panel)
        self.delete_button.setObjectName("dangerDeleteButton")
        self.delete_button.clicked.connect(self._delete_selected_account)
        self.delete_button.setFixedWidth(210)
        self.delete_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        action_buttons_layout.addWidget(self.delete_button)
        action_buttons_layout.addStretch(1)

        self.action_buttons_widget = QWidget(self.main_panel)
        self.action_buttons_widget.setLayout(action_buttons_layout)

        main_layout.addWidget(self.action_buttons_widget)

        main_layout.addStretch(1)
        body_layout.addWidget(self.main_panel, 2)

    def _setup_timers(self) -> None:
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self._refresh_codes)
        self.refresh_timer.start()

    def _setup_tray(self, icon_path: Path) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(self.windowIcon())

        self.tray_menu = QMenu(self)
        self.show_action = QAction("Restore", self)
        self.show_action.triggered.connect(self._restore_window)
        self.tray_menu.addAction(self.show_action)

        self.codes_menu = QMenu("Copy Codes", self)
        self.tray_menu.addMenu(self.codes_menu)

        self.hide_action = QAction("Minimize to Tray", self)
        self.hide_action.triggered.connect(self._minimize_to_tray)
        self.tray_menu.addAction(self.hide_action)

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self._exit_application)
        self.tray_menu.addAction(self.exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _load_accounts_to_list(self) -> None:
        current_storage_index = self._storage_index_for_row(self.account_list.currentRow())

        self.account_list.clear()
        self._visible_account_indices = []
        query = self.search_input.text().strip().lower()

        for storage_index, account in enumerate(self._storage.accounts):
            searchable = " ".join(
                [
                    str(account.get("name", "")),
                    str(account.get("issuer", "")),
                    str(account.get("account", "")),
                ]
            ).lower()
            if query and query not in searchable:
                continue

            self._visible_account_indices.append(storage_index)
            item = QListWidgetItem(self.account_list)
            item.setSizeHint(QSize(260, 112))
            widget = AccountItemWidget(account, self.account_list)
            widget.code_clicked.connect(lambda item_row=storage_index: self._on_sidebar_code_clicked(item_row))
            self.account_list.setItemWidget(item, widget)

        if self.account_list.count() > 0:
            if current_storage_index is not None and current_storage_index in self._visible_account_indices:
                self.account_list.setCurrentRow(self._visible_account_indices.index(current_storage_index))
            else:
                self.account_list.setCurrentRow(0)

        self._refresh_codes()
        self._refresh_tray_codes_menu()

    def _on_search_text_changed(self, _text: str) -> None:
        self._load_accounts_to_list()

    def _on_account_rows_moved(self, from_row: int, to_row: int) -> None:
        if from_row == to_row:
            return

        if self.search_input.text().strip():
            self._show_status("Clear search to reorder accounts.", is_error=True, timeout=3000)
            self._load_accounts_to_list()
            return

        if len(self._visible_account_indices) != len(self._storage.accounts):
            self._show_status("Reorder is only available in full list view.", is_error=True, timeout=3000)
            self._load_accounts_to_list()
            return

        self._storage.move_account(from_row, to_row)
        self._load_accounts_to_list()
        if 0 <= to_row < self.account_list.count():
            self.account_list.setCurrentRow(to_row)

    def _storage_index_for_row(self, row: int) -> int | None:
        if row < 0 or row >= len(self._visible_account_indices):
            return None
        return self._visible_account_indices[row]

    def _show_add_account_menu(self) -> None:
        dialog = AddAccountChoiceDialog(theme=self._current_theme, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.choice == "scan":
            self._start_qr_scan()
        elif dialog.choice == "manual":
            self._add_manual_account()

    def _start_qr_scan(self) -> None:
        if self._scan_active:
            return

        self._scan_active = True
        self.add_account_button.setEnabled(False)
        self.hide()
        overlay = ScanOverlay()
        self._scan_overlay = overlay
        overlay.qr_detected.connect(self._process_qr_payload)
        overlay.scan_cancelled.connect(self._on_scan_cancelled)
        overlay.destroyed.connect(lambda _obj=None, source=overlay: self._on_scan_overlay_closed(source))
        overlay.show()

    def _end_scan_session(self) -> None:
        self._scan_active = False
        self.add_account_button.setEnabled(True)
        if not self._force_close:
            self._restore_window()

    def _show_status(self, message: str, *, is_error: bool = False, timeout: int = 3000) -> None:
        if is_error:
            self.statusBar().setStyleSheet("QStatusBar { color: #ff6b6b; font-weight: 700; }")
        else:
            self.statusBar().setStyleSheet("")

        self.statusBar().showMessage(message, timeout)
        QTimer.singleShot(timeout + 60, lambda: self.statusBar().setStyleSheet(""))

    def _format_scan_error(self, reason: str) -> str:
        normalized = (reason or "").lower()
        if "no qr code" in normalized:
            return "No valid OTP QR found. Select only the QR square and try again."
        if "timed out" in normalized:
            return "Scan timed out. Select a smaller QR area and retry."
        if "unavailable" in normalized:
            return "QR scanner backend is unavailable on this system."
        return reason or "QR scan failed"

    @pyqtSlot(str)
    def _process_qr_payload(self, payload: str) -> None:
        self._end_scan_session()

        if not payload.lower().startswith("otpauth://"):
            self._show_status("Invalid QR: expected an OTP provisioning QR (otpauth://)", is_error=True, timeout=5000)
            return

        try:
            account = self._totp.parse_otpauth_url(payload)
            self._storage.add_account(account)
        except Exception as error:  # noqa: BLE001
            self._show_status(f"Failed to add account: {error}", is_error=True, timeout=6000)
            return

        self._load_accounts_to_list()
        self._show_status("Account added from QR", timeout=2500)

    @pyqtSlot(str)
    def _on_scan_cancelled(self, reason: str) -> None:
        self._end_scan_session()
        if reason and reason not in {"Scan cancelled", "Selection too small"}:
            self._show_status(self._format_scan_error(reason), is_error=True, timeout=6000)

    def _on_scan_overlay_closed(self, source: ScanOverlay | None = None) -> None:
        if source is not None and source is not self._scan_overlay:
            return

        if self._scan_active:
            self._end_scan_session()

        if source is None or source is self._scan_overlay:
            self._scan_overlay = None

    def _add_manual_account(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Account")
        dialog.resize(420, 240)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        otpauth_input = QLineEdit(dialog)
        otpauth_input.setPlaceholderText("otpauth://totp/Issuer:email@example.com?secret=...")
        form.addRow("otpauth URL", otpauth_input)

        name_input = QLineEdit(dialog)
        form.addRow("Name", name_input)

        account_input = QLineEdit(dialog)
        form.addRow("Email / Username", account_input)

        issuer_input = QLineEdit(dialog)
        form.addRow("Issuer", issuer_input)

        secret_input = QLineEdit(dialog)
        secret_input.setPlaceholderText("BASE32 secret")
        form.addRow("Secret", secret_input)

        layout.addLayout(form)

        save_button = QPushButton("Save", dialog)
        save_button.setObjectName("manualSaveButton")
        save_button.clicked.connect(dialog.accept)
        layout.addWidget(save_button)

        if self._current_theme == "light":
            dialog.setStyleSheet(
                """
                QDialog { background-color: #f6f9fd; border: 1px solid #c8d5e6; border-radius: 12px; }
                QLabel { color: #1f3147; font-weight: 600; }
                QLineEdit {
                    background-color: #edf3fa;
                    border: 1px solid #b7cbe3;
                    border-radius: 8px;
                    padding: 7px 10px;
                    color: #24364a;
                }
                QLineEdit:focus { border-color: #7ea5d2; }
                QPushButton#manualSaveButton {
                    background-color: #3f7cc8;
                    border: 1px solid #2f67ad;
                    border-radius: 10px;
                    padding: 9px 14px;
                    color: #ffffff;
                    font-weight: 700;
                }
                QPushButton#manualSaveButton:hover { background-color: #336eb8; }
                """
            )
        else:
            dialog.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel { color: #e8f0ff; font-weight: 600; }
                QLineEdit {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 8px;
                    padding: 7px 10px;
                    color: #e8f0ff;
                }
                QLineEdit:focus { border-color: #6ea8fe; }
                QPushButton#manualSaveButton {
                    background-color: #2f67ad;
                    border: 1px solid #4f89ce;
                    border-radius: 10px;
                    padding: 9px 14px;
                    color: #ffffff;
                    font-weight: 700;
                }
                QPushButton#manualSaveButton:hover { background-color: #3b76c1; }
                """
            )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            if otpauth_input.text().strip():
                account = self._totp.parse_otpauth_url(otpauth_input.text().strip())
            else:
                account = {
                    "name": name_input.text().strip() or issuer_input.text().strip() or "Account",
                    "issuer": issuer_input.text().strip(),
                    "account": account_input.text().strip(),
                    "secret": secret_input.text().strip().replace(" ", ""),
                    "digits": 6,
                    "period": 30,
                    "algorithm": "sha1",
                }
            self._storage.add_account(account)
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Invalid Account", str(error))
            return

        self._load_accounts_to_list()

    def _show_account_context_menu(self, pos) -> None:
        row = self.account_list.indexAt(pos).row()
        if row < 0:
            return

        storage_index = self._storage_index_for_row(row)
        if storage_index is None:
            return

        menu = QMenu(self)
        copy_action = menu.addAction("Copy Code")
        rename_action = menu.addAction("Rename Account")
        delete_action = menu.addAction("Delete Account")

        selected = menu.exec(self.account_list.viewport().mapToGlobal(pos))
        if selected == copy_action:
            self._copy_code_for_storage_index(storage_index)
        elif selected == rename_action:
            self._rename_account(storage_index)
        elif selected == delete_action:
            self._delete_account(storage_index)

    def _on_sidebar_code_clicked(self, storage_index: int) -> None:
        if storage_index < 0 or storage_index >= len(self._storage.accounts):
            return

        if storage_index in self._visible_account_indices:
            self.account_list.setCurrentRow(self._visible_account_indices.index(storage_index))

        self._copy_code_for_storage_index(storage_index)

    def _rename_account(self, row: int) -> None:
        existing_name = self._storage.accounts[row].get("name", "Account")

        dialog = QDialog(self)
        dialog.setWindowTitle("Rename Account")
        dialog.setModal(True)
        dialog.resize(380, 150)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        label = QLabel("New name", dialog)
        layout.addWidget(label)

        name_input = QLineEdit(dialog)
        name_input.setText(str(existing_name))
        name_input.selectAll()
        layout.addWidget(name_input)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)
        cancel_button = QPushButton("Cancel", dialog)
        save_button = QPushButton("Save", dialog)
        save_button.setObjectName("renameSaveButton")
        cancel_button.clicked.connect(dialog.reject)
        save_button.clicked.connect(dialog.accept)
        buttons_layout.addWidget(cancel_button)
        buttons_layout.addWidget(save_button)
        layout.addLayout(buttons_layout)

        if self._current_theme == "light":
            dialog.setStyleSheet(
                """
                QDialog { background-color: #f6f9fd; border: 1px solid #c8d5e6; border-radius: 12px; }
                QLabel { color: #1f3147; font-weight: 600; }
                QLineEdit {
                    background-color: #edf3fa;
                    border: 1px solid #b7cbe3;
                    border-radius: 8px;
                    padding: 7px 10px;
                    color: #24364a;
                }
                QLineEdit:focus { border-color: #7ea5d2; }
                QPushButton {
                    background-color: #e3ecf8;
                    border: 1px solid #b7cbe3;
                    border-radius: 9px;
                    padding: 7px 12px;
                    color: #21354b;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #d8e5f4; border-color: #9fb8d7; }
                QPushButton#renameSaveButton {
                    background-color: #3f7cc8;
                    border: 1px solid #2f67ad;
                    color: #ffffff;
                }
                QPushButton#renameSaveButton:hover { background-color: #336eb8; }
                """
            )
        else:
            dialog.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel { color: #e8f0ff; font-weight: 600; }
                QLineEdit {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 8px;
                    padding: 7px 10px;
                    color: #e8f0ff;
                }
                QLineEdit:focus { border-color: #6ea8fe; }
                QPushButton {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 9px;
                    padding: 7px 12px;
                    color: #f1f6ff;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #1b314d; border-color: #406a9f; }
                QPushButton#renameSaveButton {
                    background-color: #2f67ad;
                    border: 1px solid #4f89ce;
                    color: #ffffff;
                }
                QPushButton#renameSaveButton:hover { background-color: #3b76c1; }
                """
            )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = name_input.text().strip()
        if not new_name:
            return

        self._storage.rename_account(row, new_name)
        self._load_accounts_to_list()
        self.account_list.setCurrentRow(row)

    def _delete_account(self, row: int) -> None:
        account_name = self._storage.accounts[row].get("name", "Selected account")
        confirmation_dialog = DeleteConfirmDialog(account_name, self._current_theme, self)
        if confirmation_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if not self._confirm_delete_pin():
            return

        self._storage.delete_account(row)
        self._load_accounts_to_list()

    def _confirm_delete_pin(self) -> bool:
        if not self._storage.pin_enabled:
            QMessageBox.warning(
                self,
                "PIN Required",
                "Set a 4-digit PIN in Settings to enable secure account deletion.",
            )
            return False

        dialog = PinConfirmDialog(theme=self._current_theme, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        if not self._storage.verify_pin(dialog.pin_value()):
            QMessageBox.warning(self, "Incorrect PIN", "Incorrect PIN. Account not deleted.")
            return False

        return True

    def _copy_selected_code(self) -> None:
        storage_index = self._storage_index_for_row(self.account_list.currentRow())
        if storage_index is not None:
            self._copy_code_for_storage_index(storage_index)

    def _delete_selected_account(self) -> None:
        storage_index = self._storage_index_for_row(self.account_list.currentRow())
        if storage_index is not None:
            self._delete_account(storage_index)

    def _copy_code_for_storage_index(self, storage_index: int) -> None:
        account = self._storage.accounts[storage_index]
        code, _ = self._safe_totp(account)
        if not code:
            return

        clipboard: QClipboard | None = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(code)

        self._play_copy_success_feedback()

    def _play_copy_success_feedback(self) -> None:
        self.copy_button.setText("Copied ✓")
        self.copy_button.setProperty("copySuccess", True)
        self.copy_button.style().unpolish(self.copy_button)
        self.copy_button.style().polish(self.copy_button)
        self.copy_button.update()

        if self._copy_pulse_animation is not None:
            base_rect = self.copy_button.geometry()
            pulse_rect = base_rect.adjusted(-4, -2, 4, 2)
            self._copy_pulse_animation.stop()
            self._copy_pulse_animation.setStartValue(base_rect)
            self._copy_pulse_animation.setKeyValueAt(0.5, pulse_rect)
            self._copy_pulse_animation.setEndValue(base_rect)
            self._copy_pulse_animation.start()

        self._copy_feedback_timer.start(1200)

    def _reset_copy_button_feedback(self) -> None:
        self.copy_button.setText("Copy Code")
        self.copy_button.setProperty("copySuccess", False)
        self.copy_button.style().unpolish(self.copy_button)
        self.copy_button.style().polish(self.copy_button)
        self.copy_button.update()

    def _safe_totp(self, account: dict[str, Any]) -> tuple[str, int]:
        try:
            return self._totp.current_code_with_remaining(account)
        except Exception:
            return "------", int(account.get("period", 30) or 30)

    def _refresh_codes(self) -> None:
        for row, storage_index in enumerate(self._visible_account_indices):
            account = self._storage.accounts[storage_index]
            code, remaining = self._safe_totp(account)
            list_item = self.account_list.item(row)
            if list_item is None:
                continue
            widget = self.account_list.itemWidget(list_item)
            if isinstance(widget, AccountItemWidget):
                widget.update_values(account, code, remaining)

        self._sync_main_display(self.account_list.currentRow())
        self._refresh_tray_codes_menu()

    def _sync_main_display(self, row: int) -> None:
        storage_index = self._storage_index_for_row(row)
        if storage_index is None:
            self._copy_feedback_timer.stop()
            self._reset_copy_button_feedback()
            self.current_service_label.setText("Select an account")
            self.current_account_label.setText("")
            self.large_code_label.setText("")
            self.main_timer.set_countdown(30, 0)
            self.copy_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.main_timer.setVisible(False)
            self.action_buttons_widget.setVisible(False)
            return

        account = self._storage.accounts[storage_index]
        code, remaining = self._safe_totp(account)
        period = int(account.get("period", 30) or 30)

        self.current_service_label.setText(_format_service_name(account.get("name", "Account")))
        self.current_account_label.setText(account.get("account", ""))
        self.large_code_label.setText(code)
        self.main_timer.set_countdown(period, remaining)
        self.copy_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.main_timer.setVisible(True)
        self.action_buttons_widget.setVisible(True)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            current_theme=self._current_theme,
            pin_enabled=self._storage.pin_enabled,
            parent=self,
        )
        dialog.theme_changed.connect(self._apply_theme)
        dialog.export_requested.connect(self._export_backup)
        dialog.import_requested.connect(self._import_backup)
        dialog.pin_setup_requested.connect(lambda: self._handle_pin_setup(dialog))
        dialog.pin_remove_requested.connect(lambda: self._handle_pin_remove(dialog))
        dialog.pin_forgot_requested.connect(lambda: self._handle_pin_forgot(dialog))
        dialog.about_requested.connect(self._show_about_dialog)
        dialog.exec()

    def _show_about_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About AuthDeck")
        dialog.setModal(True)
        dialog.resize(440, 250)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("AuthDeck v1.0.4", dialog)
        title.setObjectName("aboutTitle")
        layout.addWidget(title)

        details = QLabel("Developer: Supan Roy", dialog)
        details.setObjectName("aboutDetails")
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        details.setOpenExternalLinks(True)
        layout.addWidget(details)

        email = QLabel("Email: <a href='mailto:support@supanroy.com'>support@supanroy.com</a>", dialog)
        email.setObjectName("aboutDetails")
        email.setTextFormat(Qt.TextFormat.RichText)
        email.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        email.setOpenExternalLinks(True)
        layout.addWidget(email)

        links = QLabel(
            "GitHub: <a href='https://github.com/Supan-Roy'>Supan-Roy</a><br/>"
            "LinkedIn: <a href='https://www.linkedin.com/in/supanroy'>supanroy</a>",
            dialog,
        )
        links.setObjectName("aboutLinks")
        links.setTextFormat(Qt.TextFormat.RichText)
        links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        links.setOpenExternalLinks(True)
        layout.addWidget(links)

        close_button = QPushButton("Close", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        if self._current_theme == "light":
            dialog.setStyleSheet(
                """
                QDialog {
                    background-color: #ffffff;
                    border: 1px solid #b8c9dd;
                    border-radius: 12px;
                }
                QLabel#aboutTitle { color: #000000; font-size: 18px; font-weight: 800; }
                QLabel#aboutDetails, QLabel#aboutLinks { color: #000000; font-size: 13px; font-weight: 700; }
                QLabel#aboutDetails a, QLabel#aboutLinks a { color: #000000; text-decoration: none; font-weight: 700; }
                QLabel#aboutDetails a:hover, QLabel#aboutLinks a:hover { text-decoration: underline; }
                QPushButton {
                    background-color: #3f7cc8;
                    border: 1px solid #2f67ad;
                    border-radius: 9px;
                    padding: 7px 14px;
                    color: #ffffff;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #336eb8; }
                """
            )
        else:
            dialog.setStyleSheet(
                """
                QDialog { background-color: #05070a; border: 1px solid #22344d; border-radius: 12px; }
                QLabel#aboutTitle { color: #eef4ff; font-size: 18px; font-weight: 800; }
                QLabel#aboutDetails, QLabel#aboutLinks { color: #c9daef; font-size: 13px; }
                QLabel#aboutDetails a, QLabel#aboutLinks a { color: #8fbaff; text-decoration: none; }
                QLabel#aboutDetails a:hover, QLabel#aboutLinks a:hover { text-decoration: underline; }
                QPushButton {
                    background-color: #2f67ad;
                    border: 1px solid #4f89ce;
                    border-radius: 9px;
                    padding: 7px 14px;
                    color: #ffffff;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #3b76c1; }
                """
            )

        dialog.exec()

    def _handle_pin_setup(self, settings_dialog: SettingsDialog) -> None:
        pin_dialog = PinSetupDialog(theme=self._current_theme, parent=self)
        if pin_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._storage.set_pin(pin_dialog.pin_value())
            settings_dialog.set_pin_enabled(True)
            self._show_status("PIN updated successfully", timeout=2500)
        except Exception as error:  # noqa: BLE001
            self._show_status(f"Failed to set PIN: {error}", is_error=True, timeout=5000)

    def _handle_pin_remove(self, settings_dialog: SettingsDialog) -> None:
        confirm = QMessageBox.question(
            self,
            "Remove PIN",
            "Remove app PIN protection?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._storage.clear_pin()
        settings_dialog.set_pin_enabled(False)
        self._show_status("PIN removed", timeout=2500)

    def _handle_pin_forgot(self, settings_dialog: SettingsDialog) -> None:
        confirm = QMessageBox.warning(
            self,
            "Forgot PIN",
            "This will delete ALL saved accounts and remove PIN lock. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._storage.reset_all_data_for_forgot_pin()
        self.search_input.clear()
        self._load_accounts_to_list()
        settings_dialog.set_pin_enabled(False)
        self._show_status("All accounts were removed. Set up AuthDeck again.", is_error=True, timeout=6000)

    def require_pin_on_startup(self) -> bool:
        if not self._storage.pin_enabled:
            return True

        unlock_dialog = PinUnlockDialog(theme=self._current_theme, parent=None)
        unlock_dialog.forgot_requested.connect(lambda: self._forgot_from_unlock(unlock_dialog))
        unlock_dialog.pin_input.textChanged.connect(
            lambda text, dialog=unlock_dialog: self._try_auto_unlock_from_pin_input(dialog, text)
        )

        attempts = 0
        while True:
            result = unlock_dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                return False

            if unlock_dialog.forgot_triggered:
                return True

            if self._storage.verify_pin(unlock_dialog.pin_value()):
                return True

            attempts += 1
            unlock_dialog.show_error("Incorrect PIN")
            if attempts >= 5:
                self._show_status("Too many failed PIN attempts", is_error=True, timeout=4000)

    def _try_auto_unlock_from_pin_input(self, dialog: PinUnlockDialog, value: str) -> None:
        pin = value.strip()
        if len(pin) != 4 or not pin.isdigit():
            return

        if self._storage.verify_pin(pin):
            dialog.accept()

    def _forgot_from_unlock(self, unlock_dialog: PinUnlockDialog) -> None:
        confirm = QMessageBox.warning(
            unlock_dialog,
            "Forgot PIN",
            "Forgot PIN will remove ALL accounts. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._storage.reset_all_data_for_forgot_pin()
        self.search_input.clear()
        self._load_accounts_to_list()
        unlock_dialog.forgot_triggered = True
        unlock_dialog.accept()
        self._show_status("All accounts removed due to forgot PIN", is_error=True, timeout=5000)

    def _export_backup(self) -> None:
        if not self._storage.accounts:
            QMessageBox.warning(self, "Export Unavailable", "No OTP accounts available to export.")
            return

        destination, _ = QFileDialog.getSaveFileName(self, "Export Backup", "authdeck-backup.json", "JSON (*.json)")
        if not destination:
            return

        password_dialog = BackupPasswordDialog(
            theme=self._current_theme,
            title="Protect Backup",
            confirm=True,
            parent=self,
        )
        if password_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._storage.export_backup(Path(destination), password_dialog.password_value())
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Export Failed", str(error))
            return
        QMessageBox.information(self, "Export Complete", "Encrypted backup exported successfully.")

    def _import_backup(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Import Backup", "", "JSON (*.json)")
        if not source:
            return

        source_path = Path(source)
        password: str | None = None

        try:
            if self._storage.is_backup_encrypted(source_path):
                password_dialog = BackupPasswordDialog(
                    theme=self._current_theme,
                    title="Unlock Backup",
                    confirm=False,
                    parent=self,
                )
                if password_dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                password = password_dialog.password_value()
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Import Failed", str(error))
            return

        try:
            self._storage.import_backup(source_path, password=password)
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Import Failed", str(error))
            return

        self._load_accounts_to_list()
        QMessageBox.information(self, "Import Complete", "Backup imported successfully.")

    def _refresh_tray_codes_menu(self) -> None:
        if self.codes_menu is None:
            return

        self.codes_menu.clear()
        if not self._storage.accounts:
            action = self.codes_menu.addAction("No accounts")
            action.setEnabled(False)
            return

        total_accounts = len(self._storage.accounts)
        visible_count = min(total_accounts, MAX_TRAY_COPY_ITEMS)

        for row in range(visible_count):
            account = self._storage.accounts[row]
            code, _ = self._safe_totp(account)
            title = f"{_format_service_name(account.get('name', 'Account'))}: {code}"
            action = self.codes_menu.addAction(title)
            action.triggered.connect(lambda _checked=False, item_row=row: self._copy_code_for_storage_index(item_row))

        if total_accounts > visible_count:
            self.codes_menu.addSeparator()
            remaining = total_accounts - visible_count
            more_action = self.codes_menu.addAction(f"+{remaining} more accounts (open app)")
            more_action.setEnabled(False)

    def _apply_theme(self, theme: str, persist: bool = True) -> None:
        self._current_theme = "dark" if theme.lower() != "light" else "light"
        if persist:
            self._storage.set_theme(self._current_theme)
        self.main_timer.set_theme(self._current_theme)

        if self._current_theme == "dark":
            self.setStyleSheet(
                """
                QMainWindow { background-color: #000000; color: #f2f6ff; }
                QWidget { font-family: Segoe UI, Inter, Arial; font-size: 13px; color: #dfe7f5; }
                #windowTitle { font-size: 22px; font-weight: 800; color: #ffffff; }
                #logoLabel { font-size: 28px; font-weight: 800; color: #ffffff; padding: 6px 4px 10px 4px; }
                #sidebar, #mainPanel {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #050505, stop:1 #0b1118);
                    border: 1px solid #1a2940;
                    border-radius: 16px;
                }
                QLabel#accountName { font-weight: 700; font-size: 14px; color: #f3f7ff; }
                QLabel#accountUser { color: #92a7c3; font-size: 12px; }
                QLabel#accountCode { color: #9ac4ff; font-size: 22px; font-weight: 800; }
                QLabel#selectedService { font-size: 38px; font-weight: 800; color: #ffffff; }
                QLabel#selectedAccount { font-size: 13px; color: #98adc8; }
                QLabel#largeCode { font-size: 74px; font-weight: 800; letter-spacing: 2px; color: #8fbaff; }
                QListWidget {
                    background-color: #02060b;
                    border: 1px solid #1a2a3f;
                    border-radius: 12px;
                    padding: 9px;
                }
                QListWidget::item { margin-bottom: 8px; border-radius: 11px; background: #0a121c; }
                QListWidget::item:selected {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #122236, stop:1 #1f3e66);
                }
                QPushButton {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 11px;
                    padding: 9px 14px;
                    color: #f1f6ff;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #1b314d; border-color: #406a9f; }
                QPushButton:pressed { background-color: #0f1b2a; }
                QPushButton:disabled { background-color: #09111b; color: #55708f; border-color: #182536; }
                QPushButton#primaryCopyButton[copySuccess="true"] {
                    background-color: rgba(255, 255, 255, 0.16);
                    border: 1px solid rgba(255, 255, 255, 0.42);
                    color: #ffffff;
                }
                QPushButton#primaryCopyButton[copySuccess="true"]:hover {
                    background-color: rgba(255, 255, 255, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.54);
                }
                QProgressBar {
                    border: 1px solid #2f4f79;
                    border-radius: 10px;
                    background-color: #02060b;
                    text-align: center;
                    height: 16px;
                    color: #dce8fa;
                }
                QProgressBar::chunk {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4a84c8, stop:1 #7eb4ff);
                    border-radius: 9px;
                }
                QProgressBar#secondaryProgress {
                    border: 1px solid #2f4f79;
                    border-radius: 10px;
                    background-color: #050b13;
                    padding: 1px;
                    min-height: 16px;
                }
                QProgressBar#secondaryProgress::chunk {
                    border-radius: 8px;
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #5f97dc, stop:1 #8cbcff);
                }
                QMenu { background-color: #070d15; border: 1px solid #2f4c72; padding: 6px; }
                QMenu::item { padding: 7px 20px; border-radius: 6px; }
                QMenu::item:selected { background-color: #1f3552; }
                QMessageBox {
                    background-color: #05070a;
                    color: #e7eefb;
                }
                QMessageBox QLabel { color: #e7eefb; }
                QMessageBox QPushButton {
                    background-color: #132135;
                    border: 1px solid #2c4870;
                    border-radius: 9px;
                    padding: 6px 14px;
                    color: #f1f6ff;
                    font-weight: 700;
                    min-width: 72px;
                }
                QMessageBox QPushButton:hover { background-color: #1b314d; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QMainWindow {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #e8edf5, stop:1 #dbe5f3);
                    color: #203144;
                }
                QWidget { font-family: Segoe UI, Inter, Arial; font-size: 13px; color: #25364a; }
                #windowTitle { font-size: 22px; font-weight: 700; }
                #logoLabel { font-size: 20px; font-weight: 700; color: #1f3147; padding: 6px 4px; }
                #sidebar, #mainPanel {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #f5f8fc, stop:1 #edf3fa);
                    border: 1px solid #c8d5e6;
                    border-radius: 14px;
                }
                QLabel#accountName { font-weight: 700; font-size: 13px; color: #1d3047; }
                QLabel#accountUser { color: #5f738b; font-size: 12px; }
                QLabel#accountCode { color: #285fa9; font-size: 20px; font-weight: 700; }
                QLabel#selectedService { font-size: 22px; font-weight: 800; color: #1d3047; }
                QLabel#selectedAccount { font-size: 13px; color: #5f738b; }
                QLabel#largeCode { font-size: 56px; font-weight: 700; letter-spacing: 2px; color: #2b63ac; }
                QListWidget {
                    background-color: #f3f7fc;
                    border: 1px solid #c9d8e9;
                    border-radius: 10px;
                    padding: 8px;
                }
                QListWidget::item {
                    margin-bottom: 8px;
                    border-radius: 10px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #e7eef8, stop:1 #dde8f5);
                }
                QListWidget::item:selected {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #d2e3f8, stop:1 #c4d9f2);
                }
                QPushButton {
                    background-color: #e3ecf8;
                    border: 1px solid #b7cbe3;
                    border-radius: 9px;
                    padding: 8px 14px;
                    color: #21354b;
                    font-weight: 700;
                }
                QPushButton:hover { background-color: #d8e5f4; border-color: #9fb8d7; }
                QPushButton:pressed { background-color: #cfdff1; }
                QPushButton#topSettingsButton,
                QPushButton#primaryAddButton,
                QPushButton#primaryCopyButton {
                    background-color: #3f7cc8;
                    border: 1px solid #2f67ad;
                    color: #ffffff;
                }
                QPushButton#topSettingsButton:hover,
                QPushButton#primaryAddButton:hover,
                QPushButton#primaryCopyButton:hover { background-color: #336eb8; }
                QPushButton#primaryCopyButton[copySuccess="true"] {
                    background-color: #16a34a;
                    border: 1px solid #13803b;
                    color: #ffffff;
                }
                QPushButton#primaryCopyButton[copySuccess="true"]:hover { background-color: #148f41; }
                QPushButton#dangerDeleteButton {
                    background-color: #ef4444;
                    border: 1px solid #d83b3b;
                    color: #ffffff;
                }
                QPushButton#dangerDeleteButton:hover { background-color: #dc2626; }
                QProgressBar {
                    border: 1px solid #b7cbe3;
                    border-radius: 8px;
                    background-color: #edf3fa;
                    text-align: center;
                    height: 14px;
                }
                QProgressBar::chunk { background-color: #5b8cc4; border-radius: 7px; }
                QProgressBar#secondaryProgress {
                    border: 1px solid #aec4df;
                    border-radius: 10px;
                    background-color: #e8f0f9;
                    padding: 1px;
                    min-height: 16px;
                }
                QProgressBar#secondaryProgress::chunk {
                    border-radius: 8px;
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #5f97dc, stop:1 #7fb0e6);
                }
                QLineEdit {
                    background-color: #edf3fa;
                    border: 1px solid #b7cbe3;
                    border-radius: 8px;
                    padding: 6px 9px;
                    color: #25364a;
                }
                QLineEdit:focus { border-color: #7ea5d2; }
                QMenu { background-color: #f5f8fc; border: 1px solid #b7cbe3; padding: 6px; }
                QMenu::item { padding: 7px 20px; border-radius: 6px; }
                QMenu::item:selected { background-color: #d8e6f7; }
                QMessageBox {
                    background-color: #f6f9fd;
                    color: #1f3147;
                }
                QMessageBox QLabel { color: #1f3147; }
                QMessageBox QPushButton {
                    background-color: #e3ecf8;
                    border: 1px solid #b7cbe3;
                    border-radius: 9px;
                    padding: 6px 14px;
                    color: #21354b;
                    font-weight: 700;
                    min-width: 72px;
                }
                QMessageBox QPushButton:hover { background-color: #d8e5f4; border-color: #9fb8d7; }
                """
            )

    def _minimize_to_tray(self) -> None:
        self.hide()
        self.tray_icon.showMessage("AuthDeck", "AuthDeck is still running in the system tray.")

    def _restore_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _exit_application(self) -> None:
        self._force_close = True
        self.tray_icon.hide()
        self.close()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._force_close = True
        self.tray_icon.hide()
        event.accept()
