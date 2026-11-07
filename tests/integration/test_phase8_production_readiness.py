"""
Nawari Phase 8 — Consolidated Production Readiness Integration Test (Workstream 8G)
Validates the unified delivery of 8A through 8F as one cohesive operational platform.
"""

import json
import os
import subprocess
import time
import pytest

from services.incidents.models import (
    IncidentStage,
    Severity,
    Confidence,
    RootCauseDomain,
    IncidentEvidence,
)
from services.incidents.fingerprint import IncidentDeduplicator
from services.incidents.lifecycle import IncidentLifecycleController
from services.integrations.itsm_adapter import ITSMAdapter
from services.integrations.email_adapter import EmailAdapter
from services.integrations.cmdb_adapter import CMDBAdapter
from services.security.rbac import Role, Permission, UserContext, RBACManager
from services.security.enrollment import EnrollmentManager
from services.security.audit import AuditLogger


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_01_workstream_8a_production_compose_hardening():
    """Verify production Docker compose overrides, security parameters, and image pins."""
    res = subprocess.run(
        [
            "docker", "compose",
            "--env-file", os.path.join(PROJECT_ROOT, ".env"),
            "-f", os.path.join(PROJECT_ROOT, "docker", "compose.yaml"),
            "-f", os.path.join(PROJECT_ROOT, "docker", "compose.prod.yaml"),
            "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert res.returncode == 0, f"Compose prod config invalid: {res.stderr}"
    config = json.loads(res.stdout)
    services = config.get("services", {})

    # Check image pinning on postgres and zabbix
    pg = services.get("postgres", {})
    assert "postgres:17.2-alpine3.21" in pg.get("image", "")

    # Check security options
    for svc_name in ("postgres", "zabbix-server", "zabbix-web", "grafana"):
        svc = services.get(svc_name, {})
        sec_opts = svc.get("security_opt", [])
        assert "no-new-privileges:true" in sec_opts, f"{svc_name} missing no-new-privileges:true"


def test_02_workstream_8b_backup_and_recovery_loop():
    """Execute backup script, verify SHA256SUMS, and verify database integrity."""
    backup_script = os.path.join(PROJECT_ROOT, "scripts", "backup", "backup_nawari.sh")
    assert os.path.exists(backup_script), "backup_nawari.sh missing"

    # Run backup
    res = subprocess.run([backup_script], capture_output=True, text=True, cwd=PROJECT_ROOT)
    assert res.returncode == 0, f"Backup script failed: {res.stderr}"

    backup_dir = res.stdout.strip().split("\n")[-1]
    assert os.path.isdir(backup_dir), f"Backup directory does not exist: {backup_dir}"

    sha_file = os.path.join(backup_dir, "SHA256SUMS")
    assert os.path.isfile(sha_file), "SHA256SUMS file missing"

    # Verify sha256 checksums
    verify_res = subprocess.run(["sha256sum", "--check", "SHA256SUMS"], capture_output=True, text=True, cwd=backup_dir)
    assert verify_res.returncode == 0, f"Checksum verification failed: {verify_res.stderr}"

    # Clean up test backup
    subprocess.run(["rm", "-rf", os.path.dirname(backup_dir)])


def test_03_workstream_8c_security_rbac_and_audit():
    """Test RBAC enforcement, endpoint enrollment with provenance, and audit log integrity."""
    # RBAC check
    operator = UserContext(username="noc_steve", roles=[Role.SERVICE_OPERATIONS])
    assert RBACManager.has_permission(operator, Permission.INCIDENT_ACKNOWLEDGE)
    assert not RBACManager.has_permission(operator, Permission.PLATFORM_CONFIGURE)

    # Enrollment
    em = EnrollmentManager()
    token = em.generate_provisioning_token(issuer="GPO")
    reg = em.register_endpoint(
        enrollment_token=token,
        hostname="kq-laptop-99",
        mac_address="AA:BB:CC:DD:EE:FF",
        client_ip="10.2.156.12",
    )
    assert reg["provenance"] == "PHYSICAL_PRODUCTION"
    assert em.validate_endpoint_token(reg["endpoint_id"], reg["secret_token"]) is True

    # Audit logging
    logger = AuditLogger()
    logger.log_event("noc_steve", "SERVICE_OPERATIONS", "ACK_INCIDENT", "INCIDENT", "INC-01", "10.2.1.58", "SUCCESS")
    logger.log_event("noc_steve", "SERVICE_OPERATIONS", "RESOLVE_INCIDENT", "INCIDENT", "INC-01", "10.2.1.58", "SUCCESS")
    valid, msg = logger.verify_integrity()
    assert valid is True, msg


def test_04_workstream_8d_and_8e_incident_itsm_flow():
    """Full lifecycle from symptom detection, deduplication, ITSM ticket creation, to MTTR resolution."""
    dedup = IncidentDeduplicator()
    cmdb = CMDBAdapter()
    itsm = ITSMAdapter()
    email = EmailAdapter()

    # 1. Lookup CMDB context for switch
    cmdb_res = cmdb.get_asset_metadata("10.2.156.45")
    assert cmdb_res.success is True

    # 2. Ingest first symptom
    inc, is_new = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.NETWORK_CORE,
        fault_entity_id=cmdb_res.data["hostname"],
        site_id=cmdb_res.data["site_id"],
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
        title=f"Core Switch Interface Flap ({cmdb_res.data['building']})",
        evidence=IncidentEvidence("IF_DOWN", "TenGigabitEthernet1/0/1 down", metric_value=0.0),
    )
    assert is_new is True
    assert inc.status == IncidentStage.CREATED

    # 3. Deduplicate second symptom
    inc, is_new2 = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.NETWORK_CORE,
        fault_entity_id=cmdb_res.data["hostname"],
        site_id=cmdb_res.data["site_id"],
        severity=Severity.CRITICAL,  # Escalation
        confidence=Confidence.CONFIRMED,
        title="Path Loss Traversing Core Switch",
        evidence=IncidentEvidence("PATH_LOSS", "Packet drop at core", metric_value=40.0),
    )
    assert is_new2 is False
    assert inc.severity == Severity.CRITICAL
    assert inc.symptoms_count == 2

    # 4. Create ITSM Ticket
    itsm_res = itsm.create_ticket(inc)
    assert itsm_res.success is True
    assert inc.external_ticket_id is not None
    assert itsm_res.data["priority"] == "P1-Critical"

    # 5. Dispatch sanitized alert email
    email_res = email.send_incident_alert(inc, ["noc@kenya-airways.com"])
    assert email_res.success is True

    # 6. Operator acknowledges
    IncidentLifecycleController.transition_to(inc, IncidentStage.ACKNOWLEDGED, actor="net_lead")
    itsm.update_ticket(inc, "Engineer dispatched to inspect optic transceiver.")

    # 7. Transition to RECOVERING and verify 3 nominal cycles
    IncidentLifecycleController.transition_to(inc, IncidentStage.INVESTIGATING)
    IncidentLifecycleController.transition_to(inc, IncidentStage.RECOVERING)

    IncidentLifecycleController.record_nominal_cycle(inc)
    IncidentLifecycleController.record_nominal_cycle(inc)
    IncidentLifecycleController.record_nominal_cycle(inc)  # Automatically resolves on cycle 3

    assert inc.status == IncidentStage.RESOLVED

    # 8. Close incident and update ITSM ticket
    IncidentLifecycleController.transition_to(inc, IncidentStage.CLOSED)
    assert inc.status == IncidentStage.CLOSED
    assert inc.mttr_seconds is not None

    resolve_res = itsm.resolve_ticket(inc, "Optic transceiver replaced and verified nominal.")
    assert resolve_res.success is True
    ticket = itsm.get_ticket(inc.external_ticket_id)
    assert ticket["state"] == "Resolved"
    assert ticket["mttr_seconds"] == inc.mttr_seconds
