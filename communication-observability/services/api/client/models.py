"""Data models and enums for Zabbix 7.4 entities."""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class InterfaceType(IntEnum):
    AGENT = 1
    SNMP = 2
    IPMI = 3
    JMX = 4


class SNMPVersion(IntEnum):
    SNMP_V1 = 1
    SNMP_V2C = 2
    SNMP_V3 = 3


class SNMPSecurityLevel(IntEnum):
    NO_AUTH_NO_PRIV = 0
    AUTH_NO_PRIV = 1
    AUTH_PRIV = 2


class SNMPAuthProtocol(IntEnum):
    MD5 = 0
    SHA1 = 1
    SHA224 = 2
    SHA256 = 3
    SHA384 = 4
    SHA512 = 5


class SNMPPrivProtocol(IntEnum):
    DES = 0
    AES128 = 1
    AES192 = 2
    AES256 = 3
    AES192C = 4
    AES256C = 5


class MacroType(IntEnum):
    TEXT = 0
    SECRET = 1
    VAULT = 2


class HostStatus(IntEnum):
    MONITORED = 0
    UNMONITORED = 1


@dataclass
class HostGroup:
    groupid: Optional[str] = None
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {"name": self.name}
        if self.groupid:
            data["groupid"] = self.groupid
        return data


@dataclass
class Template:
    templateid: Optional[str] = None
    host: str = ""
    name: str = ""


@dataclass
class HostInterfaceDetails:
    version: int = SNMPVersion.SNMP_V2C
    community: str = "{$SNMP_COMMUNITY}"
    securityname: str = ""
    securitylevel: int = SNMPSecurityLevel.NO_AUTH_NO_PRIV
    authprotocol: int = SNMPAuthProtocol.SHA1
    authpassphrase: str = ""
    privprotocol: int = SNMPPrivProtocol.AES128
    privpassphrase: str = ""
    contextname: str = ""

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


@dataclass
class HostInterface:
    interfaceid: Optional[str] = None
    hostid: Optional[str] = None
    main: int = 1
    type: int = InterfaceType.AGENT
    useip: int = 1
    ip: str = "127.0.0.1"
    dns: str = ""
    port: str = "10050"
    details: Optional[HostInterfaceDetails] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "main": int(self.main),
            "type": int(self.type),
            "useip": int(self.useip),
            "ip": self.ip,
            "dns": self.dns,
            "port": str(self.port),
        }
        if self.interfaceid:
            data["interfaceid"] = self.interfaceid
        if self.details and self.type == InterfaceType.SNMP:
            data["details"] = self.details.to_dict()
        return data


@dataclass
class HostMacro:
    macro: str
    value: str
    type: int = MacroType.TEXT
    description: str = ""
    hostmacroid: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "macro": self.macro,
            "value": self.value,
            "type": int(self.type),
        }
        if self.description:
            data["description"] = self.description
        if self.hostmacroid:
            data["hostmacroid"] = self.hostmacroid
        return data


@dataclass
class HostTag:
    tag: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return {"tag": self.tag, "value": self.value}


@dataclass
class Host:
    host: str
    name: str = ""
    status: int = HostStatus.MONITORED
    description: str = ""
    hostid: Optional[str] = None
    groups: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    interfaces: list[HostInterface] = field(default_factory=list)
    macros: list[HostMacro] = field(default_factory=list)
    tags: list[HostTag] = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            self.name = self.host

