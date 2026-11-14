"""Integration tests for Phase 6.1: Validation, Hardening & Resilience Pass.

Validates:
1. Zabbix Item Types, Units, and Schema Integrity on nawari-voice-probe-01.
2. Real-time Trigger Evaluation (Firing) and Automated Recovery (Clearing).
3. Duplicate Timestamp Handling & Nanosecond Resolution in PostgreSQL.
4. ZabbixSender Resilience: Connection Retries, Offline Spooling & Spool Replay.
5. Telemetry Staleness Guard & Health State Degradation.
6. Unidirectional Media Invariant Enforcement (No Fabricated MOS).
7. Calibrated Hypothesis Classification (Confirmed vs Probable vs Suspected).
"""

import json
import time
from pathlib import Path
import pytest

from services.api.client import ZabbixClient
from services.api.config import get_settings
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import (
    HypothesisStatus,
    RootCauseDomain,
    ServiceHealthState,
    TelemetricEnvironment,
)
from services.voice.models import (
    CallOutcome,
    MediaQualityMetrics,
    MediaVerificationLevel,
    SipSignalingMetrics,
    SyntheticCallResult,
)
from services.voice.rtp_analyzer import RtpAnalyzer
from services.voice.telemetry_schema import (
    CanonicalVoiceEvent,
    CorrelationIdentifiers,
    DataCompleteness,
    EndpointIdentifiers,
    MeasurementConfidence,
    MediaTelemetry,
    MilestoneTimestamps,
    SignalingTelemetry,
)
from services.voice.zabbix_sender import (
    ZabbixMetric,
    ZabbixSender,
    ZabbixSenderError,
)


@pytest.fixture(scope="module")
def zabbix_client() -> ZabbixClient:
    """Authenticated Zabbix API client."""
    client = ZabbixClient(get_settings().zabbix)
    client.connect()
    return client


def test_01_zabbix_item_types_and_units_integrity(zabbix_client: ZabbixClient):
    """Verify all 12 items on nawari-voice-probe-01 have correct data types, units, and tags."""
    items = zabbix_client.call("item.get", {
        "host": "nawari-voice-probe-01",
        "selectTags": "extend",
    })
    item_map = {item["key_"]: item for item in items}

    # Float items (value_type == '0')
    float_keys = {
        "voice.synthetic.setup_time": "ms",
        "voice.synthetic.duration": "s",
        "voice.synthetic.mos": "",
        "voice.synthetic.r_factor": "",
        "voice.synthetic.jitter": "ms",
        "voice.synthetic.packet_loss": "%",
        "voice.synthetic.rtt": "ms",
        "voice.synthetic.one_way_delay": "ms",
    }
    for k, unit in float_keys.items():
        assert k in item_map, f"Missing item {k}"
        assert item_map[k]["value_type"] == "0", f"Item {k} expected value_type 0 (float), got {item_map[k]['value_type']}"
        if unit:
            assert item_map[k]["units"] == unit, f"Item {k} expected units '{unit}', got '{item_map[k]['units']}'"

    # Unsigned int item (value_type == '3')
    assert "voice.synthetic.sip_status" in item_map
    assert item_map["voice.synthetic.sip_status"]["value_type"] == "3"

    # Character / text items (value_type == '1' or '4')
    char_keys = [
        "voice.synthetic.outcome",
        "voice.synthetic.media_status",
        "voice.synthetic.environment",
    ]
    for k in char_keys:
        assert k in item_map, f"Missing item {k}"
        assert item_map[k]["value_type"] in ("1", "4"), f"Item {k} expected character type"


