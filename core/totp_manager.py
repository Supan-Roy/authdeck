from __future__ import annotations

import hashlib
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pyotp


class TOTPManager:
    """Handles parsing and generation of TOTP codes."""

    _DIGEST_MAP = {
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }

    def parse_otpauth_url(self, otpauth_url: str) -> dict[str, Any]:
        """Parse an otpauth URI into a normalized account dictionary."""
        parsed = urlparse(otpauth_url)
        if parsed.scheme != "otpauth" or parsed.netloc.lower() != "totp":
            raise ValueError("Only otpauth://totp URLs are supported")

        label = unquote(parsed.path.lstrip("/"))
        label_issuer = ""
        account_name = label
        if ":" in label:
            label_issuer, account_name = [value.strip() for value in label.split(":", 1)]

        query = parse_qs(parsed.query)
        secret = (query.get("secret", [""])[0] or "").replace(" ", "")
        if not secret:
            raise ValueError("Missing secret in otpauth URL")

        issuer = query.get("issuer", [label_issuer])[0] or label_issuer
        digits = int(query.get("digits", ["6"])[0])
        period = int(query.get("period", ["30"])[0])
        algorithm = (query.get("algorithm", ["SHA1"])[0] or "SHA1").lower()

        return {
            "name": issuer or account_name or "Account",
            "issuer": issuer or "",
            "account": account_name or "",
            "secret": secret,
            "digits": digits,
            "period": period,
            "algorithm": algorithm,
        }

    def current_code(self, account: dict[str, Any]) -> str:
        """Generate the current TOTP code for an account."""
        period = int(account.get("period", 30) or 30)
        digits = int(account.get("digits", 6) or 6)
        algorithm = str(account.get("algorithm", "sha1")).lower()
        digest = self._DIGEST_MAP.get(algorithm, hashlib.sha1)

        totp = pyotp.TOTP(
            account["secret"],
            digits=digits,
            interval=period,
            digest=digest,
        )
        return totp.now()

    def seconds_remaining(self, account: dict[str, Any]) -> int:
        """Return number of seconds until current code expires."""
        period = int(account.get("period", 30) or 30)
        return period - (int(time.time()) % period)

    def current_code_with_remaining(self, account: dict[str, Any]) -> tuple[str, int]:
        """Return current code and seconds remaining."""
        return self.current_code(account), self.seconds_remaining(account)
