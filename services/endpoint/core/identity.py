"""Persistent and secure endpoint agent identity management."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class IdentityCorruptError(Exception):
    """Raised when the stored identity file is corrupt or unparseable."""
    pass


@dataclass(frozen=True)
class EndpointIdentity:
    """Immutable persistent identity of an enrolled endpoint agent."""
    agent_id: str
    enrolled_at: str
    hostname: str
    re_registration_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EndpointIdentity:
        # Validate UUID format
        agent_id = data.get("agent_id", "")
        try:
            uuid.UUID(agent_id, version=4)
        except (ValueError, TypeError, AttributeError) as exc:
            raise IdentityCorruptError(f"Stored agent_id '{agent_id}' is not a valid UUIDv4: {exc}") from exc

        return cls(
            agent_id=agent_id,
            enrolled_at=data.get("enrolled_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            hostname=data.get("hostname", os.uname().nodename if hasattr(os, "uname") else "unknown"),
            re_registration_count=int(data.get("re_registration_count", 0)),
        )


def mask_agent_id(agent_id: str) -> str:
    """Mask a UUID agent ID for safe presentation in standard logs.

    Example: 'e4b3c2a1-0000-4000-8000-123456789abc' -> 'e4b3****-****-****-****-****9abc'
    """
    if not agent_id or len(agent_id) < 12:
        return "********"
    return f"{agent_id[:4]}****-****-****-****-****{agent_id[-4:]}"


class IdentityManager:
    """Manages atomic persistence, recovery, and lifecycle of the agent identity."""

    def __init__(self, state_path: Optional[str] = None) -> None:
        if state_path:
            self.state_file = Path(state_path).expanduser().resolve()
        else:
            default_dir = Path.home() / ".nawari"
            self.state_file = default_dir / "agent_identity.json"

        self._identity: Optional[EndpointIdentity] = None

    @property
    def identity(self) -> EndpointIdentity:
        """Return the current identity, loading or initializing if necessary."""
        if self._identity is None:
            self._identity = self.load_or_create()
        return self._identity

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    def load_or_create(self) -> EndpointIdentity:
        """Load identity from disk, or atomically generate a new one if not present."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        raise IdentityCorruptError("Identity file is empty")
                    data = json.loads(content)
                    return EndpointIdentity.from_dict(data)
            except (json.JSONDecodeError, IdentityCorruptError, KeyError) as exc:
                # Safely back up corrupted file rather than crashing or silently overwriting
                corrupt_backup = self.state_file.with_name(
                    f"{self.state_file.name}.corrupt.{int(time.time())}"
                )
                try:
                    shutil.copy2(self.state_file, corrupt_backup)
                except Exception:
                    pass
                # Generate replacement identity
                new_id = self._generate_new_identity(re_reg_count=1)
                self._save_atomic(new_id)
                return new_id
            except Exception as exc:
                raise IdentityCorruptError(f"Unexpected error loading identity: {exc}") from exc

        # First run: generate clean identity
        new_id = self._generate_new_identity(re_reg_count=0)
        self._save_atomic(new_id)
        return new_id

    def re_register(self, force: bool = False) -> EndpointIdentity:
        """Explicitly re-register and generate a new agent identity."""
        current_count = self._identity.re_registration_count if self._identity else 0
        new_id = self._generate_new_identity(re_reg_count=current_count + 1)
        self._save_atomic(new_id)
        self._identity = new_id
        return new_id

    def _generate_new_identity(self, re_reg_count: int) -> EndpointIdentity:
        hostname = os.uname().nodename if hasattr(os, "uname") else "unknown"
        return EndpointIdentity(
            agent_id=str(uuid.uuid4()),
            enrolled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            hostname=hostname,
            re_registration_count=re_reg_count,
        )

    def _save_atomic(self, identity: EndpointIdentity) -> None:
        """Atomically persist identity file using tempfile rename to avoid partial writes."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(identity.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Secure file permissions (0600: read/write by owner only)
            try:
                os.chmod(tmp_file, 0o600)
            except Exception:
                pass

            tmp_file.replace(self.state_file)
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass
