"""services/multisite/packaging.py
==================================
Enterprise Deployment Profiles, Systemd Lifecycle & Packaging Engine (Workstream 13G).

Governs:
1. Turnkey deployment profiles (simulation, staging, single-site-production, multi-site-production).
2. Strict enforcement of Phase 8.2 Physical Commissioning Gating (HARD_PRODUCTION_DENY).
3. Hardened, sandboxed systemd service unit generation for Hub, Regional Proxy, and Edge Collector.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

logger = logging.getLogger("nawari.multisite.packaging")


class DeploymentTier(str, Enum):
    SIMULATION = "simulation"
    STAGING = "staging"
    SINGLE_SITE_PRODUCTION = "single-site-production"
    MULTI_SITE_PRODUCTION = "multi-site-production"


class PackagingTarget(str, Enum):
    HUB_FULL = "hub-full"
    REGIONAL_PROXY = "regional-proxy"
    EDGE_COLLECTOR = "edge-collector"


class ProductionGatingViolation(PermissionError):
    """Raised when an attempt is made to initialize a production profile without Phase 8.2 certification."""
    pass


@dataclass
class SystemdServiceConfig:
    """Configuration for systemd service generation."""
    unit_name: str
    description: str
    target: PackagingTarget
    exec_start: str
    user: str = "nawari"
    group: str = "nawari"
    working_directory: str = "/opt/nawari"
    memory_max_mb: int = 512
    cpu_quota_pct: int = 50
    restart_sec: int = 5
    watchdog_sec: int = 30


class DeploymentProfileManager:
    """Manages profile loading, schema validation, and physical production gate verification."""

    def __init__(self, profiles_dir: Optional[str] = None) -> None:
        if profiles_dir:
            self.profiles_dir = Path(profiles_dir)
        else:
            self.profiles_dir = Path(__file__).resolve().parent.parent.parent / "deploy" / "profiles"

    def load_profile(self, profile_name: str) -> Dict[str, Any]:
        """Load YAML configuration for the named profile."""
        profile_file = self.profiles_dir / f"{profile_name}.yaml"
        if not profile_file.exists():
            raise FileNotFoundError(f"Deployment profile not found: {profile_file}")

        with open(profile_file, "r") as f:
            data = yaml.safe_load(f)
        return data

    def validate_deployment_eligibility(
        self,
        profile_name: str,
        is_phase_8_2_certified: bool = False,
    ) -> Dict[str, Any]:
        """Verify whether target environment is permitted to launch the given profile.

        ENFORCES HARD_PRODUCTION_DENY FOR PRODUCTION PROFILES WITHOUT PHASE 8.2 CERTIFICATE.
        """
        profile = self.load_profile(profile_name)
        requires_commissioning = profile.get("phase_8_2_commissioning_required", False)

        if requires_commissioning and not is_phase_8_2_certified:
            return {
                "allowed": False,
                "status": "HARD_PRODUCTION_DENY",
                "profile_name": profile_name,
                "reason": (
                    "Phase 8.2 physical enterprise commissioning has not been executed. "
                    "Autonomous mutations against live Kenya Airways infrastructure remain strictly prohibited."
                ),
                "required_gate": "PHASE_8_2_PHYSICAL_COMMISSIONING",
            }

        return {
            "allowed": True,
            "status": "APPROVED_FOR_DEPLOYMENT",
            "profile_name": profile_name,
            "tier": profile.get("tier"),
            "live_mutation_allowed": profile.get("live_mutation_allowed", False),
        }

    def assert_deployment_allowed(self, profile_name: str, is_phase_8_2_certified: bool = False) -> None:
        """Helper that raises ProductionGatingViolation if deployment is denied."""
        eligibility = self.validate_deployment_eligibility(profile_name, is_phase_8_2_certified)
        if not eligibility["allowed"]:
            raise ProductionGatingViolation(f"[{eligibility['status']}] {eligibility['reason']}")


class SystemdUnitGenerator:
    """Generates production-grade, hardened Linux systemd service unit files."""

    @classmethod
    def generate_unit(cls, config: SystemdServiceConfig) -> str:
        """Render a hardened systemd unit file with security restrictions."""
        return f"""[Unit]
Description={config.description}
After=network.target network-online.target
Wants=network-online.target
Documentation=https://docs.kenya-airways.com/nawari

[Service]
Type=simple
User={config.user}
Group={config.group}
WorkingDirectory={config.working_directory}
ExecStart={config.exec_start}
Restart=always
RestartSec={config.restart_sec}s
TimeoutStopSec=15s
WatchdogSec={config.watchdog_sec}s

# Resource Constraints
MemoryMax={config.memory_max_mb}M
CPUQuota={config.cpu_quota_pct}%

# Linux Sandboxing & Hardening Directives
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
PrivateTmp=true
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_RAW

[Install]
WantedBy=multi-user.target
"""

    @classmethod
    def get_standard_hub_config(cls) -> SystemdServiceConfig:
        return SystemdServiceConfig(
            unit_name="nawari-hub.service",
            description="Nawari Central Hub Enterprise Observability & Service Assurance Engine",
            target=PackagingTarget.HUB_FULL,
            exec_start="/opt/nawari/bin/python3 -m services.hub_daemon",
            memory_max_mb=768,
            cpu_quota_pct=80,
        )

    @classmethod
    def get_standard_proxy_config(cls) -> SystemdServiceConfig:
        return SystemdServiceConfig(
            unit_name="nawari-regional-proxy.service",
            description="Nawari Regional Concentrator & Active Telemetry Proxy",
            target=PackagingTarget.REGIONAL_PROXY,
            exec_start="/opt/nawari/bin/python3 -m services.proxy_daemon",
            memory_max_mb=256,
            cpu_quota_pct=40,
        )

    @classmethod
    def get_standard_edge_config(cls) -> SystemdServiceConfig:
        return SystemdServiceConfig(
            unit_name="nawari-edge-collector.service",
            description="Nawari Outstation Edge Telemetry Collector & Spool Forwarder",
            target=PackagingTarget.EDGE_COLLECTOR,
            exec_start="/opt/nawari/bin/python3 -m services.edge_daemon",
            memory_max_mb=128,
            cpu_quota_pct=25,
        )

