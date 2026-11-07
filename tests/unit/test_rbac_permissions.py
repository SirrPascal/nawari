"""
Unit tests for Nawari Phase 8 Enterprise Security, RBAC, Enrollment & Audit.
"""

import os
import tempfile
import pytest

from services.security.rbac import (
    Role,
    Permission,
    UserContext,
    RBACManager,
    PermissionDeniedError,
)
from services.security.enrollment import (
    EnrollmentManager,
    EnrollmentError,
    RevocationError,
)
from services.security.audit import AuditLogger


def test_01_rbac_platform_admin_full_access():
    admin = UserContext(username="superadmin", roles=[Role.PLATFORM_ADMIN])
    assert RBACManager.has_permission(admin, Permission.PLATFORM_CONFIGURE)
    assert RBACManager.has_permission(admin, Permission.USER_MANAGE)
    assert RBACManager.has_permission(admin, Permission.VOICE_OPERATE)
    assert RBACManager.has_permission(admin, Permission.AUDIT_VIEW)
    assert RBACManager.can_access_grafana_folder(admin, "AnyFolder")


def test_02_rbac_network_engineer_permissions():
    net_eng = UserContext(username="netops_jane", roles=[Role.NETWORK_ENGINEER])
    assert RBACManager.has_permission(net_eng, Permission.NETWORK_VIEW)
    assert RBACManager.has_permission(net_eng, Permission.NETWORK_OPERATE)
    assert RBACManager.has_permission(net_eng, Permission.INCIDENT_ACKNOWLEDGE)
    # Cannot operate voice or manage platform users
    assert not RBACManager.has_permission(net_eng, Permission.VOICE_OPERATE)
    assert not RBACManager.has_permission(net_eng, Permission.USER_MANAGE)

    with pytest.raises(PermissionDeniedError):
        RBACManager.require_permission(net_eng, Permission.USER_MANAGE)


def test_03_rbac_security_auditor_read_only():
    auditor = UserContext(username="auditor_bob", roles=[Role.SECURITY_AUDITOR])
    assert RBACManager.has_permission(auditor, Permission.AUDIT_VIEW)
    assert RBACManager.has_permission(auditor, Permission.NETWORK_VIEW)
    assert not RBACManager.has_permission(auditor, Permission.INCIDENT_ACKNOWLEDGE)
    assert not RBACManager.has_permission(auditor, Permission.NETWORK_OPERATE)


def test_04_enrollment_lifecycle():
    mgr = EnrollmentManager()
    token = mgr.generate_provisioning_token(issuer="MDM_GPO", expires_in_hours=1, one_time=True)

    # Register endpoint from private Kenya Airways IP
    reg = mgr.register_endpoint(
        enrollment_token=token,
        hostname="kq-exec-laptop-01",
        mac_address="00:1A:2B:3C:4D:5E",
        client_ip="10.2.156.45",
    )
    assert "endpoint_id" in reg
    assert reg["provenance"] == "PHYSICAL_PRODUCTION"
    assert "secret_token" in reg

    # Validate secret token
    ep_id = reg["endpoint_id"]
    secret_token = reg["secret_token"]
    assert mgr.validate_endpoint_token(ep_id, secret_token) is True
    assert mgr.validate_endpoint_token(ep_id, "wrong_secret") is False

    # Second registration with one-time token must fail
    with pytest.raises(EnrollmentError):
        mgr.register_endpoint(
            enrollment_token=token,
            hostname="kq-exec-laptop-02",
            mac_address="00:1A:2B:3C:4D:5F",
            client_ip="10.2.156.46",
        )


def test_05_endpoint_revocation():
    mgr = EnrollmentManager()
    token = mgr.generate_provisioning_token(issuer="MDM_GPO", one_time=False)
    reg = mgr.register_endpoint(
        enrollment_token=token,
        hostname="kq-decom-01",
        mac_address="00:11:22:33:44:55",
        client_ip="192.168.1.100",
    )
    ep_id = reg["endpoint_id"]
    secret = reg["secret_token"]

    assert mgr.validate_endpoint_token(ep_id, secret) is True

    # Revoke endpoint
    mgr.revoke_endpoint(ep_id, reason="Device decommissioned", actor="secops")
    assert mgr.is_revoked(ep_id) is True
    assert mgr.validate_endpoint_token(ep_id, secret) is False


def test_06_tamper_resistant_audit_log():
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        log_path = f.name

    try:
        logger = AuditLogger(log_path)
        logger.log_event("admin", "PLATFORM_ADMIN", "CONFIG_UPDATE", "SERVICE", "zabbix", "10.2.1.58", "SUCCESS")
        logger.log_event("secops", "SECURITY_AUDITOR", "REVOKE_ENDPOINT", "ENDPOINT", "uuid-1234", "10.2.1.59", "SUCCESS")

        valid, msg = logger.verify_integrity()
        assert valid is True

        # Read back from file
        file_valid, file_msg = AuditLogger.verify_file(log_path)
        assert file_valid is True

        # Tamper with file
        with open(log_path, "r") as f:
            lines = f.readlines()
        tampered = lines[0].replace("CONFIG_UPDATE", "UNAUTHORIZED_ALTERATION")
        with open(log_path, "w") as f:
            f.write(tampered + lines[1])

        tampered_valid, tampered_msg = AuditLogger.verify_file(log_path)
        assert tampered_valid is False
        assert "Signature mismatch" in tampered_msg or "Hash chain broken" in tampered_msg

    finally:
        if os.path.exists(log_path):
            os.remove(log_path)
