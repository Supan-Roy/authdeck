from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any


class StorageManager:
    """JSON-based storage manager for AuthDeck accounts."""

    _PIN_ITERATIONS = 240_000

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._accounts: list[dict[str, Any]] = []
        self._security: dict[str, Any] = {}
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
            self._accounts = [self._normalize_account(account) for account in accounts]
            self._security = security
        except Exception:
            self._accounts = []
            self._security = {}
            self._save()

    def _save(self) -> None:
        payload = {"accounts": self._accounts, "security": self._security}
        self.file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

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

    def export_backup(self, destination: Path) -> None:
        payload = {"accounts": self._accounts}
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_backup(self, source: Path) -> None:
        payload = json.loads(source.read_text(encoding="utf-8"))
        accounts = payload.get("accounts", [])
        if not isinstance(accounts, list):
            raise ValueError("Backup file must include an accounts list")

        self._accounts = [self._normalize_account(account) for account in accounts]
        self._save()

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
