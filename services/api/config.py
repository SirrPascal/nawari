"""Configuration loader and typed settings for Nawari services."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def find_project_root() -> Path:
    """Traverse up to locate the project root containing .env or docker/."""
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / ".env").exists() or (current / "docker" / "compose.yaml").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path.cwd()


def load_env_file(env_path: Optional[Path] = None) -> dict[str, str]:
    """Parse .env file into a dictionary without overriding existing os.environ."""
    if env_path is None:
        env_path = find_project_root() / ".env"
    
    loaded = {}
    if not env_path.exists():
        return loaded

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                loaded[k] = v
                # Also set in os.environ if not already present
                if k not in os.environ:
                    os.environ[k] = v
    return loaded


_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def resolve_secret_reference(value: str) -> str:
    """Resolve environment variable expressions like ${SECRET_NAME:-default}."""
    if not isinstance(value, str):
        return value

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    return _ENV_REF_PATTERN.sub(_replace, value)


@dataclass
class ZabbixSettings:
    """Zabbix JSON-RPC client connection settings."""
    url: str = "http://localhost:8088/api_jsonrpc.php"
    token: Optional[str] = None
    user: str = "Admin"
    password: str = ""
    timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_factor: float = 0.5


@dataclass
class NawariSettings:
    """Global configuration for Nawari backend and provisioning engine."""
    env: str = "development"
    project_root: Path = field(default_factory=find_project_root)
    provisioning_dir: Path = field(init=False)
    zabbix: ZabbixSettings = field(default_factory=ZabbixSettings)

    def __post_init__(self):
        self.provisioning_dir = self.project_root / "provisioning" / "zabbix"


def get_settings() -> NawariSettings:
    """Load settings from environment and .env file."""
    load_env_file()
    
    # Priority for Zabbix URL:
    # 1. ZBX_API_URL or ZABBIX_URL
    # 2. http://localhost:${ZBX_WEB_PORT:-8088}/api_jsonrpc.php
    web_port = os.environ.get("ZBX_WEB_PORT", "8088")
    default_url = f"http://localhost:{web_port}/api_jsonrpc.php"
    zabbix_url = os.environ.get("ZABBIX_URL", os.environ.get("ZBX_API_URL", default_url))
    
    zabbix_token = os.environ.get("ZBX_API_TOKEN") or None
    zabbix_user = os.environ.get("ZBX_API_USER", "Admin")
    zabbix_password = os.environ.get("ZBX_API_PASSWORD", "")
    if not zabbix_token and not zabbix_password:
        raise ValueError(
            "ZBX_API_PASSWORD or ZBX_API_TOKEN must be configured for Zabbix access"
        )

    zbx_settings = ZabbixSettings(
        url=zabbix_url,
        token=zabbix_token,
        user=zabbix_user,
        password=zabbix_password,
        timeout_seconds=float(os.environ.get("ZBX_TIMEOUT", "10.0")),
        max_retries=int(os.environ.get("ZBX_MAX_RETRIES", "3")),
        backoff_factor=float(os.environ.get("ZBX_BACKOFF", "0.5")),
    )

    return NawariSettings(
        env=os.environ.get("NAWARI_ENV", "development"),
        zabbix=zbx_settings,
    )
