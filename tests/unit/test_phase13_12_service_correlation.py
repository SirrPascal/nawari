"""tests/unit/test_phase13_12_service_correlation.py
=================================================
Comprehensive unit test suite for Phase 13.12:
Service Dependency Mapping & Event Correlation.
"""

import time
import pytest
from services.assurance.causality_engine import (
    CausalClassification,
    CausalityEngine,
    ServiceImpactLevel,
)
from services.multisite.service_catalog import (
    BusinessService,
    DependencyLogic,
    ServiceCatalog,
    ServiceComponentDependency,
    ServiceTier,
    TelemetryQuality,
)


def test_service_catalog_seeding_and_integrity():
    """Verify all 8 Kenya Airways telecommunications services are seeded in catalog."""
    catalog = ServiceCatalog(auto_seed=True)
    expected_services = [
        "SVC-ENTERPRISE-NETWORK",
        "SVC-WAN-CONNECTIVITY",
        "SVC-SIP-CARRIER",
        "SVC-CORP-TELEPHONY",
        "SVC-CONTACT-CENTER-INBOUND",
        "SVC-CONTACT-CENTER-OUTBOUND",
        "SVC-IVR-SELFSERVICE",
        "SVC-COMPLIANCE-RECORDING",
    ]
    for s_id in expected_services:
        svc = catalog.get_service(s_id)
        assert svc is not None
        assert len(svc.dependencies) > 0


def test_service_dag_acyclic():
    """Verify DAG cycle detection algorithm confirms 0 cycles."""
    catalog = ServiceCatalog(auto_seed=True)
    cycles = catalog.detect_dependency_cycles()
    assert len(cycles) == 0, f"Cycles detected: {cycles}"


def test_ha_pair_single_failure_degraded():
    """Verify single SBCE failure results in REDUNDANCY_FAILOVER and DEGRADED impact."""
    engine = CausalityEngine()
    problems = [
        {
            "eventid": "301",
            "host": "avaya-sbce-01",
            "name": "SBCE: Interface Eth0 Down",
            "severity": 4,
            "clock": time.time(),
        }
    ]
    incidents = engine.correlate_active_problems(problems)
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.service_id == "SVC-SIP-CARRIER"
    assert inc.service_impact == ServiceImpactLevel.DEGRADED
    assert inc.causal_classification == CausalClassification.REDUNDANCY_FAILOVER
    assert inc.is_total_outage is False
    assert inc.recommended_action_id == 12  # Telephony action, not Action 10


def test_ha_pair_dual_failure_total_outage():
    """Verify dual SBCE failure results in ROOT_CAUSE and TOTAL_OUTAGE (Action 10)."""
    engine = CausalityEngine()
    problems = [
        {
            "eventid": "302",
            "host": "avaya-sbce-01",
            "name": "SBCE: Power Supply Failure",
            "severity": 5,
            "clock": time.time(),
        },
        {
            "eventid": "303",
            "host": "avaya-sbce-02",
            "name": "SBCE: Panic Halt",
            "severity": 5,
            "clock": time.time(),
        },
    ]
    incidents = engine.correlate_active_problems(problems)
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.service_id == "SVC-SIP-CARRIER"
    assert inc.service_impact == ServiceImpactLevel.TOTAL_OUTAGE
    assert inc.causal_classification == CausalClassification.ROOT_CAUSE
    assert inc.is_total_outage is True
    assert inc.recommended_action_id == 10  # Action 10 total outage


def test_core_switch_root_cause_isolation():
    """Verify core switch failure pins root cause and suppresses child alarms."""
    engine = CausalityEngine()
    problems = [
        {
            "eventid": "401",
            "host": "jkia-core-sw01",
            "name": "Core: Uplink Port-Channel Down",
            "severity": 5,
            "clock": time.time(),
        },
        {
            "eventid": "402",
            "host": "avaya-cm-01",
            "name": "CM: Ping Loss",
            "severity": 4,
            "clock": time.time(),
        },
        {
            "eventid": "403",
            "host": "avaya-g450-01",
            "name": "G450: Unreachable",
            "severity": 4,
            "clock": time.time(),
        },
    ]
    incidents = engine.correlate_active_problems(problems)
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.primary_root_cause["host"] == "jkia-core-sw01"
    assert inc.causal_classification == CausalClassification.ROOT_CAUSE
    assert len(inc.suppressed_symptoms) == 2


def test_flapping_dampening_algorithm():
    """Verify rapid repeated state transitions are flagged as FLAPPING_DAMPENED."""
    engine = CausalityEngine(flapping_window_seconds=60.0, flapping_threshold_count=3)
    t = time.time()
    assert engine.record_event_transition("sw01", "if01", timestamp=t) is False
    assert engine.record_event_transition("sw01", "if01", timestamp=t + 10) is False
    assert engine.record_event_transition("sw01", "if01", timestamp=t + 20) is True


def test_independent_event_handling():
    """Verify standalone unmapped host event is treated as INDEPENDENT_EVENT."""
    engine = CausalityEngine()
    problems = [
        {
            "eventid": "501",
            "host": "generic-host-99",
            "name": "Host high load",
            "severity": 2,
            "clock": time.time(),
        }
    ]
    incidents = engine.correlate_active_problems(problems)
    assert len(incidents) == 1
    assert incidents[0].causal_classification == CausalClassification.INDEPENDENT_EVENT
    assert incidents[0].service_id == "SVC-UNMAPPED"


def test_service_health_upstream_propagation():
    """Verify downstream child service degrades when parent service degrades."""
    catalog = ServiceCatalog(auto_seed=True)
    # Simulate parent service SVC-CORP-TELEPHONY degraded (health 0.50)
    upstream_health = {"SVC-CORP-TELEPHONY": 0.50}
    comp_states = {
        "avaya-cms-01": {"state": "UP", "quality": TelemetryQuality.FRESH.value}
    }
    result = catalog.evaluate_service_health("SVC-COMPLIANCE-RECORDING", comp_states, upstream_service_health=upstream_health)
    assert result.status == "DEGRADED"
    assert result.health_index <= 0.50


def test_missing_telemetry_safe_downgrade():
    """Verify missing telemetry marks component as missing and downgrades status."""
    catalog = ServiceCatalog(auto_seed=True)
    comp_states = {} # Empty telemetry
    result = catalog.evaluate_service_health("SVC-COMPLIANCE-RECORDING", comp_states)
    assert result.status in ("DEGRADED", "CRITICAL_DOWN")


def test_zabbix_service_tree_schema():
    """Verify Zabbix Service Tree sync constructs valid service structures."""
    class MockZabbixClient:
        def __init__(self):
            self.calls = []
        def call(self, method, params):
            self.calls.append((method, params))
            if method == "service.get":
                return []
            if method == "service.create":
                return {"serviceids": ["mock-id-1"]}
            return {}

    mock_client = MockZabbixClient()
    engine = CausalityEngine()
    report = engine.sync_to_zabbix_service_tree(mock_client)
    assert report["root_service_id"] == "mock-id-1"
    assert report["created_count"] == 9  # 1 root + 8 services
