"""Configuration settings for Nawari Voice Observability Engine."""

import os
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
                if k not in os.environ:
                    os.environ[k] = v
    return loaded


@dataclass
class VoiceSettings:
    """Typed settings for Asterisk AMI connection, safety rules, and thresholds."""

    ami_host: str = "127.0.0.1"
    ami_port: int = 5038
    ami_user: str = "nawari"
    ami_secret: str = "nawari_ami_dev_secret"

    # Timeouts & Limits
    default_timeout_seconds: float = 15.0
    max_duration_seconds: float = 30.0
    cooldown_seconds: float = 5.0

    # Circuit breaker
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown_seconds: float = 60.0

    # Safety Allow/Deny Lists
    allowed_targets: list[str] = field(
        default_factory=lambda: ["1001", "1002", "1003", "1004", "8801", "8802"]
    )
    emergency_blacklist: set[str] = field(
        default_factory=lambda: {"911", "112", "999", "000", "100", "991"}
    )

    # Live Avaya Infrastructure Targets
    avaya_sbce_primary_ip: str = "10.2.156.131"
    avaya_sbce_secondary_ip: str = "10.2.156.130"
    avaya_sm_primary_ip: str = "10.2.156.40"
    avaya_sip_port: int = 5060

    # Staged Active Testing Controls
    options_ping_timeout_seconds: float = 3.0
    options_ping_interval_seconds: int = 60
    stage_prerequisite_window_seconds: float = 300.0

    # Dialplan contexts
    diagnostic_context: str = "nawari-diagnostic"
    outbound_context: str = "nawari-outbound"
    default_caller_id: str = "NawariSynthetic <1000>"

    # Paths
    state_dir: Path = field(default_factory=lambda: Path("/tmp/nawari_voice"))

    @property
    def lock_file_path(self) -> Path:
        return self.state_dir / "voice_call.lock"

    @property
    def circuit_breaker_state_path(self) -> Path:
        return self.state_dir / "circuit_breaker.json"

    @property
    def options_state_path(self) -> Path:
        return self.state_dir / "options_status.json"


def get_voice_settings() -> VoiceSettings:
    """Instantiate VoiceSettings populated from environment variables."""
    load_env_file()

    allowed_targets_env = os.environ.get("NAWARI_VOICE_ALLOWED_TARGETS")
    if allowed_targets_env:
        targets = [t.strip() for t in allowed_targets_env.split(",") if t.strip()]
    else:
        targets = ["1001", "1002", "1003", "1004", "8801", "8802"]

    state_dir_env = os.environ.get("NAWARI_VOICE_STATE_DIR")
    state_dir = Path(state_dir_env) if state_dir_env else Path("/tmp/nawari_voice")

    return VoiceSettings(
        ami_host=os.environ.get("ASTERISK_AMI_HOST", "127.0.0.1"),
        ami_port=int(os.environ.get("ASTERISK_AMI_PORT", "5038")),
        ami_user=os.environ.get("ASTERISK_AMI_USER", "nawari"),
        ami_secret=os.environ.get("ASTERISK_AMI_SECRET", "nawari_ami_dev_secret"),
        default_timeout_seconds=float(os.environ.get("NAWARI_VOICE_TIMEOUT", "15.0")),
        max_duration_seconds=float(os.environ.get("NAWARI_VOICE_MAX_DURATION", "30.0")),
        cooldown_seconds=float(os.environ.get("NAWARI_VOICE_COOLDOWN", "5.0")),
        circuit_breaker_threshold=int(os.environ.get("NAWARI_CIRCUIT_BREAKER_THRESHOLD", "3")),
        circuit_breaker_cooldown_seconds=float(
            os.environ.get("NAWARI_CIRCUIT_BREAKER_COOLDOWN", "60.0")
        ),
        allowed_targets=targets,
        diagnostic_context=os.environ.get("NAWARI_VOICE_DIAGNOSTIC_CONTEXT", "nawari-diagnostic"),
        outbound_context=os.environ.get("NAWARI_VOICE_OUTBOUND_CONTEXT", "nawari-outbound"),
        default_caller_id=os.environ.get("NAWARI_VOICE_CALLER_ID", "NawariSynthetic <1000>"),
        state_dir=state_dir,
    )

