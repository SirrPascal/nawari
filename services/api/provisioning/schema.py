"""Desired-state schema and YAML parser for Nawari monitoring declarations."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import yaml

from services.api.client.models import (
    InterfaceType,
    MacroType,
    SNMPAuthProtocol,
    SNMPPrivProtocol,
    SNMPSecurityLevel,
    SNMPVersion,
)
from services.api.config import resolve_secret_reference


@dataclass
class DesiredHostGroup:
    name: str
    description: str = ""


@dataclass
class DesiredInterfaceDetails:
    version: int = SNMPVersion.SNMP_V2C
    community: str = "{$SNMP_COMMUNITY}"
    securityname: str = ""
    securitylevel: int = SNMPSecurityLevel.NO_AUTH_NO_PRIV
    authprotocol: int = SNMPAuthProtocol.SHA1
    authpassphrase: str = ""
    privprotocol: int = SNMPPrivProtocol.AES128
    privpassphrase: str = ""
    contextname: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesiredInterfaceDetails":
        version_raw = data.get("version", 2)
        if isinstance(version_raw, str):
            v_lower = version_raw.lower()
            if "3" in v_lower:
                version = SNMPVersion.SNMP_V3
            elif "1" in v_lower:
                version = SNMPVersion.SNMP_V1
            else:
                version = SNMPVersion.SNMP_V2C
        else:
            version = int(version_raw)

        # Security level mapping
        sec_level_raw = resolve_secret_reference(str(data.get("securitylevel", 0)))
        if isinstance(sec_level_raw, str):
            s_lower = sec_level_raw.lower()
            if "priv" in s_lower:
                sec_level = SNMPSecurityLevel.AUTH_PRIV
            elif "auth" in s_lower:
                sec_level = SNMPSecurityLevel.AUTH_NO_PRIV
            else:
                sec_level = SNMPSecurityLevel.NO_AUTH_NO_PRIV
        else:
            sec_level = int(sec_level_raw)

        # Protocol mappings
        auth_proto_str = resolve_secret_reference(str(data.get("authprotocol", "SHA1")))
        priv_proto_str = resolve_secret_reference(str(data.get("privprotocol", "AES128")))
        auth_proto = cls._parse_auth_protocol(auth_proto_str)
        priv_proto = cls._parse_priv_protocol(priv_proto_str)

        return cls(
            version=version,
            community=resolve_secret_reference(str(data.get("community", "{$SNMP_COMMUNITY}"))),
            securityname=resolve_secret_reference(str(data.get("securityname", ""))),
            securitylevel=sec_level,
            authprotocol=auth_proto,
            authpassphrase=resolve_secret_reference(str(data.get("authpassphrase", ""))),
            privprotocol=priv_proto,
            privpassphrase=resolve_secret_reference(str(data.get("privpassphrase", ""))),
            contextname=str(data.get("contextname", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "version": int(self.version),
            "community": self.community,
        }
        if self.version == SNMPVersion.SNMP_V3:
            res["securityname"] = self.securityname
            res["securitylevel"] = int(self.securitylevel)
            if self.securitylevel >= SNMPSecurityLevel.AUTH_NO_PRIV:
                res["authprotocol"] = int(self.authprotocol)
                res["authpassphrase"] = self.authpassphrase
            if self.securitylevel >= SNMPSecurityLevel.AUTH_PRIV:
                res["privprotocol"] = int(self.privprotocol)
                res["privpassphrase"] = self.privpassphrase
            if self.contextname:
                res["contextname"] = self.contextname
        return res

    @staticmethod
    def _parse_auth_protocol(val: Any) -> int:
        if isinstance(val, int):
            return val
        s = str(val).upper()
        if "SHA256" in s:
            return SNMPAuthProtocol.SHA256
        elif "SHA512" in s:
            return SNMPAuthProtocol.SHA512
        elif "SHA" in s:
            return SNMPAuthProtocol.SHA1
        elif "MD5" in s:
            return SNMPAuthProtocol.MD5
        return SNMPAuthProtocol.SHA1

    @staticmethod
    def _parse_priv_protocol(val: Any) -> int:
        if isinstance(val, int):
            return val
        s = str(val).upper()
        if "AES256" in s:
            return SNMPPrivProtocol.AES256
        elif "AES" in s:
            return SNMPPrivProtocol.AES128
        elif "DES" in s:
            return SNMPPrivProtocol.DES
        return SNMPPrivProtocol.AES128


@dataclass
class DesiredInterface:
    type: int = InterfaceType.AGENT
    ip: str = "127.0.0.1"
    port: str = "10050"
    main: int = 1
    useip: int = 1
    dns: str = ""
    details: Optional[DesiredInterfaceDetails] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesiredInterface":
        type_raw = data.get("type", "agent")
        if isinstance(type_raw, str):
            t_lower = type_raw.lower()
            if "snmp" in t_lower:
                if_type = InterfaceType.SNMP
            elif "ipmi" in t_lower:
                if_type = InterfaceType.IPMI
            elif "jmx" in t_lower:
                if_type = InterfaceType.JMX
            else:
                if_type = InterfaceType.AGENT
        else:
            if_type = int(type_raw)

        raw_port = str(data.get("port", "161" if if_type == InterfaceType.SNMP else "10050"))
        port = resolve_secret_reference(raw_port)
        details = None
        if "details" in data and if_type == InterfaceType.SNMP:
            details = DesiredInterfaceDetails.from_dict(data["details"])

        return cls(
            type=if_type,
            ip=resolve_secret_reference(str(data.get("ip", "127.0.0.1"))),
            port=port,
            main=int(data.get("main", 1)),
            useip=int(data.get("useip", 1)),
            dns=str(data.get("dns", "")),
            details=details,
        )


@dataclass
class DesiredMacro:
    macro: str
    value: str
    type: int = MacroType.TEXT
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesiredMacro":
        macro_name = str(data.get("macro", "")).strip()
        if not macro_name.startswith("{$"):
            macro_name = f"{{${macro_name.strip('{}')}}}"

        val = resolve_secret_reference(str(data.get("value", "")))
        type_raw = data.get("type", 0)
        if isinstance(type_raw, str):
            t_lower = type_raw.lower()
            m_type = MacroType.SECRET if "secret" in t_lower else MacroType.TEXT
        else:
            m_type = int(type_raw)

        return cls(
            macro=macro_name,
            value=val,
            type=m_type,
            description=str(data.get("description", "")),
        )


@dataclass
class DesiredTag:
    tag: str
    value: str


@dataclass
class DesiredHost:
    host: str
    name: str = ""
    status: int = 0
    description: str = ""
    groups: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    interfaces: list[DesiredInterface] = field(default_factory=list)
    macros: list[DesiredMacro] = field(default_factory=list)
    tags: list[DesiredTag] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesiredHost":
        host_key = str(data.get("host", "")).strip()
        name = str(data.get("name", host_key)).strip() or host_key
        status = int(data.get("status", 0))
        description = str(data.get("description", ""))

        groups = [str(g).strip() for g in data.get("groups", [])]
        templates = [str(t).strip() for t in data.get("templates", [])]

        interfaces = [DesiredInterface.from_dict(i) for i in data.get("interfaces", [])]
        macros = [DesiredMacro.from_dict(m) for m in data.get("macros", [])]
        tags = [
            DesiredTag(tag=str(t.get("tag", "")), value=str(t.get("value", "")))
            for t in data.get("tags", [])
        ]

        return cls(
            host=host_key,
            name=name,
            status=status,
            description=description,
            groups=groups,
            templates=templates,
            interfaces=interfaces,
            macros=macros,
            tags=tags,
        )


@dataclass
class DesiredState:
    host_groups: list[DesiredHostGroup] = field(default_factory=list)
    hosts: list[DesiredHost] = field(default_factory=list)


def load_desired_state_from_dir(directory: Path) -> DesiredState:
    """Recursively search directory for .yaml/.yml files and assemble DesiredState."""
    state = DesiredState()
    if not directory.exists():
        return state

    yaml_files = sorted(directory.rglob("*.yaml")) + sorted(directory.rglob("*.yml"))
    seen_groups = set()
    seen_hosts = set()

    for path in yaml_files:
        with open(path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)

        if not isinstance(content, dict):
            continue

        # Parse host groups
        for grp in content.get("host_groups", []):
            if isinstance(grp, str):
                name = grp.strip()
                if name and name not in seen_groups:
                    state.host_groups.append(DesiredHostGroup(name=name))
                    seen_groups.add(name)
            elif isinstance(grp, dict):
                name = str(grp.get("name", "")).strip()
                if name and name not in seen_groups:
                    desc = str(grp.get("description", ""))
                    state.host_groups.append(DesiredHostGroup(name=name, description=desc))
                    seen_groups.add(name)

        # Parse hosts
        for h in content.get("hosts", []):
            if isinstance(h, dict):
                dh = DesiredHost.from_dict(h)
                if dh.host and dh.host not in seen_hosts:
                    state.hosts.append(dh)
                    seen_hosts.add(dh.host)
                    # Implicitly register required groups
                    for grp_name in dh.groups:
                        if grp_name not in seen_groups:
                            state.host_groups.append(DesiredHostGroup(name=grp_name))
                            seen_groups.add(grp_name)

    return state
