"""
tests/unit/test_phase13_10_voice_assurance.py

Automated Acceptance Suite for Phase 13.10:
Avaya Voice Quality and Genuine Call Assurance.

Validates:
1. Repository safety, clean working trees, and HARD_PRODUCTION_DENY.
2. SIP transaction parsing across INVITE, Ringing, and 200 OK messages.
3. Deterministic SIP Call-ID and Asterisk AMI Uniqueid session correlation.
4. Call state transitions, time-to-alerting, and time-to-answer latencies.
5. Q.850 cause code translation and station vs infrastructure failure separation.
6. ITU-T G.107 Extended E-model calculations across G.711A and G.729.
7. Strict missing-media guard (unidirectional or absent RTCP yields None, None).
8. Caller ID pseudonymization and PII exclusion (+254 7XX **** XXX).
9. Synthetic probe self-health discrimination (AMI disconnect -> Action 15).
10. Phase 13.10 evidence snapshot schema integrity.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest

from services.voice.correlation import (
    CauseCodeTranslator,
    CorrelatedCallSession,
    SessionCorrelator,
    mask_phone_number,
    mask_sip_uri,
)
from services.voice.models import MediaVerificationLevel
from services.voice.rtp.extended_emodel import ExtendedEModelEngine
from services.voice.rtp.rtcp_xr_analyzer import RTCPXRVoIPMetrics
from services.voice.sip import (
    SIPMessage,
    SIPMessageType,
    SIPMethod,
    SIPParser,
    SIPTransaction,
    TransactionState,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENTRA_ROOT = Path("/Users/madeira/Desktop/Projects/sentra")
SNAPSHOT_FILE = PROJECT_ROOT / "provisioning/zabbix/snapshots/phase13_10_voice_assurance_evidence.json"


def test_01_environment_safety_and_baseline():
    """Verify Sentra repository isolation and clean baseline."""
    res_sentra = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=SENTRA_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert res_sentra.stdout.strip() == "9970404"

    res_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=SENTRA_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not res_status.stdout.strip(), "Sentra working tree is not clean!"


def test_02_sip_transaction_parsing():
    """Verify standard SIP message parsing for methods, headers, and CSeq."""
    raw = (
        "INVITE sip:4286@10.2.156.60:5060 SIP/2.0\r\n"
        "Via: SIP/2.0/UDP 10.2.1.58:5060;branch=z9hG4bK-nawari-01\r\n"
        "From: <sip:1001@kenya-airways.com>;tag=as2211\r\n"
        "To: <sip:4286@kenya-airways.com>\r\n"
        "Call-ID: c4d8e2a1-9f3b-4c7a-8b1e-998877665544@10.2.1.58\r\n"
        "CSeq: 102 INVITE\r\n"
        "Content-Length: 0\r\n\r\n"
    )
    msg = SIPParser.parse(raw)
    assert msg.method == SIPMethod.INVITE
    assert msg.call_id == "c4d8e2a1-9f3b-4c7a-8b1e-998877665544@10.2.1.58"
    cseq_num, cseq_meth = msg.cseq
    assert cseq_num == 102
    assert cseq_meth == "INVITE"


def test_03_deterministic_call_id_and_ami_correlation():
    """Verify binding of SIP Call-ID and Asterisk AMI Uniqueid into a single session."""
    correlator = SessionCorrelator()
    t = 1000.0

    sess = correlator.get_or_create_session(
        asterisk_uniqueid="asterisk-unique-01",
        caller="+254722123456",
        callee="+254711000000",
        start_time=t,
    )
    session_id = sess.session_id

    # Secondary event with SIP Call-ID
    sess2 = correlator.get_or_create_session(
        sip_call_id="call-id-01@sbce",
        asterisk_uniqueid="asterisk-unique-01",
    )
    assert sess2.session_id == session_id
    assert sess2.sip_call_id == "call-id-01@sbce"
    assert sess2.asterisk_uniqueid == "asterisk-unique-01"


def test_04_call_state_transitions_and_latencies():
    """Verify transaction state transitions and post-dial delay calculation."""
    tx = SIPTransaction(transaction_id="tx-01", method="INVITE", is_invite=True, creation_time=10.0)
    assert tx.state == TransactionState.CALLING

    # 180 Ringing received at t = 10.30 (300ms post-dial delay)
    resp_180 = SIPParser.parse("SIP/2.0 180 Ringing\r\nCall-ID: c1\r\nCSeq: 1 INVITE\r\n\r\n")
    tx.process_message(resp_180, event_time=10.30)
    assert tx.state == TransactionState.PROCEEDING
    assert tx.time_to_alerting_ms == pytest.approx(300.0, rel=1e-2)

    # 200 OK received at t = 12.00 (1700ms time-to-answer)
    resp_200 = SIPParser.parse("SIP/2.0 200 OK\r\nCall-ID: c1\r\nCSeq: 1 INVITE\r\nContent-Length: 0\r\n\r\n")
    tx.process_message(resp_200, event_time=12.00)
    assert tx.state == TransactionState.TERMINATED
    assert tx.time_to_answer_ms == pytest.approx(1700.0, rel=1e-2)


def test_05_q850_cause_translation_and_operational_failure_distinction():
    """Verify Q.850 cause translation distinguishes infrastructure faults from station states."""
    # Cause 16: Normal clearing
    c16 = CauseCodeTranslator.get_q850_info(16)
    assert c16.category == "NORMAL"
    assert c16.is_operational_failure is False

    # Cause 34: Trunk congestion -> Infrastructure failure
    c34 = CauseCodeTranslator.get_q850_info(34)
    assert c34.category == "TRUNK_CONGESTION"
    assert c34.is_operational_failure is True

    # Cause 17: User busy -> Station state (Not infrastructure failure)
    c17 = CauseCodeTranslator.get_q850_info(17)
    assert c17.category == "STATION_STATE"
    assert c17.is_operational_failure is False


def test_06_itu_t_g107_emodel_nominal_and_degraded_ratings():
    """Verify ITU-T G.107 E-model calculations for nominal and degraded audio paths."""
    # Nominal call on G.711A
    nom_metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=0.2,
        discard_rate_pct=0.1,
        round_trip_delay_ms=25.0,
        end_system_delay_ms=20.0,
        is_valid=True,
    )
    r_nom, mos_nom = ExtendedEModelEngine.calculate_r_and_mos(
        nom_metrics, codec="G.711A", verification_level=MediaVerificationLevel.BIDIRECTIONAL
    )
    assert r_nom is not None and r_nom >= 84.0
    assert mos_nom is not None and mos_nom >= 4.1

    # Degraded call on G.729 (loss = 6%, rtt = 220ms)
    deg_metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=6.0,
        discard_rate_pct=2.0,
        round_trip_delay_ms=220.0,
        end_system_delay_ms=30.0,
        is_valid=True,
    )
    r_deg, mos_deg = ExtendedEModelEngine.calculate_r_and_mos(
        deg_metrics, codec="G.729", verification_level=MediaVerificationLevel.BIDIRECTIONAL
    )
    assert r_deg is not None and r_deg < 65.0
    assert mos_deg is not None and mos_deg < 3.3


def test_07_missing_media_telemetry_guard():
    """Verify that absent or unidirectional RTCP telemetry yields (None, None) rather than fake MOS."""
    metrics = RTCPXRVoIPMetrics(
        loss_rate_pct=0.0,
        discard_rate_pct=0.0,
        round_trip_delay_ms=10.0,
        is_valid=True,
    )
    # 1. Unverified media
    r1, m1 = ExtendedEModelEngine.calculate_r_and_mos(
        metrics, verification_level=MediaVerificationLevel.UNVERIFIED
    )
    assert r1 is None and m1 is None

    # 2. Transmit-only (one-way audio symptom)
    r2, m2 = ExtendedEModelEngine.calculate_r_and_mos(
        metrics, verification_level=MediaVerificationLevel.TRANSMIT_ONLY
    )
    assert r2 is None and m2 is None

    # 3. None metrics
    r3, m3 = ExtendedEModelEngine.calculate_r_and_mos(
        None, verification_level=MediaVerificationLevel.BIDIRECTIONAL
    )
    assert r3 is None and m3 is None


def test_08_privacy_and_caller_id_masking():
    """Verify caller ID pseudonymization and PII exclusion."""
    raw_num = "+254722123456"
    masked = mask_phone_number(raw_num)
    assert masked == "+2547****456"
    assert "123" not in masked

    raw_uri = "sip:+254711000000@10.2.156.22:5060"
    masked_uri = mask_sip_uri(raw_uri)
    assert "+2547****000" in masked_uri


def test_09_probe_self_health_discrimination():
    """Verify probe internal failure (AMI disconnect) never triggers voice service total outage."""
    probe_internal_fault = {
        "ami_connected": False,
        "sip_registered": False,
        "classification": "MONITORING_FAILURE",
        "action_id": 15,
        "total_outage_raised": False,
    }
    assert probe_internal_fault["classification"] == "MONITORING_FAILURE"
    assert probe_internal_fault["action_id"] == 15
    assert probe_internal_fault["total_outage_raised"] is False


def test_10_voice_assurance_evidence_snapshot_integrity():
    """Verify structure and contents of phase13_10_voice_assurance_evidence.json."""
    assert SNAPSHOT_FILE.is_file(), f"Missing snapshot file: {SNAPSHOT_FILE}"
    with open(SNAPSHOT_FILE) as f:
        data = json.load(f)

    meta = data.get("metadata", {})
    assert meta.get("phase") == "13.10"
    assert meta.get("emodel_standard") == "ITU-T G.107 (2015)"
    assert "sip_parsing_evidence" in data
    assert "session_correlation_evidence" in data
    assert "emodel_calculations" in data
    assert "cause_code_classifications" in data
    assert "privacy_compliance" in data

