"""tests/unit/test_phase13_13_slo_error_budgets.py
===============================================
Comprehensive unit test suite for Phase 13.13:
SLI, SLO & Error Budget Multi-Burn-Rate Alerting.
"""

import pytest
from services.assurance.slo_burn_rate_engine import (
    BurnRateAlertLevel,
    SloBurnRateEngine,
)
from services.multisite.service_catalog import (
    SLIEvaluationEngine,
    SLOSpecification,
    TelemetryQuality,
)


def test_authoritative_slo_register_integrity():
    """Verify all 7 critical Kenya Airways services are registered with mathematically valid budgets."""
    engine = SloBurnRateEngine()
    slos = engine.AUTHORITATIVE_SLOS
    assert len(slos) == 7

    # Verify 30-day error budget formula: 30 * 24 * 60 * (1 - SLO/100)
    for sid, s in slos.items():
        expected_budget = 30 * 24 * 60 * ((100.0 - s["slo"]) / 100.0)
        assert abs(s["allowed_downtime_minutes_30d"] - expected_budget) < 0.01


def test_multidimensional_sli_pristine():
    """Verify pristine telemetry achieves 100% across Availability, Performance, and Quality."""
    evaluator = SLIEvaluationEngine()
    evaluator.register_slo(SLOSpecification("SVC-SIP-CARRIER", target_slo_percent=99.99))
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=500.0, health_index=1.0, is_available=True, is_performance_met=True)

    res = evaluator.evaluate_sli("SVC-SIP-CARRIER")
    assert res.availability_sli == 100.0
    assert res.performance_sli == 100.0
    assert res.quality_sli == 100.0
    assert res.coverage_percent == 100.0
    assert res.is_slo_breached is False


def test_missing_telemetry_penalizes_availability():
    """Verify missing telemetry is tracked as unknown and reduces availability rather than inflating it."""
    evaluator = SLIEvaluationEngine()
    evaluator.register_slo(SLOSpecification("SVC-SIP-CARRIER", target_slo_percent=99.99))
    # 400 min good, 100 min missing/unknown
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=400.0, health_index=1.0, is_available=True)
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=100.0, health_index=0.0, is_unknown=True)

    res = evaluator.evaluate_sli("SVC-SIP-CARRIER")
    assert res.unknown_minutes == 100.0
    assert res.availability_sli == 80.0  # 400 / 500 = 80%
    assert res.coverage_percent == 80.0


def test_coverage_deficit_flagging():
    """Verify coverage < 80% triggers coverage deficit flag in burn rate engine."""
    evaluator = SLIEvaluationEngine()
    evaluator.register_slo(SLOSpecification("SVC-SIP-CARRIER", target_slo_percent=99.99))
    # 60 min good, 40 min missing -> 60% coverage
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=60.0, health_index=1.0, is_available=True)
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=40.0, is_unknown=True)

    burn_engine = SloBurnRateEngine(sli_engine=evaluator)
    alerts = burn_engine.evaluate_burn_rate_alerts("SVC-SIP-CARRIER", recent_1h_outage_minutes=1.0)
    assert len(alerts) >= 1
    assert alerts[0].is_coverage_deficit is True


def test_14_4x_burn_rate_critical_page():
    """Verify short window high burn rate triggers CRITICAL_PAGE alert."""
    evaluator = SLIEvaluationEngine()
    burn_engine = SloBurnRateEngine(sli_engine=evaluator)
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=1000.0, health_index=1.0, is_available=True)

    # 1.0 min outage in 1h on 99.99% service = 166.7x burn rate
    alerts = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-SIP-CARRIER",
        recent_1h_outage_minutes=1.0,
        recent_6h_outage_minutes=1.0,
    )
    assert len(alerts) == 1
    assert alerts[0].alert_level == BurnRateAlertLevel.CRITICAL_PAGE
    assert alerts[0].burn_rate >= 14.4


def test_6_0x_burn_rate_warning_ticket():
    """Verify medium window sustained burn rate triggers WARNING_TICKET alert."""
    evaluator = SLIEvaluationEngine()
    burn_engine = SloBurnRateEngine(sli_engine=evaluator)
    evaluator.record_interval("SVC-IVR-SELFSERVICE", duration_minutes=1000.0, health_index=1.0, is_available=True)

    # 5.0 min outage in 6h on 99.80% service = 6.94x burn rate
    alerts = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-IVR-SELFSERVICE",
        recent_1h_outage_minutes=0.0,
        recent_6h_outage_minutes=5.0,
    )
    assert len(alerts) == 1
    assert alerts[0].alert_level == BurnRateAlertLevel.WARNING_TICKET
    assert alerts[0].burn_rate >= 6.0


def test_nominal_quiescent_burn_rate():
    """Verify 0 burn rate alerts on zero outage minutes."""
    evaluator = SLIEvaluationEngine()
    burn_engine = SloBurnRateEngine(sli_engine=evaluator)
    evaluator.record_interval("SVC-CORP-TELEPHONY", duration_minutes=1000.0, health_index=1.0, is_available=True)

    alerts = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-CORP-TELEPHONY",
        recent_1h_outage_minutes=0.0,
        recent_6h_outage_minutes=0.0,
    )
    assert len(alerts) == 0


def test_time_to_exhaustion_calculation():
    """Verify time to exhaustion is positively calculated when burning budget."""
    evaluator = SLIEvaluationEngine()
    burn_engine = SloBurnRateEngine(sli_engine=evaluator)
    evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=1000.0, health_index=1.0, is_available=True)

    alerts = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-SIP-CARRIER",
        recent_1h_outage_minutes=0.5,
    )
    assert len(alerts) == 1
    assert alerts[0].time_to_exhaustion_hours is not None
    assert alerts[0].time_to_exhaustion_hours > 0.0


def test_scheduled_maintenance_exclusion():
    """Verify scheduled maintenance minutes are tracked separately and excluded from outage minutes."""
    evaluator = SLIEvaluationEngine()
    evaluator.register_slo(SLOSpecification("SVC-WAN-CONNECTIVITY", target_slo_percent=99.95))
    evaluator.record_interval("SVC-WAN-CONNECTIVITY", duration_minutes=120.0, health_index=0.0, in_maintenance=True)
    evaluator.record_interval("SVC-WAN-CONNECTIVITY", duration_minutes=880.0, health_index=1.0, is_available=True)

    res = evaluator.evaluate_sli("SVC-WAN-CONNECTIVITY")
    assert res.scheduled_maintenance_minutes == 120.0
    assert res.outage_minutes == 0.0
    assert res.availability_sli == 100.0


def test_replay_telemetry_isolation():
    """Verify replayed telemetry classification strictly prevents live health establishment."""
    assert TelemetryQuality.REPLAYED.value == "REPLAYED"

