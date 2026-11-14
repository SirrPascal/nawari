"""
Unit tests for Nawari Phase 8 Incident Management & Lifecycle (Workstream 8D).
"""

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
from services.incidents.lifecycle import (
    IncidentLifecycleController,
    InvalidStateTransitionError,
)


def test_01_incident_deduplication_and_grouping():
    dedup = IncidentDeduplicator()

    # First symptom from switch-core01
    inc1, is_new1 = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.NETWORK_CORE,
        fault_entity_id="sw-core01.kq.internal",
        site_id="NBO-HQ",
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
        title="Core Switch Packet Drop",
        evidence=IncidentEvidence("DROP_RATE", "High interface drop rate", metric_value=12.5),
    )
    assert is_new1 is True
    assert inc1.symptoms_count == 1
    assert inc1.severity == Severity.HIGH

    # Second symptom on the same core switch from an endpoint probe
    inc2, is_new2 = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.NETWORK_CORE,
        fault_entity_id="sw-core01.kq.internal",
        site_id="NBO-HQ",
        severity=Severity.CRITICAL,  # Higher severity!
        confidence=Confidence.CONFIRMED,
        title="Path loss detected traversing core switch",
        evidence=IncidentEvidence("PATH_LOSS", "Endpoint loss onset at core hop", metric_value=25.0),
    )
    assert is_new2 is False
    assert inc2.incident_id == inc1.incident_id
    assert inc2.symptoms_count == 2
    assert inc2.severity == Severity.CRITICAL  # Escalate severity to CRITICAL
    assert len(inc2.evidence) == 2


def test_02_lifecycle_state_transitions():
    dedup = IncidentDeduplicator()
    inc, _ = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.VOICE_SIP,
        fault_entity_id="sbce01.kq.internal",
        site_id="JKIA-T1A",
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
        title="SIP 503 Service Unavailable",
    )
    assert inc.status == IncidentStage.CREATED

    # Legal transitions: CREATED -> CLASSIFIED -> ACKNOWLEDGED -> INVESTIGATING -> RECOVERING
    IncidentLifecycleController.transition_to(inc, IncidentStage.CLASSIFIED)
    assert inc.status == IncidentStage.CLASSIFIED

    IncidentLifecycleController.transition_to(inc, IncidentStage.ACKNOWLEDGED, actor="voice_eng_peter")
    assert inc.status == IncidentStage.ACKNOWLEDGED
    assert inc.acknowledged_by == "voice_eng_peter"
    assert inc.acknowledged_at is not None

    IncidentLifecycleController.transition_to(inc, IncidentStage.INVESTIGATING)
    assert inc.status == IncidentStage.INVESTIGATING

    IncidentLifecycleController.transition_to(inc, IncidentStage.RECOVERING)
    assert inc.status == IncidentStage.RECOVERING

    # Attempting to resolve prematurely (nominal cycles < 3) must raise InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        IncidentLifecycleController.transition_to(inc, IncidentStage.RESOLVED)


def test_03_flapping_protection_and_nominal_recovery():
    dedup = IncidentDeduplicator()
    inc, _ = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.NETWORK_ACCESS,
        fault_entity_id="sw-acc03.kq.internal",
        site_id="EMBAKASI",
        severity=Severity.MEDIUM,
        confidence=Confidence.PROBABLE,
        title="Flapping Access Port",
    )
    IncidentLifecycleController.transition_to(inc, IncidentStage.ACKNOWLEDGED, actor="net_admin")
    IncidentLifecycleController.transition_to(inc, IncidentStage.INVESTIGATING)
    IncidentLifecycleController.transition_to(inc, IncidentStage.RECOVERING)

    # Cycle 1
    assert IncidentLifecycleController.record_nominal_cycle(inc) == 1
    assert inc.status == IncidentStage.RECOVERING

    # Flap occurs!
    IncidentLifecycleController.record_degradation(inc, reason="Port bounced again")
    assert inc.nominal_cycles == 0
    assert inc.status == IncidentStage.INVESTIGATING

    # Return to recovery
    IncidentLifecycleController.transition_to(inc, IncidentStage.RECOVERING)
    IncidentLifecycleController.record_nominal_cycle(inc)  # 1
    IncidentLifecycleController.record_nominal_cycle(inc)  # 2
    IncidentLifecycleController.record_nominal_cycle(inc)  # 3 -> Triggers auto-resolution!

    assert inc.status == IncidentStage.RESOLVED
    assert inc.resolved_at is not None

    # Close incident and verify MTTR calculation
    IncidentLifecycleController.transition_to(inc, IncidentStage.CLOSED)
    assert inc.status == IncidentStage.CLOSED
    assert inc.mttr_seconds is not None
    assert inc.mttr_seconds >= 0.0


