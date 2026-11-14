"""Unit tests for Workstream 10E: Kenya Airways Dial Plan & Carrier Routing Assurance."""

from __future__ import annotations

import pytest

from services.voice.dialplan import (
    ExtensionCategory,
    KQNumberClassifier,
    RoutingAssuranceEngine,
)


def test_kq_number_classification():
    # 1. Pride Centre HQ Extension
    info_hq = KQNumberClassifier.classify("1001")
    assert info_hq.category == ExtensionCategory.PRIDE_CENTRE_HQ
    assert info_hq.is_allowlisted_test is True
    assert info_hq.is_emergency is False

    info_hq_non_test = KQNumberClassifier.classify("1250")
    assert info_hq_non_test.category == ExtensionCategory.PRIDE_CENTRE_HQ
    assert info_hq_non_test.is_allowlisted_test is False

    # 2. JKIA Terminal 1A
    info_t1a = KQNumberClassifier.classify("2050")
    assert info_t1a.category == ExtensionCategory.JKIA_TERMINAL_1A

    # 3. Regional Outstations
    info_mba = KQNumberClassifier.classify("4020")
    assert info_mba.category == ExtensionCategory.REGIONAL_OUTSTATIONS

    # 4. National mobile (Safaricom)
    info_saf = KQNumberClassifier.classify("0712345678")
    assert info_saf.category == ExtensionCategory.EXTERNAL_NATIONAL
    assert info_saf.normalized_number == "+254712345678"
    assert "Safaricom" in info_saf.operator

    # 5. National mobile (Airtel)
    info_airtel = KQNumberClassifier.classify("0733123456")
    assert info_airtel.category == ExtensionCategory.EXTERNAL_NATIONAL
    assert "Airtel" in info_airtel.operator


def test_emergency_numbers_strictly_identified():
    for emer in ("999", "112", "911"):
        info = KQNumberClassifier.classify(emer)
        assert info.category == ExtensionCategory.EMERGENCY
        assert info.is_emergency is True
        assert info.is_allowlisted_test is False


def test_carrier_route_selection_validation():
    trunk_status = {
        "SAFARICOM_SIP": "UP",
        "AIRTEL_SIP": "UP",
        "TELKOM_ISDN": "UP",
    }

    # 1. Optimal route selection
    res_opt = RoutingAssuranceEngine.validate_route_selection(
        destination="+254712345678",
        selected_trunk="SAFARICOM_SIP",
        trunk_status_map=trunk_status,
    )
    assert res_opt["routing_verdict"] == "OPTIMAL_ROUTE"
    assert res_opt["severity"] == "HEALTHY"

    # 2. Suboptimal route selection (Secondary selected while primary is UP)
    res_subopt = RoutingAssuranceEngine.validate_route_selection(
        destination="+254712345678",
        selected_trunk="AIRTEL_SIP",
        trunk_status_map=trunk_status,
    )
    assert res_subopt["routing_verdict"] == "SUBOPTIMAL_CARRIER_ROUTE"
    assert res_subopt["severity"] == "WARNING"

    # 3. Legitimate failover (Primary is DOWN, Secondary selected)
    trunk_status_failover = {
        "SAFARICOM_SIP": "DOWN",
        "AIRTEL_SIP": "UP",
        "TELKOM_ISDN": "UP",
    }
    res_failover = RoutingAssuranceEngine.validate_route_selection(
        destination="+254712345678",
        selected_trunk="AIRTEL_SIP",
        trunk_status_map=trunk_status_failover,
    )
    assert res_failover["routing_verdict"] == "FAILOVER_CARRIER_ROUTE_ACTIVE"
    assert res_failover["severity"] == "INFO"


def test_safety_gate_enforcement():
    # Allowlisted test extension passes cleanly
    RoutingAssuranceEngine.enforce_safety_gate("1001")
    RoutingAssuranceEngine.enforce_safety_gate("4286")

    # Emergency number strictly blocked
    with pytest.raises(ValueError, match="SAFETY VIOLATION: Dialing emergency services"):
        RoutingAssuranceEngine.enforce_safety_gate("999")

    with pytest.raises(ValueError, match="SAFETY VIOLATION: Dialing emergency services"):
        RoutingAssuranceEngine.enforce_safety_gate("112")

    # Unallowlisted external number blocked for synthetic testing
    with pytest.raises(ValueError, match="SAFETY VIOLATION: Destination"):
        RoutingAssuranceEngine.enforce_safety_gate("+254712345678")