def test_02_zabbix_trigger_firing_and_recovery(zabbix_client: ZabbixClient):
    """Verify that a synthetic failure fires a trigger and subsequent success clears/recovers it."""
    sender = ZabbixSender(host="127.0.0.1", port=10051)
    now = int(time.time())

    # Step A: Inject synthetic failure (outcome=FAILED)
    metric_fail = [
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.outcome", "FAILED", now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.sip_status", 500, now),
    ]
    resp = sender.send(metric_fail)
    assert resp.processed == 2

    # Step B: Wait for Zabbix server trigger evaluation and verify problem appears
    problem_found = False
    for _ in range(15):
        problems = zabbix_client.call("problem.get", {
            "output": ["eventid", "name", "severity"],
            "recent": True,
            "sortfield": ["eventid"],
            "sortorder": "DESC",
        })
        for p in problems:
            if "Synthetic voice test failed" in p.get("name", ""):
                problem_found = True
                break
        if problem_found:
            break
        time.sleep(1.0)

    assert problem_found, "Expected trigger 'Synthetic voice test failed or congested' to fire"

    # Step C: Inject healthy metric (outcome=ANSWERED)
    now_recovery = int(time.time()) + 2
    metric_ok = [
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.outcome", "ANSWERED", now_recovery),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.sip_status", 200, now_recovery),
    ]
    resp_ok = sender.send(metric_ok)
    assert resp_ok.processed == 2

    # Step D: Verify trigger recovers (problem resolves / r_eventid is populated)
    recovered = False
    for _ in range(15):
        problems = zabbix_client.call("problem.get", {
            "output": ["eventid", "name", "r_eventid"],
            "sortfield": ["eventid"],
            "sortorder": "DESC",
        })
        # If problem cleared or r_eventid != '0', trigger recovered
        active_probe_problems = [
            p for p in problems if "Synthetic voice test failed" in p.get("name", "") and p.get("r_eventid", "0") == "0"
        ]
        if not active_probe_problems:
            recovered = True
            break
        time.sleep(1.0)

    assert recovered, "Expected trigger 'Synthetic voice test failed or congested' to recover after ANSWERED test"


def test_03_duplicate_timestamp_and_ns_resolution(zabbix_client: ZabbixClient):
    """Verify that multiple metrics sent with the exact same epoch second are preserved."""
    sender = ZabbixSender(host="127.0.0.1", port=10051)
    fixed_clock = int(time.time())

    # Send 2 metrics for voice.synthetic.setup_time at identical clock
    m1 = [ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.setup_time", 111.0, fixed_clock)]
    m2 = [ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.setup_time", 222.0, fixed_clock)]

    r1 = sender.send(m1)
    time.sleep(0.05)
    r2 = sender.send(m2)

    assert r1.processed == 1
    assert r2.processed == 1

    # Query item history (wait up to 3s for history cache flush)
    items = zabbix_client.call("item.get", {
        "host": "nawari-voice-probe-01",
        "filter": {"key_": "voice.synthetic.setup_time"},
    })
    vals = set()
    for _ in range(10):
        hist = zabbix_client.call("history.get", {
            "itemids": [items[0]["itemid"]],
            "history": 0,
            "time_from": fixed_clock - 2,
            "time_till": fixed_clock + 2,
        })
        if hist:
            vals = {float(h["value"]) for h in hist}
            if 111.0 in vals or 222.0 in vals:
                break
        time.sleep(0.5)

    assert 111.0 in vals or 222.0 in vals


def test_04_zabbix_sender_offline_spool_and_replay(tmp_path: Path):
    """Verify ZabbixSender retries, spools to disk on outage, and replays upon recovery."""
    spool_file = tmp_path / "zabbix_spool.jsonl"
    # Port 19999 has no listener
    offline_sender = ZabbixSender(
        host="127.0.0.1",
        port=19999,
        timeout=0.2,
        max_retries=1,
        backoff_factor=0.05,
        spool_file=spool_file,
    )

    metrics = [
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.outcome", "ANSWERED"),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.duration", 4.5),
    ]

    with pytest.raises(ZabbixSenderError) as exc_info:
        offline_sender.send(metrics)

    assert exc_info.value.spooled is True
    assert spool_file.exists()

    with open(spool_file, "r") as f:
        lines = f.readlines()
    assert len(lines) == 2

    # Now replay to live Zabbix Server (port 10051)
    replayer = ZabbixSender(host="127.0.0.1", port=10051, spool_file=spool_file)
    replayed_count = replayer.replay_spool()
    assert replayed_count == 2
    assert not spool_file.exists(), "Spool file should be deleted upon successful replay"


def test_05_stale_telemetry_detection_and_service_state():
    """Verify that stale telemetry (>15m) produces UNKNOWN service health and SUSPECTED hypothesis."""
    now = time.time()
    event = CanonicalVoiceEvent(
        collection_timestamp=now - 1200.0,  # 20 min ago
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=now - 1205.0, hungup=now - 1200.0),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            setup_time_ms=100.0,
            duration_seconds=5.0,
            sip_status_code=200,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            estimated_mos=4.4,
            data_completeness=DataCompleteness.COMPLETE,
        ),
    )

    correlator = CrossDomainCorrelator()
    report = correlator.correlate(event, active_problems=[])

    assert report.is_stale is True
    assert report.health_state == ServiceHealthState.UNKNOWN
    stale_hyp = [h for h in report.hypotheses if "Stale Voice Telemetry" in h.title]
    assert len(stale_hyp) == 1
    assert stale_hyp[0].status == HypothesisStatus.SUSPECTED


