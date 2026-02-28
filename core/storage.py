from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class StorageManager:
    """JSON-based storage manager for AuthDeck accounts."""

    _PIN_ITERATIONS = 240_000
    _BACKUP_KDF_ITERATIONS = 600_000
    _BACKUP_SALT_BYTES = 16
    _BACKUP_NONCE_BYTES = 12

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._accounts: list[dict[str, Any]] = []
        self._security: dict[str, Any] = {}
        self._settings: dict[str, Any] = {}
        self._load()

    @property
    def accounts(self) -> list[dict[str, Any]]:
        return self._accounts

    @property
    def pin_enabled(self) -> bool:
        pin = self._security.get("pin", {})
        return isinstance(pin, dict) and bool(pin.get("hash") and pin.get("salt"))

    def _load(self) -> None:
        if not self.file_path.exists():
            self._accounts = []
            self._save()
            return

        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
            accounts = payload.get("accounts", [])
            if not isinstance(accounts, list):
                raise ValueError("Invalid accounts format")
            security = payload.get("security", {})
            if not isinstance(security, dict):
                security = {}
            settings = payload.get("settings", {})
            if not isinstance(settings, dict):
                settings = {}
            self._accounts = [self._normalize_account(account) for account in accounts]
            self._security = security
            self._settings = settings
        except Exception:
            self._accounts = []
            self._security = {}
            self._settings = {}
            self._save()

    def _save(self) -> None:
        payload = {
            "accounts": self._accounts,
            "security": self._security,
            "settings": self._settings,
        }
        self.file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_theme(self) -> str:
        theme = str(self._settings.get("theme", "dark")).lower().strip()
        return "light" if theme == "light" else "dark"

    def set_theme(self, theme: str) -> None:
        normalized = "light" if str(theme).lower().strip() == "light" else "dark"
        if self._settings.get("theme") == normalized:
            return
        self._settings["theme"] = normalized
        self._save()

    def add_account(self, account: dict[str, Any]) -> None:
        self._accounts.append(self._normalize_account(account))
        self._save()

    def update_account(self, index: int, account: dict[str, Any]) -> None:
        self._accounts[index] = self._normalize_account(account)
        self._save()

    def rename_account(self, index: int, new_name: str) -> None:
        self._accounts[index]["name"] = new_name.strip() or self._accounts[index]["name"]
        self._save()

    def delete_account(self, index: int) -> None:
        del self._accounts[index]
        self._save()

    def move_account(self, from_index: int, to_index: int) -> None:
        if from_index < 0 or from_index >= len(self._accounts):
            return
        if to_index < 0 or to_index >= len(self._accounts):
            return
        if from_index == to_index:
            return

        account = self._accounts.pop(from_index)
        self._accounts.insert(to_index, account)
        self._save()

    def export_backup(self, destination: Path, password: str) -> None:
        salt = secrets.token_bytes(self._BACKUP_SALT_BYTES)
        nonce = secrets.token_bytes(self._BACKUP_NONCE_BYTES)
        key = self._derive_backup_key(password, salt, self._BACKUP_KDF_ITERATIONS)

        plaintext_payload = {"accounts": self._accounts}
        plaintext = json.dumps(plaintext_payload, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)

        payload = {
            "version": 2,
            "encrypted": True,
            "kdf": {
                "name": "pbkdf2_sha256",
                "iterations": self._BACKUP_KDF_ITERATIONS,
                "salt": base64.b64encode(salt).decode("ascii"),
            },
            "cipher": {
                "name": "aes-256-gcm",
                "nonce": base64.b64encode(nonce).decode("ascii"),
            },
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_backup(self, source: Path, password: str | None = None) -> None:
        payload = json.loads(source.read_text(encoding="utf-8"))

        if bool(payload.get("encrypted")):
            if not password:
                raise ValueError("Backup password is required for this backup")

            kdf_info = payload.get("kdf", {})
            cipher_info = payload.get("cipher", {})
            if not isinstance(kdf_info, dict) or not isinstance(cipher_info, dict):
                raise ValueError("Invalid encrypted backup format")

            encoded_salt = kdf_info.get("salt")
            encoded_nonce = cipher_info.get("nonce")
            encoded_ciphertext = payload.get("ciphertext")
            iterations = int(kdf_info.get("iterations", self._BACKUP_KDF_ITERATIONS) or self._BACKUP_KDF_ITERATIONS)
            if not encoded_salt or not encoded_nonce or not encoded_ciphertext:
                raise ValueError("Invalid encrypted backup format")

            try:
                salt = base64.b64decode(encoded_salt)
                nonce = base64.b64decode(encoded_nonce)
                ciphertext = base64.b64decode(encoded_ciphertext)
                key = self._derive_backup_key(password, salt, iterations)
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
                decrypted_payload = json.loads(plaintext.decode("utf-8"))
            except Exception as error:  # noqa: BLE001
                raise ValueError("Incorrect backup password or corrupted backup file") from error

            accounts = decrypted_payload.get("accounts", [])
        else:
            accounts = payload.get("accounts", [])

        if not isinstance(accounts, list):
            raise ValueError("Backup file must include an accounts list")

        self._accounts = [self._normalize_account(account) for account in accounts]
        self._save()

    def is_backup_encrypted(self, source: Path) -> bool:
        payload = json.loads(source.read_text(encoding="utf-8"))
        return bool(payload.get("encrypted"))

    def _derive_backup_key(self, password: str, salt: bytes, iterations: int) -> bytes:
        if len(password) < 8:
            raise ValueError("Backup password must be at least 8 characters")
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=32,
        )

    def set_pin(self, pin: str) -> None:
        pin_bytes = pin.strip().encode("utf-8")
        if len(pin_bytes) != 4 or not pin.strip().isdigit():
            raise ValueError("PIN must be exactly 4 digits")

        salt = secrets.token_bytes(16)
        pin_hash = hashlib.pbkdf2_hmac("sha256", pin_bytes, salt, self._PIN_ITERATIONS)
        self._security["pin"] = {
            "hash": base64.b64encode(pin_hash).decode("ascii"),
            "salt": base64.b64encode(salt).decode("ascii"),
            "iterations": self._PIN_ITERATIONS,
            "algorithm": "pbkdf2_sha256",
        }
        self._save()

    def clear_pin(self) -> None:
        self._security.pop("pin", None)
        self._save()

    def verify_pin(self, pin: str) -> bool:
        pin_record = self._security.get("pin", {})
        if not isinstance(pin_record, dict):
            return False

        encoded_hash = pin_record.get("hash")
        encoded_salt = pin_record.get("salt")
        iterations = int(pin_record.get("iterations", self._PIN_ITERATIONS) or self._PIN_ITERATIONS)
        if not encoded_hash or not encoded_salt:
            return False

        try:
            expected_hash = base64.b64decode(encoded_hash)
            salt = base64.b64decode(encoded_salt)
        except Exception:
            return False

        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            pin.strip().encode("utf-8"),
            salt,
            iterations,
        )
        return secrets.compare_digest(expected_hash, candidate_hash)

    def reset_all_data_for_forgot_pin(self) -> None:
        self._accounts = []
        self._security = {}
        self._settings = {}
        self._save()

    def _normalize_account(self, account: dict[str, Any]) -> dict[str, Any]:
        # Keep structure encryption-ready and strict.
        normalized = {
            "name": str(account.get("name", "Account")).strip() or "Account",
            "issuer": str(account.get("issuer", "")).strip(),
            "account": str(account.get("account", "")).strip(),
            "secret": str(account.get("secret", "")).strip().replace(" ", ""),
            "digits": int(account.get("digits", 6) or 6),
            "period": int(account.get("period", 30) or 30),
            "algorithm": str(account.get("algorithm", "sha1")).lower(),
        }
        if not normalized["secret"]:
            raise ValueError("Account secret is required")
        return normalized
