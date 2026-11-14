"""
Nawari Phase 8 — Role-Based Access Control (RBAC) Module
Implements enterprise role definitions, granular resource permissions, and policy evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Set


class Role(str, Enum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    NETWORK_ENGINEER = "NETWORK_ENGINEER"
    VOICE_ENGINEER = "VOICE_ENGINEER"
    SERVICE_OPERATIONS = "SERVICE_OPERATIONS"
    SECURITY_AUDITOR = "SECURITY_AUDITOR"
    ENDPOINT_ADMIN = "ENDPOINT_ADMIN"


class Permission(str, Enum):
    # Platform Administration
    PLATFORM_CONFIGURE = "PLATFORM_CONFIGURE"
    USER_MANAGE = "USER_MANAGE"
    SECRETS_MANAGE = "SECRETS_MANAGE"

    # Network Engineering
    NETWORK_VIEW = "NETWORK_VIEW"
    NETWORK_OPERATE = "NETWORK_OPERATE"

    # Voice / Telephony
    VOICE_VIEW = "VOICE_VIEW"
    VOICE_OPERATE = "VOICE_OPERATE"

    # Incidents & Assurance
    INCIDENT_VIEW = "INCIDENT_VIEW"
    INCIDENT_ACKNOWLEDGE = "INCIDENT_ACKNOWLEDGE"
    INCIDENT_RESOLVE = "INCIDENT_RESOLVE"

    # Endpoint Management
    ENDPOINT_VIEW = "ENDPOINT_VIEW"
    ENDPOINT_MANAGE = "ENDPOINT_MANAGE"

    # Security & Audit
    AUDIT_VIEW = "AUDIT_VIEW"


ROLE_PERMISSIONS_MAP: dict[Role, Set[Permission]] = {
    Role.PLATFORM_ADMIN: {
        Permission.PLATFORM_CONFIGURE,
        Permission.USER_MANAGE,
        Permission.SECRETS_MANAGE,
        Permission.NETWORK_VIEW,
        Permission.NETWORK_OPERATE,
        Permission.VOICE_VIEW,
        Permission.VOICE_OPERATE,
        Permission.INCIDENT_VIEW,
        Permission.INCIDENT_ACKNOWLEDGE,
        Permission.INCIDENT_RESOLVE,
        Permission.ENDPOINT_VIEW,
        Permission.ENDPOINT_MANAGE,
        Permission.AUDIT_VIEW,
    },
    Role.NETWORK_ENGINEER: {
        Permission.NETWORK_VIEW,
        Permission.NETWORK_OPERATE,
        Permission.INCIDENT_VIEW,
        Permission.INCIDENT_ACKNOWLEDGE,
        Permission.ENDPOINT_VIEW,
        Permission.VOICE_VIEW,
    },
    Role.VOICE_ENGINEER: {
        Permission.VOICE_VIEW,
        Permission.VOICE_OPERATE,
        Permission.INCIDENT_VIEW,
        Permission.INCIDENT_ACKNOWLEDGE,
        Permission.ENDPOINT_VIEW,
        Permission.NETWORK_VIEW,
    },
    Role.SERVICE_OPERATIONS: {
        Permission.NETWORK_VIEW,
        Permission.VOICE_VIEW,
        Permission.ENDPOINT_VIEW,
        Permission.INCIDENT_VIEW,
        Permission.INCIDENT_ACKNOWLEDGE,
    },
    Role.SECURITY_AUDITOR: {
        Permission.AUDIT_VIEW,
        Permission.INCIDENT_VIEW,
        Permission.NETWORK_VIEW,
        Permission.VOICE_VIEW,
        Permission.ENDPOINT_VIEW,
    },
    Role.ENDPOINT_ADMIN: {
        Permission.ENDPOINT_VIEW,
        Permission.ENDPOINT_MANAGE,
        Permission.INCIDENT_VIEW,
        Permission.INCIDENT_ACKNOWLEDGE,
    },
}

# Grafana Folder Scoping
ROLE_GRAFANA_FOLDERS: dict[Role, Set[str]] = {
    Role.PLATFORM_ADMIN: {"*"},
    Role.NETWORK_ENGINEER: {"Network", "Core", "Topology", "Incidents", "Endpoints"},
    Role.VOICE_ENGINEER: {"Voice", "Telephony", "Incidents", "Endpoints"},
    Role.SERVICE_OPERATIONS: {"Operations", "Fleet", "Overview", "Incidents", "Dashboards"},
    Role.SECURITY_AUDITOR: {"Audit", "Security", "Overview", "Incidents"},
    Role.ENDPOINT_ADMIN: {"Endpoints", "Fleet", "Incidents"},
}


class PermissionDeniedError(Exception):
    """Raised when an operation is attempted without the required permission."""
    pass


@dataclass
class UserContext:
    username: str
    roles: list[Role] = field(default_factory=list)
    client_ip: str = "127.0.0.1"
    session_id: str = ""
    is_active: bool = True

    def get_all_permissions(self) -> Set[Permission]:
        perms: Set[Permission] = set()
        for r in self.roles:
            perms.update(ROLE_PERMISSIONS_MAP.get(r, set()))
        return perms


class RBACManager:
    @staticmethod
    def has_permission(user: UserContext, permission: Permission) -> bool:
        if not user.is_active:
            return False
        return permission in user.get_all_permissions()

    @staticmethod
    def require_permission(user: UserContext, permission: Permission) -> None:
        if not RBACManager.has_permission(user, permission):
            raise PermissionDeniedError(
                f"User '{user.username}' with roles {[r.value for r in user.roles]} "
                f"lacks required permission: '{permission.value}'"
            )

    @staticmethod
    def can_access_grafana_folder(user: UserContext, folder_name: str) -> bool:
        if not user.is_active:
            return False
        for role in user.roles:
            allowed_folders = ROLE_GRAFANA_FOLDERS.get(role, set())
            if "*" in allowed_folders or folder_name in allowed_folders:
                return True
        return False
