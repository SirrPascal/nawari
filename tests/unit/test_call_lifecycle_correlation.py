"""Unit tests for Workstream 10B: Call Lifecycle, Multi-Leg Correlation, Q.850, and Privacy."""

from __future__ import annotations

import pytest

from services.voice.correlation import (
    CauseCodeTranslator,
    CorrelatedCallSession,
    SessionCorrelator,
    mask_phone_number,
    mask_sip_uri,
)


def test_q850_cause_translation():
    info16 = CauseCodeTranslator.get_q850_info(16)
    assert info16.name == "Normal call clearing"
    assert info16.category == "NORMAL"
    assert info16.is_operational_failure is False

    info34 = CauseCodeTranslator.get_q850_info(34)
    assert info34.name == "No circuit/channel available"
    assert info34.category == "TRUNK_CONGESTION"
    assert info34.is_operational_failure is True

    info1 = CauseCodeTranslator.get_q850_info(1)
    assert info1.category == "DIALPLAN_DEFECT"


def test_reason_header_parsing():
    header = 'Q.850;cause=16;text="Normal call clearing"'
    parsed = CauseCodeTranslator.parse_reason_header(header)
    assert parsed["protocol"] == "Q.850"
    assert parsed["cause_code"] == 16
    assert parsed["name"] == "Normal call clearing"
    assert parsed["is_operational_failure"] is False

    header_503 = 'SIP;cause=503;text="Service Unavailable"'
    parsed_503 = CauseCodeTranslator.parse_reason_header(header_503)
    assert parsed_503["protocol"] == "SIP"
    assert parsed_503["cause_code"] == 503
    assert parsed_503["is_operational_failure"] is True


def test_station_state_vs_infrastructure_failure_classification():
    # 1. 480 with Avaya Warning header -> Station State (phone offline, softphone unreg)
    res_480 = CauseCodeTranslator.classify_call_termination(
        status_code=480,
        warning_header='399 avaya-sm01 "User not registered"',
    )
    assert res_480["category"] == "STATION_STATE"
    assert res_480["is_infrastructure_failure"] is False
    assert "User not registered" in res_480["diagnostic_summary"]

    # 2. 486 Busy -> Station State
    res_486 = CauseCodeTranslator.classify_call_termination(status_code=486)
    assert res_486["category"] == "STATION_STATE"
    assert res_486["is_infrastructure_failure"] is False

    # 3. 503 Congestion -> Infrastructure Failure
    res_503 = CauseCodeTranslator.classify_call_termination(
        status_code=503,
        reason_header='Q.850;cause=34;text="No circuit available"',
    )
    assert res_503["category"] == "TRUNK_CONGESTION"
    assert res_503["is_infrastructure_failure"] is True


def test_privacy_and_pii_masking():
    # Allowlisted diagnostic extensions preserved
    assert mask_phone_number("1001") == "1001"
    assert mask_phone_number("4286") == "4286"

    # E.164 Kenyan passenger/employee number masked
    masked_e164 = mask_phone_number("+254712345678")
    assert masked_e164 == "+2547****678"
    assert "1234" not in masked_e164

    # Local mobile format
    masked_local = mask_phone_number("0712345678")
    assert masked_local == "071****678"

    # Non-allowlisted internal extension
    masked_ext = mask_phone_number("2398")
    assert masked_ext == "2**8"

    # SIP URI masking
    masked_uri = mask_sip_uri("sip:+254712345678@10.2.156.60:5060")
    assert masked_uri == "sip:+2547****678@10.2.156.60:5060"


def test_multi_leg_session_correlation():
    correlator = SessionCorrelator()

    # 1. Asterisk initiates call with Uniqueid
    sess1 = correlator.get_or_create_session(
        asterisk_uniqueid="1731050000.12",
        caller="1001",
        callee="+254712345678",
        start_time=1000.0,
    )
    assert sess1.session_id.startswith("sess-")
    assert sess1.caller_masked == "1001"
    assert sess1.callee_masked == "+2547****678"

    # 2. SIP INVITE generated with Call-ID
    sess2 = correlator.get_or_create_session(
        sip_call_id="call-uuid-9988",
        asterisk_uniqueid="1731050000.12",
    )
    # Must resolve to same session
    assert sess2.session_id == sess1.session_id

    # 3. Avaya SBCE CDR links session with Global Call ID
    sess3 = correlator.get_or_create_session(
        avaya_session_id="avaya-gcid-445566",
        sip_call_id="call-uuid-9988",
    )
    assert sess3.session_id == sess1.session_id

    # 4. Add call legs
    correlator.add_call_leg(sess1.session_id, "leg-1", "AMI", "Asterisk", "Asterisk-Channel", start_time=1000.0)
    correlator.add_call_leg(sess1.session_id, "leg-2", "SIP", "Asterisk", "Avaya-SBCE", start_time=1000.05)

    # 5. Terminate session
    sess_term = correlator.terminate_session(
        session_id=sess1.session_id,
        final_sip_code=200,
        end_time=1015.0,
    )
    assert sess_term.termination_category == "SUCCESS"
    assert sess_term.duration_seconds == 15.0
    assert sess_term.is_operational_failure is False
    assert len(sess_term.legs) == 2
    assert sess_term.legs[0].status == "TERMINATED"

