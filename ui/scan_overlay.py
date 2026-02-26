from __future__ import annotations

from queue import Empty, Queue
from threading import Thread

from PyQt6.QtCore import QPoint, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from core.qr_scanner import QRScanner


class ScanOverlay(QWidget):
    """Transparent full-screen region selector for QR scanning."""

    qr_detected = pyqtSignal(str)
    scan_cancelled = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scanner = QRScanner()
        self._start_pos = QPoint()
        self._end_pos = QPoint()
        self._is_selecting = False
        self._is_scanning = False
        self._scan_cancelled = False
        self._finished = False
        self._scan_results: Queue[tuple[str, str]] = Queue()
        self._scan_poll_timer = QTimer(self)
        self._scan_poll_timer.setInterval(80)
        self._scan_poll_timer.timeout.connect(self._poll_scan_result)
        self._scan_timeout_timer = QTimer(self)
        self._scan_timeout_timer.setSingleShot(True)
        self._scan_timeout_timer.timeout.connect(self._on_scan_timeout)

        self.setWindowTitle("Scan QR")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._set_virtual_desktop_geometry()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _set_virtual_desktop_geometry(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            self.showFullScreen()
            return

        virtual_geometry = screens[0].virtualGeometry()
        self.setGeometry(virtual_geometry)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._close_button_rect().contains(
            event.position().toPoint()
        ):
            self._cancel_scan("Scan cancelled")
            return

        if self._is_scanning:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()
            self._end_pos = self._start_pos
            self._is_selecting = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_scanning:
            return

        if self._is_selecting:
            self._end_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._is_selecting:
            return

        self._is_selecting = False
        self._end_pos = event.position().toPoint()

        selection = QRect(self._start_pos, self._end_pos).normalized()
        if selection.width() < 8 or selection.height() < 8:
            self.scan_cancelled.emit("Selection too small")
            self.close()
            return

        self._is_scanning = True
        self._scan_cancelled = False
        self.setCursor(Qt.CursorShape.WaitCursor)

        selection_payload = {
            "top": selection.top(),
            "left": selection.left(),
            "width": selection.width(),
            "height": selection.height(),
        }
        worker = Thread(
            target=self._scan_worker,
            args=(selection_payload, self.width(), self.height()),
            daemon=True,
        )
        worker.start()
        self._scan_poll_timer.start()
        self._scan_timeout_timer.start(9000)
        self.update()

    def _scan_worker(self, selection_payload: dict[str, int], canvas_width: int, canvas_height: int) -> None:
        try:
            payload = self._scanner.decode_from_screen_selection(
                selection=selection_payload,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
            self._scan_results.put(("ok", payload))
        except Exception as error:  # noqa: BLE001
            self._scan_results.put(("err", str(error)))

    def _poll_scan_result(self) -> None:
        if self._finished:
            self._scan_poll_timer.stop()
            return

        try:
            status, payload = self._scan_results.get_nowait()
        except Empty:
            return

        self._scan_poll_timer.stop()
        self._scan_timeout_timer.stop()
        self._is_scanning = False

        if self._scan_cancelled:
            self.close()
            return

        if status == "ok":
            self.qr_detected.emit(payload)
        else:
            self.scan_cancelled.emit(payload)
        self.close()

    def _on_scan_timeout(self) -> None:
        if self._finished:
            return

        self._is_scanning = False
        self._scan_cancelled = True
        self._scan_poll_timer.stop()
        self.scan_cancelled.emit("Scan timed out. Try selecting a tighter QR region.")
        self.close()

    def _cancel_scan(self, reason: str) -> None:
        if self._finished:
            return

        self._scan_cancelled = True
        self._is_scanning = False
        self._scan_poll_timer.stop()
        self._scan_timeout_timer.stop()
        self.scan_cancelled.emit(reason)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_scan("Scan cancelled")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._finished = True
        self._scan_poll_timer.stop()
        self._scan_timeout_timer.stop()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Dim entire screen.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

        # Highlight selected area.
        selection = QRect(self._start_pos, self._end_pos).normalized()
        if not selection.isNull():
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(selection, QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#6ea8fe"), 2))
            painter.drawRect(selection)

        if self._is_scanning:
            painter.setPen(QPen(QColor("#e7eefb"), 1))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Scanning QR code...")

        # Top-right cancel button.
        close_rect = self._close_button_rect()
        painter.setPen(QPen(QColor("#7fa4cf"), 1))
        painter.setBrush(QColor(10, 18, 30, 220))
        painter.drawRoundedRect(close_rect, 8, 8)
        painter.setPen(QPen(QColor("#e7eefb"), 2))
        painter.drawText(close_rect, Qt.AlignmentFlag.AlignCenter, "×")

    def _close_button_rect(self) -> QRect:
        button_size = 40
        margin = 18
        return QRect(self.width() - button_size - margin, margin, button_size, button_size)
