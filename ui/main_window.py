from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, QStandardPaths, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QClipboard, QCloseEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
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


class AccountItemWidget(QWidget):
    """Visual widget for an account in the sidebar list."""

    def __init__(self, account: dict[str, Any], parent=None) -> None:
        super().__init__(parent)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(6)

        self.name_label = QLabel(account.get("name", "Account"), self)
        self.name_label.setObjectName("accountName")
        root_layout.addWidget(self.name_label)

        self.account_label = QLabel(account.get("account", ""), self)
        self.account_label.setObjectName("accountUser")
        root_layout.addWidget(self.account_label)

        self.code_label = QLabel("------", self)
        self.code_label.setObjectName("accountCode")
        root_layout.addWidget(self.code_label)

        self.progress = SmoothProgressBar(self)
        self.progress.setTextVisible(False)
        self.progress.setMaximum(30)
        self.progress.setValue(0)
        root_layout.addWidget(self.progress)

    def update_values(self, account: dict[str, Any], code: str, remaining: int) -> None:
        period = int(account.get("period", 30) or 30)
        self.name_label.setText(account.get("name", "Account"))
        self.account_label.setText(account.get("account", ""))
        self.code_label.setText(code)
        self.progress.setMaximum(period)
        self.progress.set_smooth_value(remaining)


