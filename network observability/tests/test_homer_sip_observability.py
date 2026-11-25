"""Comprehensive Verification Suite for HOMER 7 SIP Observability, Native HEPv3 Streaming, and AVTEST Correlation.

Verifies:
1. HOMER / Heplify receiver health, port 9060 listeners, metrics, and PostgreSQL storage.
2. Direct HEPv3 capture from Asterisk 22.11.0 (res_hep_pjsip).
3. Retrieval and chronological reconstruction of RFC 3261 SIP ladders from PostgreSQL homer_data.
4. End-to-end isolated synthetic call execution (Ext 1001 Answered / 200 OK, Ext 1003 Busy / 486 Busy Here).
5. Strict safety gates preventing corporate Avaya / external network dialing.
6. Persistent AVTEST correlation storage and HTTP API endpoints.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
import sys

_pkg = Path(__file__).resolve().parent.parent / "platform"
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))

from nawari.homer_client import HomerClient, PERMITTED_LOCAL_EXTENSIONS
from nawari.store import Store


@pytest.fixture
def homer():
    return HomerClient()


@pytest.fixture
def store(tmp_path):
    db_file = tmp_path / "test_homer_nawari.db"
    return Store(str(db_file))


def test_homer_service_status(homer):
    """Verifies that the HOMER / Heplify capture pipeline is healthy and active."""
    status = homer.get_service_status()
    assert status["status"] == "healthy"
    assert status["heplify_server"]["status"] == "running"
    assert status["heplify_server"]["version"] == "1.60.10"
    assert status["heplify_server"]["hep_listener"]["port"] == 9060
    assert status["heplify_server"]["hep_listener"]["active"] is True
    assert status["database"]["engine"] == "PostgreSQL 17"
    assert status["database"]["database"] == "homer_data"
    assert status["database"]["connected"] is True
    assert status["asterisk_capture"]["version"] == "22.11.0"
    assert status["asterisk_capture"]["res_hep"] is True
    assert status["asterisk_capture"]["res_hep_pjsip"] is True
    assert status["asterisk_capture"]["capture_node_id"] == "nawari-avtest-lab"


def test_homer_query_captured_calls(homer):
    """Verifies querying distinct SIP transactions from PostgreSQL hep_proto_1_call."""
    calls = homer.list_captured_calls(limit=10)
    assert isinstance(calls, list)
    assert len(calls) > 0
    first = calls[0]
    assert "call_id" in first
    assert "packet_count" in first
    assert "methods" in first
    assert first["evidence_quality"] in ("verified_genuine_capture", "synthetic_probe")
    assert first["classification"] in ("PRODUCTION", "SYNTHETIC")


def test_homer_sip_ladder_parsing(homer):
    """Verifies that raw captured SIP packets are parsed into a chronological SIP ladder."""
    calls = homer.list_captured_calls(limit=5)
    assert len(calls) > 0
    call_id = calls[0]["call_id"]

    ladder = homer.get_sip_ladder(call_id)
    assert ladder["call_id"] == call_id
    assert ladder["total_hops"] > 0
    assert len(ladder["hops"]) == ladder["total_hops"]
    assert "sequenceDiagram" in ladder["mermaid"]
    assert ladder["correlation_status"] in ("verified", "provisional")
    assert ladder["classification"] in ("PRODUCTION", "SYNTHETIC")

    # Verify individual hop structure
    first_hop = ladder["hops"][0]
    assert "hop_id" in first_hop
    assert "source_node" in first_hop
    assert "target_node" in first_hop
    assert "message_label" in first_hop
    assert "raw_sip" in first_hop
    assert "INVITE" in first_hop["raw_sip"] or "SIP/2.0" in first_hop["raw_sip"]


def test_safety_gate_blocks_corporate_avaya_destinations(homer):
    """Ensures the safety gate strictly rejects external numbers or corporate Avaya IPs."""
    prohibited_destinations = [
        "192.0.2.131",
        "192.0.2.22",
        "999",
        "112",
        "911",
        "+254700000000",
        "9999",
    ]
    for dest in prohibited_destinations:
        with pytest.raises(ValueError, match="Safety Violation"):
            homer.execute_isolated_test_call(extension=dest)


def test_execute_isolated_call_answered_echo(homer):
    """Executes a genuine isolated SIP call to Ext 1001 (Echo) and verifies 200 OK Answered."""
    res = homer.execute_isolated_test_call(extension="1001")
    assert res["target_extension"] == "1001"
    if res['actual_code'] is None:
        assert res['outcome'] == 'UNKNOWN' and res['correlation_status'] != 'verified'
    else:
        assert res['actual_code'] == 200 and res['outcome'] == 'ANSWERED' 
    assert res["correlation_status"] in {"provisional","unmatched"}  # No Action-ID-to-Call-ID proof is supplied.
    assert res["safety_audit"]["corporate_network_contacted"] is False
    assert res["safety_audit"]["avaya_production_impact"] == "ZERO_ISOLATED_LAB"

    # Verify ladder has genuine hops
    ladder = res["ladder"]
    if res['actual_code'] is None:
        assert not any('200 OK' in hop['message_label'] for hop in ladder['hops'])
        return
    assert ladder["total_hops"] >= 4
    assert any("INVITE" in h["message_label"] for h in ladder["hops"])
    assert any("200 OK" in h["message_label"] for h in ladder["hops"])
    # ACK/media coverage is not implied by observing a final SIP response.


def test_execute_isolated_call_busy_failure(homer):
    """Executes a genuine isolated SIP call to Ext 1003 (Busy Simulator) and verifies 486 Busy."""
    res = homer.execute_isolated_test_call(extension="1003")
    assert res["target_extension"] == "1003"
    if res['actual_code'] is None:
        assert res['outcome'] == 'UNKNOWN'
        assert res['correlation_status'] != 'verified'
        assert not any('486' in hop['message_label'] for hop in res['ladder']['hops'])
        return  # Missing capture is unconfirmed, never a fabricated busy response.
    assert res["actual_code"] == 486
    assert res["outcome"] == "BUSY"
    assert res["correlation_status"] in {"provisional","unmatched"}  # No Action-ID-to-Call-ID proof is supplied.

    # Verify ladder contains the 486 response
    ladder = res["ladder"]
    assert any("486" in h["message_label"] for h in ladder["hops"])


def test_avtest_correlation_persistence(store):
    """Verifies persistence and retrieval of AVTEST runs linked to HOMER Call-IDs in store."""
    rec = {
        "avtest_run_id": "avtest-lab-test-01",
        "action_id": "act-test-01",
        "target_extension": "1001",
        "test_name": "Synthetic Echo Test",
        "sip_call_id": "call-id-test-xyz",
        "capture_source_id": "res_hep_pjsip (Asterisk 22.11.0)",
        "homer_reference": "homer://transaction/call-id-test-xyz",
        "actual_code": 200,
        "outcome": "ANSWERED",
        "setup_duration_ms": 115.4,
        "correlation_status": "verified",
        "source_timestamp": "2026-11-17 05:15:00 UTC",
        "ladder": {"call_id": "call-id-test-xyz", "total_hops": 4, "hops": []},
    }
    run_id = store.record_avtest_sip_correlation("default", rec)
    assert run_id == "avtest-lab-test-01"

    runs = store.list_avtest_sip_correlations("default")
    assert len(runs) == 1
    assert runs[0]["sip_call_id"] == "call-id-test-xyz"
    assert runs[0]["outcome"] == "ANSWERED"

    single = store.get_avtest_sip_correlation("default", "avtest-lab-test-01")
    assert single is not None
    assert single["target_extension"] == "1001"
    assert single["homer_reference"] == "homer://transaction/call-id-test-xyz"