def test_04_escalation_evaluation():
    dedup = IncidentDeduplicator()
    inc, _ = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.VOICE_MEDIA,
        fault_entity_id="trunk-pri-01",
        site_id="NBO-HQ",
        severity=Severity.CRITICAL,
        confidence=Confidence.CONFIRMED,
        title="Complete PSTN Trunk Outage",
    )
    # Initially within SLA window
    needs_esc, _ = IncidentLifecycleController.evaluate_escalation(inc)
    assert needs_esc is False

    # Simulate 16 minutes unacknowledged
    inc.created_at = time.time() - (16 * 60)
    needs_esc, reason = IncidentLifecycleController.evaluate_escalation(inc)
    assert needs_esc is True
    assert "CRITICAL incident unacknowledged" in reason

    # Once acknowledged, escalation ceases
    IncidentLifecycleController.transition_to(inc, IncidentStage.ACKNOWLEDGED, actor="noc_lead")
    needs_esc, _ = IncidentLifecycleController.evaluate_escalation(inc)
    assert needs_esc is False


def test_05_stale_or_silent_telemetry_cannot_cause_recovery():
    """Verify that source silence, NO_DATA, STALE, or outdated telemetry cannot resolve an incident."""
    dedup = IncidentDeduplicator()
    inc, _ = dedup.process_symptom(
        root_cause_domain=RootCauseDomain.ENDPOINT_WIFI,
        fault_entity_id="laptop-wifi-01",
        site_id="NBO-HQ",
        severity=Severity.HIGH,
        confidence=Confidence.CONFIRMED,
        title="High Wi-Fi Packet Loss",
    )
    IncidentLifecycleController.transition_to(inc, IncidentStage.ACKNOWLEDGED, actor="ops")
    IncidentLifecycleController.transition_to(inc, IncidentStage.INVESTIGATING)
    IncidentLifecycleController.transition_to(inc, IncidentStage.RECOVERING)

    # 1. Active nominal telemetry cycle 1
    c1 = IncidentLifecycleController.record_nominal_cycle(
        inc,
        telemetry_timestamp=time.time(),
        telemetry_status="NOMINAL",
    )
    assert c1 == 1
    assert inc.nominal_cycles == 1

    # 2. Source drops off or stops reporting (NO_DATA) -> Must NOT count as recovery!
    c2 = IncidentLifecycleController.record_nominal_cycle(
        inc,
        telemetry_timestamp=time.time(),
        telemetry_status="NO_DATA",
    )
    assert c2 == 0
    assert inc.nominal_cycles == 0  # Resets to 0!
    assert inc.status == IncidentStage.RECOVERING  # Does NOT resolve

    # 3. Delayed/stale telemetry (5 minutes old) -> Must NOT count as recovery!
    IncidentLifecycleController.record_nominal_cycle(
        inc,
        telemetry_timestamp=time.time(),
        telemetry_status="NOMINAL",
    )
    assert inc.nominal_cycles == 1

    c_stale = IncidentLifecycleController.record_nominal_cycle(
        inc,
        telemetry_timestamp=time.time() - 300,  # 300 seconds old
        telemetry_status="NOMINAL",
        max_staleness_seconds=120.0,
    )
    assert c_stale == 0
    assert inc.nominal_cycles == 0  # Stale telemetry rejected and resets cycle!


