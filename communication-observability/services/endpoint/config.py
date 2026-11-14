"""Configuration and target policy models for the Nawari Endpoint Agent.

Strictly enforces the Zero-Remote-Execution (Zero-RCE) principle:
- Validates targets against allowed domain and subnet whitelists.
- Rejects shell metacharacters and invalid hostnames/IPs.
- Enforces strict numeric bounds on intervals and timeouts.
"""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.endpoint.models import ServiceProtocol, TelemetricEnvironment

HOSTNAME_REGEX = re.compile(
    r"^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
)
DANGEROUS_CHARS_REGEX = re.compile(r"[;`$&|<>\\\n\r\t\"']")


class ConfigurationError(Exception):
    """Raised when agent configuration or target policy violates validation rules."""
    pass


@dataclass(frozen=True)
class TargetPolicy:
    """Diagnostic target policy configuration."""
    target_id: str
    target_name: str
    destination: str
    port: Optional[int] = None
    protocol: ServiceProtocol = ServiceProtocol.ICMP
    traceroute_enabled: bool = True
    max_hops: int = 30
    timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        # Zero-RCE Invariant: No shell metacharacters
        if DANGEROUS_CHARS_REGEX.search(self.destination) or DANGEROUS_CHARS_REGEX.search(self.target_id):
            raise ConfigurationError(
                f"Target destination or ID contains forbidden shell metacharacters: {self.destination}"
            )

        # Validate destination is IP or RFC-compliant hostname
        is_ip = False
        try:
            ipaddress.ip_address(self.destination)
            is_ip = True
        except ValueError:
            is_ip = False

        if not is_ip and not HOSTNAME_REGEX.match(self.destination):
            raise ConfigurationError(
                f"Target destination '{self.destination}' is neither a valid IP address nor a valid RFC hostname"
            )

        # Port validation
        if self.port is not None and not (1 <= self.port <= 65535):
            raise ConfigurationError(f"Target port out of range [1, 65535]: {self.port}")

        # Hops validation
        if not (1 <= self.max_hops <= 64):
            raise ConfigurationError(f"max_hops out of range [1, 64]: {self.max_hops}")

        # Timeout validation
        if not (0.1 <= self.timeout_seconds <= 30.0):
            raise ConfigurationError(f"timeout_seconds out of range [0.1, 30.0]: {self.timeout_seconds}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "destination": self.destination,
            "port": self.port,
            "protocol": self.protocol.value,
            "traceroute_enabled": self.traceroute_enabled,
            "max_hops": self.max_hops,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TargetPolicy:
        return cls(
            target_id=data["target_id"],
            target_name=data.get("target_name", data["target_id"]),
            destination=data["destination"],
            port=data.get("port"),
            protocol=ServiceProtocol(data.get("protocol", "ICMP")),
            traceroute_enabled=bool(data.get("traceroute_enabled", True)),
            max_hops=int(data.get("max_hops", 30)),
            timeout_seconds=float(data.get("timeout_seconds", 3.0)),
        )


@dataclass(frozen=True)
class AgentConfig:
    """Top-level configuration for the endpoint agent."""
    agent_id: Optional[str] = None
    hostname: str = field(default_factory=lambda: os.uname().nodename if hasattr(os, "uname") else "unknown")
    state_dir: str = field(default_factory=lambda: str(Path.home() / ".nawari"))
    gateway_url: str = "http://127.0.0.1:8443"
    api_token: str = "nawari-dev-token"
    environment: TelemetricEnvironment = TelemetricEnvironment.MOCK_SIMULATED
    poll_interval_seconds: int = 60
    jitter_max_seconds: float = 10.0
    spool_dir: str = field(default_factory=lambda: str(Path.home() / ".nawari" / "spool"))
    max_spool_records: int = 1000
    max_spool_age_seconds: int = 7 * 24 * 60 * 60
    circuit_breaker_max_cpu_pct: float = 25.0
    allowed_domains: List[str] = field(default_factory=lambda: ["*.internal", "*.local", "localhost"])
    allowed_subnets: List[str] = field(default_factory=lambda: ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"])
    targets: List[TargetPolicy] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (5 <= self.poll_interval_seconds <= 3600):
            raise ConfigurationError(
                f"poll_interval_seconds out of range [5, 3600]: {self.poll_interval_seconds}"
            )
        if not (0.0 <= self.jitter_max_seconds <= 60.0):
            raise ConfigurationError(
                f"jitter_max_seconds out of range [0.0, 60.0]: {self.jitter_max_seconds}"
            )
        if not (10 <= self.max_spool_records <= 50000):
            raise ConfigurationError(
                f"max_spool_records out of range [10, 50000]: {self.max_spool_records}"
            )
        if not (60 <= self.max_spool_age_seconds <= 7 * 24 * 60 * 60):
            raise ConfigurationError(
                "max_spool_age_seconds must be between 60 seconds and seven days"
            )

    def validate_target_allowed(self, target: TargetPolicy) -> bool:
        """Verify target conforms to allowed subnets or domain whitelist."""
        # 1. Check if IP
        try:
            ip = ipaddress.ip_address(target.destination)
            for subnet_str in self.allowed_subnets:
                try:
                    if ip in ipaddress.ip_network(subnet_str):
                        return True
                except ValueError:
                    continue
            return False
        except ValueError:
            pass

        # 2. Check domain suffix
        dest = target.destination.lower()
        for domain_pattern in self.allowed_domains:
            pattern = domain_pattern.lower()
            if pattern.startswith("*."):
                suffix = pattern[1:]  # e.g. ".internal"
                if dest.endswith(suffix):
                    return True
            elif dest == pattern:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "hostname": self.hostname,
            "state_dir": self.state_dir,
            "gateway_url": self.gateway_url,
            "api_token": "***REDACTED***",
            "environment": self.environment.value,
            "poll_interval_seconds": self.poll_interval_seconds,
            "jitter_max_seconds": self.jitter_max_seconds,
            "spool_dir": self.spool_dir,
            "max_spool_records": self.max_spool_records,
            "max_spool_age_seconds": self.max_spool_age_seconds,
            "circuit_breaker_max_cpu_pct": self.circuit_breaker_max_cpu_pct,
            "allowed_domains": list(self.allowed_domains),
            "allowed_subnets": list(self.allowed_subnets),
            "targets": [t.to_dict() for t in self.targets],
        }

    @classmethod
    def load_from_dict(cls, data: Dict[str, Any]) -> AgentConfig:
        targets = [TargetPolicy.from_dict(t) for t in data.get("targets", [])]
        return cls(
            agent_id=data.get("agent_id"),
            hostname=data.get("hostname", os.uname().nodename if hasattr(os, "uname") else "unknown"),
            state_dir=data.get("state_dir", str(Path.home() / ".nawari")),
            gateway_url=data.get("gateway_url", "http://127.0.0.1:8443"),
            api_token=data.get("api_token", "nawari-dev-token"),
            environment=TelemetricEnvironment(data.get("environment", TelemetricEnvironment.MOCK_SIMULATED.value)),
            poll_interval_seconds=int(data.get("poll_interval_seconds", 60)),
            jitter_max_seconds=float(data.get("jitter_max_seconds", 10.0)),
            spool_dir=data.get("spool_dir", str(Path.home() / ".nawari" / "spool")),
            max_spool_records=int(data.get("max_spool_records", 1000)),
            max_spool_age_seconds=int(data.get("max_spool_age_seconds", 7 * 24 * 60 * 60)),
            circuit_breaker_max_cpu_pct=float(data.get("circuit_breaker_max_cpu_pct", 25.0)),
            allowed_domains=list(data.get("allowed_domains", ["*.internal", "*.local", "localhost"])),
            allowed_subnets=list(data.get("allowed_subnets", ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"])),
            targets=targets,
        )

    @classmethod
    def load_from_env(cls) -> AgentConfig:
        agent_id = os.getenv("NAWARI_AGENT_ID")
        hostname = os.getenv("NAWARI_AGENT_HOSTNAME", os.uname().nodename if hasattr(os, "uname") else "unknown")
        state_dir = os.getenv("NAWARI_STATE_DIR", str(Path.home() / ".nawari"))
        gateway_url = os.getenv("NAWARI_GATEWAY_URL", "http://127.0.0.1:8443")
        api_token = os.getenv("NAWARI_AGENT_TOKEN", "nawari-dev-token")
        env_str = os.getenv("NAWARI_ENVIRONMENT", TelemetricEnvironment.MOCK_SIMULATED.value)
        interval = int(os.getenv("NAWARI_POLL_INTERVAL", "60"))
        jitter = float(os.getenv("NAWARI_JITTER_SECONDS", "5.0"))
        spool_dir = os.getenv("NAWARI_SPOOL_DIR", str(Path.home() / ".nawari" / "spool"))
        max_spool_age_seconds = int(
            os.getenv("NAWARI_SPOOL_MAX_AGE_SECONDS", str(7 * 24 * 60 * 60))
        )

        default_targets = [
            TargetPolicy(
                target_id="avaya-sbce-sig-a1",
                target_name="Avaya SBCE Signaling A1",
                destination="127.0.0.1",
                port=5061,
                protocol=ServiceProtocol.TCP,
                traceroute_enabled=True,
                timeout_seconds=2.0,
            ),
            TargetPolicy(
                target_id="zabbix-web",
                target_name="Zabbix Web UI",
                destination="127.0.0.1",
                port=8088,
                protocol=ServiceProtocol.HTTP,
                traceroute_enabled=False,
                timeout_seconds=2.0,
            ),
        ]

        return cls(
            agent_id=agent_id,
            hostname=hostname,
            state_dir=state_dir,
            gateway_url=gateway_url,
            api_token=api_token,
            environment=TelemetricEnvironment(env_str),
            poll_interval_seconds=interval,
            jitter_max_seconds=jitter,
            spool_dir=spool_dir,
            max_spool_age_seconds=max_spool_age_seconds,
            targets=default_targets,
        )
