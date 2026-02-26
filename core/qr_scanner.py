from __future__ import annotations

from typing import Any

import mss
from PIL import Image, ImageOps


class QRScanner:
    """Screen-region and image QR scanner for otpauth provisioning."""

    def __init__(self) -> None:
        # Import lazily to avoid crashing app startup when zbar is missing.
        try:
            from pyzbar.pyzbar import decode  # pylint: disable=import-outside-toplevel
        except Exception as error:  # noqa: BLE001
            self._decode = None
            self._decode_error = error
        else:
            self._decode = decode
            self._decode_error = None

    def decode_from_image(self, image: Image.Image) -> str:
        if self._decode is None:
            raise RuntimeError("QR decoding is unavailable. Install pyzbar + zbar runtime.") from self._decode_error

        decoded_payload = self._decode_first_payload(image)
        if not decoded_payload:
            raise ValueError("No QR code detected in the selected region")

        payload = decoded_payload.strip()
        if not payload:
            raise ValueError("Detected QR payload is empty")
        return payload

    def _decode_first_payload(self, image: Image.Image) -> str | None:
        variants: list[Image.Image] = [image]
        grayscale = ImageOps.grayscale(image)
        variants.append(grayscale)
        variants.append(ImageOps.autocontrast(grayscale))

        # Upscale small captures to improve decode reliability.
        if image.width < 300 or image.height < 300:
            variants.append(image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS))

        for variant in variants:
            decoded = self._decode(variant)
            if not decoded:
                continue

            payload = decoded[0].data.decode("utf-8", errors="ignore").strip()
            if payload:
                return payload

        return None

    def decode_from_screen_region(self, region: dict[str, Any]) -> str:
        """Capture a region from screen and decode the first QR payload found."""
        with mss.mss() as screen_capture:
            screenshot = screen_capture.grab(region)
            image = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return self.decode_from_image(image)

    def decode_from_screen_selection(
        self,
        selection: dict[str, int],
        canvas_width: int,
        canvas_height: int,
    ) -> str:
        """Decode QR from a selection rectangle relative to a full-screen overlay canvas."""
        if canvas_width <= 0 or canvas_height <= 0:
            raise ValueError("Invalid overlay canvas size")

        with mss.mss() as screen_capture:
            virtual_monitor = screen_capture.monitors[0]
            screenshot = screen_capture.grab(virtual_monitor)
            full_image = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

        scale_x = screenshot.width / float(canvas_width)
        scale_y = screenshot.height / float(canvas_height)

        left = max(0, int(selection["left"] * scale_x))
        top = max(0, int(selection["top"] * scale_y))
        right = min(screenshot.width, int((selection["left"] + selection["width"]) * scale_x))
        bottom = min(screenshot.height, int((selection["top"] + selection["height"]) * scale_y))

        if right - left < 4 or bottom - top < 4:
            raise ValueError("Selected area is too small")

        cropped = full_image.crop((left, top, right, bottom))
        return self.decode_from_image(cropped)