class SmoothProgressBar(QProgressBar):
    """Progress bar with gentle value animation for smoother visual updates."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._animation = QPropertyAnimation(self, b"value", self)
        self._animation.setDuration(220)
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
        self.forgot_button.setAutoDefault(False)
        self.forgot_button.setDefault(False)
        self.forgot_button.clicked.connect(self.forgot_requested.emit)
        buttons.addWidget(self.forgot_button)

        self.unlock_button = QPushButton("Unlock", self)
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
                QDialog { background-color: #ffffff; border: 1px solid #d7e1eb; border-radius: 12px; }
                QLabel { color: #1f2a35; }
                QLabel#pinError { color: #b42318; font-weight: 700; }
                QLineEdit { background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 8px; padding: 8px 10px; }
                QPushButton { background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 8px; padding: 8px 10px; }
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
        self._current_theme = "dark"
        self._force_close = False
        self._scan_active = False
        self.codes_menu: QMenu | None = None
        self._asset_dir = asset_dir
        self._visible_account_indices: list[int] = []

        icon_path = asset_dir / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._apply_theme(self._current_theme)
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
        self.add_account_button.clicked.connect(self._show_add_account_menu)
        side_layout.addWidget(self.add_account_button)

        self.search_input = QLineEdit(self.sidebar)
        self.search_input.setPlaceholderText("Search services...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        side_layout.addWidget(self.search_input)

        self.account_list = QListWidget(self.sidebar)
        self.account_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.account_list.customContextMenuRequested.connect(self._show_account_context_menu)
        self.account_list.currentRowChanged.connect(self._sync_main_display)
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

        self.main_progress = SmoothProgressBar(self.main_panel)
        self.main_progress.setTextVisible(True)
        self.main_progress.setFormat("%v sec")
        self.main_progress.setMaximum(30)
        main_layout.addWidget(self.main_progress)

        action_buttons_layout = QHBoxLayout()
        action_buttons_layout.setSpacing(10)

        self.copy_button = QPushButton("Copy Code", self.main_panel)
        self.copy_button.clicked.connect(self._copy_selected_code)
        self.copy_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_buttons_layout.addWidget(self.copy_button)

        self.delete_button = QPushButton("Delete Code", self.main_panel)
        self.delete_button.clicked.connect(self._delete_selected_account)
        self.delete_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_buttons_layout.addWidget(self.delete_button)

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
        self._scan_overlay = ScanOverlay()
        self._scan_overlay.qr_detected.connect(self._process_qr_payload)
        self._scan_overlay.scan_cancelled.connect(self._on_scan_cancelled)
        self._scan_overlay.destroyed.connect(self._on_scan_overlay_closed)
        self._scan_overlay.show()

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

    def _on_scan_overlay_closed(self, _obj=None) -> None:
        if self._scan_active:
            self._end_scan_session()

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
        save_button.clicked.connect(dialog.accept)
        layout.addWidget(save_button)

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

    def _rename_account(self, row: int) -> None:
        existing_name = self._storage.accounts[row].get("name", "Account")
        new_name, accepted = QInputDialog.getText(self, "Rename Account", "New name", text=existing_name)
        if not accepted or not new_name.strip():
            return
        self._storage.rename_account(row, new_name)
        self._load_accounts_to_list()
        self.account_list.setCurrentRow(row)

    def _delete_account(self, row: int) -> None:
        account_name = self._storage.accounts[row].get("name", "Selected account")
        confirmation_dialog = DeleteConfirmDialog(account_name, self._current_theme, self)
        if confirmation_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._storage.delete_account(row)
        self._load_accounts_to_list()

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

        self.statusBar().showMessage("Code copied to clipboard", 1800)

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
            self.current_service_label.setText("Select an account")
            self.current_account_label.setText("")
            self.large_code_label.setText("")
            self.main_progress.setMaximum(30)
            self.main_progress.set_smooth_value(0)
            self.copy_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.main_progress.setVisible(False)
            self.action_buttons_widget.setVisible(False)
            return

        account = self._storage.accounts[storage_index]
        code, remaining = self._safe_totp(account)
        period = int(account.get("period", 30) or 30)

        self.current_service_label.setText(account.get("name", "Account"))
        self.current_account_label.setText(account.get("account", ""))
        self.large_code_label.setText(code)
        self.main_progress.setMaximum(period)
        self.main_progress.set_smooth_value(remaining)
        self.copy_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.main_progress.setVisible(True)
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
        destination, _ = QFileDialog.getSaveFileName(self, "Export Backup", "authdeck-backup.json", "JSON (*.json)")
        if not destination:
            return
        try:
            self._storage.export_backup(Path(destination))
        except Exception as error:  # noqa: BLE001
            QMessageBox.critical(self, "Export Failed", str(error))
            return
        QMessageBox.information(self, "Export Complete", "Backup exported successfully.")

    def _import_backup(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Import Backup", "", "JSON (*.json)")
        if not source:
            return
        try:
            self._storage.import_backup(Path(source))
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

        for row, account in enumerate(self._storage.accounts):
            code, _ = self._safe_totp(account)
            title = f"{account.get('name', 'Account')}: {code}"
            action = self.codes_menu.addAction(title)
            action.triggered.connect(lambda _checked=False, item_row=row: self._copy_code_for_storage_index(item_row))

    def _apply_theme(self, theme: str) -> None:
        self._current_theme = "dark" if theme.lower() != "light" else "light"

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
                QMenu { background-color: #070d15; border: 1px solid #2f4c72; padding: 6px; }
                QMenu::item { padding: 7px 20px; border-radius: 6px; }
                QMenu::item:selected { background-color: #1f3552; }
                QMessageBox { background-color: #000000; }
                """
            )
        else:
            self.setStyleSheet(
                """
                QMainWindow { background-color: #f3f6fb; color: #1f2a35; }
                QWidget { font-family: Segoe UI, Inter, Arial; font-size: 13px; color: #243242; }
                #windowTitle { font-size: 22px; font-weight: 700; }
                #logoLabel { font-size: 20px; font-weight: 700; color: #1f2a35; padding: 6px 4px; }
                #sidebar, #mainPanel { background-color: #ffffff; border: 1px solid #d7e1eb; border-radius: 14px; }
                QLabel#accountName { font-weight: 600; font-size: 13px; color: #1f2a35; }
                QLabel#accountUser { color: #607286; font-size: 12px; }
                QLabel#accountCode { color: #255ea8; font-size: 20px; font-weight: 700; }
                QLabel#selectedService { font-size: 22px; font-weight: 700; color: #1f2a35; }
                QLabel#selectedAccount { font-size: 13px; color: #607286; }
                QLabel#largeCode { font-size: 56px; font-weight: 700; letter-spacing: 2px; color: #255ea8; }
                QListWidget { background-color: #f9fbfd; border: 1px solid #d7e1eb; border-radius: 10px; padding: 8px; }
                QListWidget::item { margin-bottom: 8px; border-radius: 10px; background: #ffffff; }
                QListWidget::item:selected { background: #e8f0fb; }
                QPushButton {
                    background-color: #eff4fa; border: 1px solid #cfddea; border-radius: 9px;
                    padding: 8px 14px; color: #1f2a35; font-weight: 600;
                }
                QPushButton:hover { background-color: #e6edf7; }
                QPushButton:pressed { background-color: #dbe5f2; }
                QProgressBar {
                    border: 1px solid #c5d4e2; border-radius: 8px; background-color: #f2f7fc;
                    text-align: center; height: 14px;
                }
                QProgressBar::chunk { background-color: #5b8cc4; border-radius: 7px; }
                QMenu { background-color: #ffffff; border: 1px solid #cfddea; padding: 6px; }
                QMenu::item { padding: 7px 20px; border-radius: 6px; }
                QMenu::item:selected { background-color: #e8f0fb; }
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
        if self._force_close:
            event.accept()
            return

        event.ignore()
        self._minimize_to_tray()
