"""
Unit tests for Nawari Phase 8 Enterprise Integrations (Workstream 8E).
"""

import time
import pytest

from services.incidents.models import (
    Incident,
    IncidentStage,
    Severity,
    Confidence,
    RootCauseDomain,
)
from services.integrations.base_adapter import (
    BaseEnterpriseAdapter,
    CircuitState,
)
from services.integrations.itsm_adapter import ITSMAdapter
from services.integrations.email_adapter import EmailAdapter
from services.integrations.sms_adapter import SMSAdapter
from services.integrations.cmdb_adapter import CMDBAdapter


def test_01_circuit_breaker_and_failure_isolation():
    adapter = BaseEnterpriseAdapter(
        name="test-unstable-service",
        failure_threshold=3,
        recovery_timeout_seconds=0.5,
        max_retries=1,
    )
    assert adapter.circuit_state == CircuitState.CLOSED

    # Simulate failing external service
    def _always_fail():
        raise ConnectionResetError("Connection refused by upstream firewall")

    # Failures 1, 2, 3
    for _ in range(3):
        res = adapter.execute_with_resilience("test_op", _always_fail)
        assert res.success is False

    # Circuit breaker must now be OPEN
    assert adapter.circuit_state == CircuitState.OPEN

    # Subsequent call must fast-fail without calling the underlying func
    fast_fail_res = adapter.execute_with_resilience("test_op", _always_fail)
    assert fast_fail_res.success is False
    assert "Circuit breaker for adapter 'test-unstable-service' is OPEN" in fast_fail_res.error

    # Wait for cooldown to HALF_OPEN
    time.sleep(0.6)
    assert adapter.circuit_state == CircuitState.HALF_OPEN

    # Successful call recovers circuit back to CLOSED
    def _now_works():
        return {"status": "ok"}

    rec_res = adapter.execute_with_resilience("test_op", _now_works)
    assert rec_res.success is True
    assert adapter.circuit_state == CircuitState.CLOSED


def test_02_idempotency_cache():
    adapter = BaseEnterpriseAdapter(name="test-idempotent", max_retries=1)
    call_count = 0

    def _operation():
        nonlocal call_count
        call_count += 1
        return {"id": "obj-123", "call": call_count}

    res1 = adapter.execute_with_resilience("op", _operation, idempotency_key="key-abc")
    assert res1.success is True
    assert res1.data["call"] == 1
    assert res1.idempotent_replay is False

    # Duplicate call with identical key
    res2 = adapter.execute_with_resilience("op", _operation, idempotency_key="key-abc")
    assert res2.success is True
    assert res2.data["call"] == 1
    assert res2.idempotent_replay is True
    assert call_count == 1  # Underlying function was not called again!


def test_03_itsm_ticket_lifecycle():
    itsm = ITSMAdapter()
    inc = Incident(
        incident_id="INC-20261108-9001",
        fingerprint="sha256-dummy",
        title="Avaya SBCE Core Signaling Failure",
        root_cause_domain=RootCauseDomain.VOICE_SIP,
        fault_entity_id="sbce01.kq.internal",
        site_id="JKIA-T1A",
        severity=Severity.CRITICAL,
        confidence=Confidence.CONFIRMED,
        status=IncidentStage.CREATED,
    )

    # 1. Create Ticket
    create_res = itsm.create_ticket(inc)
    assert create_res.success is True
    assert inc.external_ticket_id is not None
    assert create_res.data["priority"] == "P1-Critical"

    ticket = itsm.get_ticket(inc.external_ticket_id)
    assert ticket is not None
    assert ticket["state"] == "New"

    # 2. Update Ticket
    update_res = itsm.update_ticket(inc, "Engineering is investigating SBCE SIP trunk link.")
    assert update_res.success is True
    assert ticket["state"] == "In Progress"
    assert "Engineering is investigating" in ticket["work_notes"][0]

    # 3. Resolve Ticket
    inc.mttr_seconds = 420.0
    resolve_res = itsm.resolve_ticket(inc, "SIP gateway restarted and nominal calls verified.")
    assert resolve_res.success is True
    assert ticket["state"] == "Resolved"
    assert ticket["mttr_seconds"] == 420.0


def test_04_email_sanitization_and_alerting():
    email = EmailAdapter()
    inc = Incident(
        incident_id="INC-20261108-9002",
        fingerprint="sha256-dummy2",
        title="High Loss on Switch Core",
        root_cause_domain=RootCauseDomain.NETWORK_CORE,
        fault_entity_id="sw-core01",
        site_id="NBO-HQ",
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
    )

    res = email.send_incident_alert(inc, recipients=["noc@kenya-airways.com"])
    assert res.success is True
    assert len(email.sent_emails) == 1
    assert "[HIGH]" in email.sent_emails[0]["subject"]

    # Verify secret masking
    dirty_text = "Failed with password='MySecretPassword123' and token=9a8b7c6d"
    clean_text = email.sanitize_content(dirty_text)
    assert "MySecretPassword123" not in clean_text
    assert "9a8b7c6d" not in clean_text
    assert "password=********" in clean_text
    assert "token=********" in clean_text


def test_05_sms_paging_and_rate_limiting():
    sms = SMSAdapter(rate_limit_seconds=1.0)
    inc_crit = Incident(
        incident_id="INC-20261108-9003",
        fingerprint="sha256-dummy3",
        title="Core Gateway Down",
        root_cause_domain=RootCauseDomain.NETWORK_CORE,
        fault_entity_id="gw-core",
        site_id="NBO-HQ",
        severity=Severity.CRITICAL,
        confidence=Confidence.CONFIRMED,
    )
    inc_med = Incident(
        incident_id="INC-20261108-9004",
        fingerprint="sha256-dummy4",
        title="Access Port Flapping",
        root_cause_domain=RootCauseDomain.NETWORK_ACCESS,
        fault_entity_id="sw-acc01",
        site_id="EMBAKASI",
        severity=Severity.MEDIUM,
        confidence=Confidence.PROBABLE,
    )

    # Non-CRITICAL incident must be suppressed
    med_res = sms.send_incident_page(inc_med, "+254711000001")
    assert med_res.success is False
    assert "SMS paging suppressed" in med_res.error

    # CRITICAL incident must be sent
    crit_res = sms.send_incident_page(inc_crit, "+254711000001")
    assert crit_res.success is True
    assert len(sms.sent_messages) == 1

    # Immediate second message to same number must be throttled
    flood_res = sms.send_incident_page(inc_crit, "+254711000001")
    assert flood_res.success is False
    assert "throttled by rate limit" in flood_res.error


def test_06_cmdb_lookup():
    cmdb = CMDBAdapter()
    res = cmdb.get_asset_metadata("10.2.1.58")
    assert res.success is True
    assert res.data["site_id"] == "NBO-HQ"
    assert res.data["criticality"] == "TIER_1_MISSION_CRITICAL"

    sbce_res = cmdb.get_asset_metadata("sbce01")
    assert sbce_res.success is True
    assert sbce_res.data["site_id"] == "JKIA-T1A"
    assert sbce_res.data["vendor"] == "Avaya"
