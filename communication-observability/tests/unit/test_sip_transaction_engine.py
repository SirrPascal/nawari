"""Unit tests for Workstream 10A: SIP Transaction Engine, Parser, and Call-Flow Ladders."""

from __future__ import annotations

import pytest

from services.voice.sip import (
    LadderHop,
    SIPCallLadder,
    SIPMessage,
    SIPMessageType,
    SIPMethod,
    SIPParser,
    SIPTransaction,
    TransactionState,
)


SAMPLE_INVITE = """INVITE sip:4286@10.2.156.60:5060 SIP/2.0
Via: SIP/2.0/UDP 10.2.1.58:5060;branch=z9hG4bK-nawari-01;rport
Max-Forwards: 70
From: <sip:1001@kenya-airways.com>;tag=as2211
To: <sip:4286@kenya-airways.com>
Contact: <sip:1001@10.2.1.58:5060>
Call-ID: c4d8e2a1-9f3b-4c7a-8b1e-998877665544@10.2.1.58
CSeq: 102 INVITE
User-Agent: Nawari Synthetic Voice Probe 1.0
Content-Type: application/sdp
Content-Length: 142

v=0
o=nawari 12345 12345 IN IP4 10.2.1.58
s=Synthetic Call
c=IN IP4 10.2.1.58
t=0 0
m=audio 10002 RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=ptime:20
"""

SAMPLE_200_OK = """SIP/2.0 200 OK
Via: SIP/2.0/UDP 10.2.1.58:5060;branch=z9hG4bK-nawari-01;received=10.2.1.58;rport=5060
From: <sip:1001@kenya-airways.com>;tag=as2211
To: <sip:4286@kenya-airways.com>;tag=avaya-cm-09
Call-ID: c4d8e2a1-9f3b-4c7a-8b1e-998877665544@10.2.1.58
CSeq: 102 INVITE
Server: Avaya Aura Communication Manager 8.1.3
Contact: <sip:4286@10.2.156.60:5060>
Content-Type: application/sdp
Content-Length: 120

v=0
o=AvayaCM 54321 54321 IN IP4 10.2.156.60
s=-
c=IN IP4 10.2.156.60
t=0 0
m=audio 20042 RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=ptime:20
"""

SAMPLE_480_UNAVAILABLE = """SIP/2.0 480 Temporarily Unavailable
Via: SIP/2.0/UDP 10.2.1.58:5060;branch=z9hG4bK-nawari-02;rport=5060
From: <sip:1001@kenya-airways.com>;tag=as2212
To: <sip:2398@kenya-airways.com>;tag=avaya-sm-01
Call-ID: diff-call-id-9988@10.2.1.58
CSeq: 103 INVITE
Warning: 399 avaya-sm01.nbo.kenya-airways.com "User not registered"
Reason: Q.850;cause=18;text="No user responding"
Content-Length: 0

"""


def test_sip_parser_request():
    msg = SIPParser.parse(SAMPLE_INVITE)
    assert msg.message_type == SIPMessageType.REQUEST
    assert msg.method == SIPMethod.INVITE
    assert msg.uri == "sip:4286@10.2.156.60:5060"
    assert msg.call_id == "c4d8e2a1-9f3b-4c7a-8b1e-998877665544@10.2.1.58"
    cseq_num, cseq_meth = msg.cseq
    assert cseq_num == 102
    assert cseq_meth == "INVITE"
    assert "application/sdp" in msg.headers["content-type"]
    assert msg.body is not None
    assert "m=audio 10002 RTP/AVP 0 8" in msg.body


def test_sip_parser_response():
    msg_200 = SIPParser.parse(SAMPLE_200_OK)
    assert msg_200.message_type == SIPMessageType.RESPONSE
    assert msg_200.status_code == 200
    assert msg_200.reason_phrase == "OK"
    assert msg_200.is_success is True

    msg_480 = SIPParser.parse(SAMPLE_480_UNAVAILABLE)
    assert msg_480.status_code == 480
    assert msg_480.is_client_error is True
    assert msg_480.warning_header is not None
    assert "User not registered" in msg_480.warning_header
    assert msg_480.reason_header is not None
    assert "Q.850;cause=18" in msg_480.reason_header


def test_sip_transaction_state_machine_and_latencies():
    inv_msg = SIPParser.parse(SAMPLE_INVITE)
    tx = SIPTransaction(
        transaction_id="tx-inv-102",
        method="INVITE",
        is_invite=True,
        creation_time=100.0,
    )
    assert tx.state == TransactionState.CALLING

    # 1. 100 Trying received at t = 100.05
    resp_100 = SIPParser.parse("SIP/2.0 100 Trying\r\nCall-ID: c4d8e2a1-9f3b\r\nCSeq: 102 INVITE\r\n\r\n")
    tx.process_message(resp_100, event_time=100.05)
    assert tx.state == TransactionState.PROCEEDING

    # 2. 180 Ringing received at t = 100.42
    resp_180 = SIPParser.parse("SIP/2.0 180 Ringing\r\nCall-ID: c4d8e2a1-9f3b\r\nCSeq: 102 INVITE\r\n\r\n")
    tx.process_message(resp_180, event_time=100.42)
    assert tx.state == TransactionState.PROCEEDING
    assert tx.post_dial_delay_ms == pytest.approx(420.0, rel=1e-2)
    assert tx.time_to_alerting_ms == pytest.approx(420.0, rel=1e-2)

    # 3. 200 OK received at t = 102.50
    resp_200 = SIPParser.parse(SAMPLE_200_OK)
    tx.process_message(resp_200, event_time=102.50)
    assert tx.state == TransactionState.TERMINATED
    assert tx.final_response_code == 200
    # Time to Answer = 102.50 - 100.42 = 2.08s = 2080ms
    assert tx.time_to_answer_ms == pytest.approx(2080.0, rel=1e-2)


def test_sip_call_ladder_generation():
    ladder = SIPCallLadder(call_id="call-ladder-01")

    # Asterisk -> SBCE (INVITE)
    ladder.add_hop(
        timestamp=100.0,
        source_node="Asterisk",
        target_node="Avaya-SBCE",
        message_label="INVITE 4286",
        phase="SETUP",
    )

    # SBCE -> Session Manager (INVITE)
    ladder.add_hop(
        timestamp=100.08,
        source_node="Avaya-SBCE",
        target_node="Session-Manager",
        message_label="INVITE 4286",
        phase="SETUP",
    )

    # Session Manager -> SBCE (180 Ringing)
    ladder.add_hop(
        timestamp=100.35,
        source_node="Session-Manager",
        target_node="Avaya-SBCE",
        message_label="180 Ringing",
        phase="ALERTING",
        status_code=180,
    )

    # SBCE -> Asterisk (180 Ringing)
    ladder.add_hop(
        timestamp=100.40,
        source_node="Avaya-SBCE",
        target_node="Asterisk",
        message_label="180 Ringing",
        phase="ALERTING",
        status_code=180,
    )

    d = ladder.to_dict()
    assert d["total_hops"] == 4
    assert len(d["nodes"]) == 3
    assert d["hops"][1]["latency_delta_ms"] == pytest.approx(80.0, rel=1e-2)

    mermaid = ladder.to_mermaid()
    assert "sequenceDiagram" in mermaid
    assert "INVITE 4286" in mermaid

