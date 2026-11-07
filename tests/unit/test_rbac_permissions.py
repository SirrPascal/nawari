"""
Unit tests for Nawari Phase 8 Enterprise Security, RBAC, Enrollment & Audit.
"""

import os
import tempfile
import time
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


def test_07_audit_log_deletion_and_reordering_detection():
    """Verify that deleting a record in the middle, reordering lines, or truncating the tail is caught."""
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        log_path = f.name

    try:
        logger = AuditLogger(log_path)
        logger.log_event("actor1", "ROLE1", "ACTION1", "TGT", "1", "10.0.0.1", "SUCCESS")
        logger.log_event("actor2", "ROLE2", "ACTION2", "TGT", "2", "10.0.0.2", "SUCCESS")
        logger.log_event("actor3", "ROLE3", "ACTION3", "TGT", "3", "10.0.0.3", "SUCCESS")

        with open(log_path, "r") as f:
            lines = f.readlines()

        assert len(lines) == 3

        # 1. Test middle deletion (drop line 1)
        with open(log_path, "w") as f:
            f.write(lines[0] + lines[2])
        valid, msg = AuditLogger.verify_file(log_path)
        assert valid is False
        assert "deletion" in msg or "mismatch" in msg or "index" in msg

        # 2. Test reordering (swap line 0 and line 1)
        with open(log_path, "w") as f:
            f.write(lines[1] + lines[0] + lines[2])
        valid_reorder, msg_reorder = AuditLogger.verify_file(log_path)
        assert valid_reorder is False
        assert "reordering" in msg_reorder or "index" in msg_reorder or "mismatch" in msg_reorder

        # 3. Test tail truncation (verify against expected_record_count)
        with open(log_path, "w") as f:
            f.write(lines[0] + lines[1])
        valid_trunc, msg_trunc = AuditLogger.verify_file(log_path, expected_record_count=3)
        assert valid_trunc is False
        assert "Truncation detected" in msg_trunc

    finally:
        if os.path.exists(log_path):
            os.remove(log_path)


def test_08_endpoint_credential_rotation():
    """Verify endpoint token rotation immediately invalidates the previous secret token."""
    mgr = EnrollmentManager()
    token = mgr.generate_provisioning_token(issuer="MDM")
    reg = mgr.register_endpoint(token, "laptop-rot", "AA:BB:CC:11:22:33", "10.2.1.100")
    ep_id = reg["endpoint_id"]
    old_secret = reg["secret_token"]

    assert mgr.validate_endpoint_token(ep_id, old_secret) is True

    # Rotate credentials
    rot = mgr.rotate_endpoint_credentials(ep_id, old_secret)
    new_secret = rot["secret_token"]
    assert new_secret != old_secret

    # Old secret must now be rejected
    assert mgr.validate_endpoint_token(ep_id, old_secret) is False
    # New secret must be accepted
    assert mgr.validate_endpoint_token(ep_id, new_secret) is True


def test_09_gateway_live_replay_guard():
    """Verify that live telemetry with clock skew > 300s is rejected when replay guard is active."""
    import json
    import urllib.request
    import urllib.error
    from unittest.mock import MagicMock
    from services.gateway.config import GatewayConfig
    from services.gateway.server import IngestionGatewayServer
    from services.voice.zabbix_sender import ZabbixSender
    from tests.unit.test_stage7d_gateway import build_sample_report

    config = GatewayConfig(
        host="127.0.0.1",
        port=8456,
        require_auth=False,
        enforce_replay_guard=True,
        max_clock_skew_seconds=60.0,
    )
    server = IngestionGatewayServer(config=config, zabbix_sender=MagicMock(spec=ZabbixSender))
    server.start()

    try:
        report = build_sample_report()
        # Set timestamp 2 hours in the past (replace on frozen dataclasses)
        import dataclasses
        past_meta = dataclasses.replace(report.metadata, timestamp_ns=int((time.time() - 7200) * 1e9))
        report = dataclasses.replace(report, metadata=past_meta)
        payload = json.dumps(report.to_dict()).encode("utf-8")

        req = urllib.request.Request(
            "http://127.0.0.1:8456/api/v1/telemetry",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)

        err = exc_info.value
        assert err.code == 400
        body = json.loads(err.read().decode("utf-8"))
        assert "Replay/Timestamp guard" in body["error"]

    finally:
        server.stop()