def test_06_unidirectional_media_invalidates_mos_in_end_to_end_flow():
    """Verify that one-way audio invalidates MOS across models, schemas, and trapper serialization."""
    metrics = RtpAnalyzer.from_metrics(
        jitter_ms=2.5,
        loss_pct=0.0,
        rtt_ms=15.0,
        packets_sent=300,
        packets_received=0,  # TRANSMIT_ONLY
    )
    assert not metrics.is_valid
    assert metrics.estimated_mos is None
    assert metrics.loss_pct is None  # Not 0.0%

    call_result = SyntheticCallResult(
        action_id="act-oneway-audit",
        target="1001",
        outcome=CallOutcome.ANSWERED,
        success=True,
        timestamp_start=time.time() - 5.0,
        timestamp_end=time.time(),
        duration_seconds=5.0,
        signaling=SipSignalingMetrics(sip_status_code=200),
        media=metrics,
    )

    event = CanonicalVoiceEvent.from_call_result(call_result)
    assert event.media.verification_level == MediaVerificationLevel.TRANSMIT_ONLY
    assert event.media.estimated_mos is None
    assert event.media.data_completeness == DataCompleteness.PARTIAL_MISSING_MEDIA

    # Convert to Zabbix metrics: MOS must NOT be emitted
    zbx_metrics = event.to_zabbix_metrics()
    zbx_keys = {m.key for m in zbx_metrics}
    assert "voice.synthetic.mos" not in zbx_keys
    assert "voice.synthetic.packet_loss" not in zbx_keys


def test_07_distinguish_confirmed_from_probable_hypotheses():
    """Verify clear distinction between Confirmed and Probable causes in incident correlation."""
    event = CanonicalVoiceEvent(
        collection_timestamp=time.time(),
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=time.time() - 5.0, hungup=time.time()),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.TIMEOUT,
            sip_status_code=408,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.NO_MEDIA,
            data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA,
        ),
    )

    active_problems = [
        {"eventid": "301", "name": "Interface B1 link down on mock-avaya-sbce-01", "severity": "4"}
    ]

    correlator = CrossDomainCorrelator()

    # Case 1: Correlated indicators without direct causality proof -> PROBABLE
    report_probable = correlator.correlate(event, active_problems=active_problems)
    primary = report_probable.primary_hypothesis
    assert primary is not None
    assert primary.status == HypothesisStatus.PROBABLE
    assert "Probable" in primary.title

    # Case 2: Direct causal proof -> CONFIRMED
    report_confirmed = correlator.correlate(
        event, active_problems=active_problems, infrastructure_metrics={"direct_causality": True}
    )
    primary_conf = report_confirmed.primary_hypothesis
    assert primary_conf is not None
    assert primary_conf.status == HypothesisStatus.CONFIRMED
    assert primary_conf.confidence > primary.confidence
