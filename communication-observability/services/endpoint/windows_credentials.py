"""Local-machine DPAPI storage for the Windows service credential."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def credential_path() -> Path:
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    return Path(program_data) / "Nawari" / "Endpoint Agent" / "credential.bin"


def store_token(token: str) -> None:
    if os.name != "nt":
        raise RuntimeError("DPAPI credential storage is available only on Windows")
    if not token or len(token) < 16:
        raise ValueError("The enrollment or agent token is missing or too short")

    import win32crypt  # type: ignore[import-not-found]

    target = credential_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    description = "Nawari Endpoint Agent machine credential"
    encrypted = win32crypt.CryptProtectData(
        token.encode("utf-8"), description, None, None, None, 0x4
    )
    target.write_bytes(encrypted)


def store_token_from_stdin() -> None:
    if sys.stdin.isatty():
        raise RuntimeError("credential-store accepts the token through redirected standard input only")
    store_token(sys.stdin.read().strip())


def load_token() -> str:
    if os.name != "nt":
        raise RuntimeError("DPAPI credential storage is available only on Windows")

    import win32crypt  # type: ignore[import-not-found]

    encrypted = credential_path().read_bytes()
    _description, clear = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
    token = clear.decode("utf-8")
    if not token:
        raise RuntimeError("The protected Nawari agent credential is empty")
    return token
