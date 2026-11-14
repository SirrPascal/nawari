"""OS platform abstraction layer for cross-platform network diagnostics."""

from __future__ import annotations

import platform as py_platform

from services.endpoint.os_platform.base import PlatformAdapter, PlatformCapabilities
from services.endpoint.os_platform.darwin import DarwinAdapter
from services.endpoint.os_platform.linux import LinuxAdapter
from services.endpoint.os_platform.windows import WindowsAdapter


def get_platform_adapter() -> PlatformAdapter:
    """Detect current operating system and return the appropriate PlatformAdapter."""
    system = py_platform.system().lower()
    if system == "darwin":
        return DarwinAdapter()
    elif system == "linux":
        return LinuxAdapter()
    elif system == "windows":
        return WindowsAdapter()
    else:
        # Fallback to Darwin/Linux generic adapter
        return DarwinAdapter()


__all__ = [
    "PlatformAdapter",
    "PlatformCapabilities",
    "DarwinAdapter",
    "LinuxAdapter",
    "WindowsAdapter",
    "get_platform_adapter",
]
