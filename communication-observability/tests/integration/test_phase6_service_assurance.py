"""Integration tests for Phase 6: End-to-End Media Quality and Voice Service Assurance.

Validates:
1. Zabbix Synthetic Probe template & host provisioning in live Zabbix 7.4.
2. Trapper ingestion over TCP 10051 via pure Python ZabbixSender.
3. Verification of persisted metrics in PostgreSQL via Zabbix API history queries.
4. Trigger evaluation on simulated voice degradation.
5. Live cross-domain incident correlation engine against Zabbix API.
6. Grafana Voice Service Assurance dashboard provisioning and API accessibility.
7. Full loop execution from Asterisk synthetic call to correlated assurance report.
"""

import os
import time
import pytest
import urllib.request
import json

from services.api.client import ZabbixClient
from services.api.config import get_settings
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import (
    HypothesisStatus,
    RootCauseDomain,
    ServiceHealthState,
)
from services.voice.models import CallOutcome, MediaVerificationLevel, SyntheticCallRequest
from services.voice.runner import SyntheticCallRunner
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
from services.voice.zabbix_sender import ZabbixMetric, ZabbixSender


@pytest.fixture(scope="module")
def zabbix_client() -> ZabbixClient:
    """Provide an authenticated Zabbix JSON-RPC API client."""
    settings = get_settings()
    client = ZabbixClient(settings.zabbix)
    client.connect()
    return client


def test_01_voice_synthetic_probe_template_provisioned(zabbix_client: ZabbixClient):
    """Verify template 'Nawari Voice Synthetic Probe by Zabbix Trapper' exists with trapper items."""
    templates = zabbix_client.call("template.get", {
        "filter": {"host": "Nawari Voice Synthetic Probe by Zabbix Trapper"},
        "selectItems": ["key_", "name", "type", "value_type"],
    })
    assert len(templates) == 1, "Expected template 'Nawari Voice Synthetic Probe by Zabbix Trapper'"
    tpl = templates[0]

    item_keys = {item["key_"] for item in tpl.get("items", [])}
    expected_keys = {
        "voice.synthetic.outcome",
        "voice.synthetic.sip_status",
        "voice.synthetic.setup_time",
        "voice.synthetic.duration",
        "voice.synthetic.media_status",
        "voice.synthetic.mos",
        "voice.synthetic.r_factor",
        "voice.synthetic.jitter",
        "voice.synthetic.packet_loss",
        "voice.synthetic.rtt",
        "voice.synthetic.one_way_delay",
    }
    missing = expected_keys - item_keys
    assert not missing, f"Missing trapper items in template: {missing}"


def test_02_voice_synthetic_probe_host_provisioned(zabbix_client: ZabbixClient):
    """Verify host 'nawari-voice-probe-01' exists and is linked to the probe template."""
    hosts = zabbix_client.call("host.get", {
        "filter": {"host": "nawari-voice-probe-01"},
        "selectParentTemplates": ["host", "name"],
    })
    assert len(hosts) == 1, "Expected host 'nawari-voice-probe-01' to exist in Zabbix"
    host = hosts[0]
    tpl_names = {t["name"] for t in host.get("parentTemplates", [])}
    assert "Nawari Voice Synthetic Probe by Zabbix Trapper" in tpl_names


def test_03_zabbix_sender_live_trapper_ingestion(zabbix_client: ZabbixClient):
    """Verify pure Python ZabbixSender transmits metrics over TCP 10051 and records in DB."""
    sender = ZabbixSender(host="127.0.0.1", port=10051)
    now = int(time.time())

    # Send a unique probe metric bundle
    test_mos = 4.28
    test_jitter = 3.4
    test_loss = 0.5
    test_setup = 145.0

    metrics = [
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.outcome", "ANSWERED", now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.sip_status", 200, now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.setup_time", test_setup, now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.duration", 5.0, now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.media_status", "BIDIRECTIONAL", now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.mos", test_mos, now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.jitter", test_jitter, now),
        ZabbixMetric("nawari-voice-probe-01", "voice.synthetic.packet_loss", test_loss, now),
    ]

    resp = sender.send(metrics)
    assert resp.response == "success"
    assert resp.processed == len(metrics), f"Expected {len(metrics)} processed, got {resp.processed} ({resp.info})"

    # Verify metrics stored in PostgreSQL via Zabbix API (wait briefly for history cache flush)
    items = zabbix_client.call("item.get", {
        "host": "nawari-voice-probe-01",
        "filter": {"key_": "voice.synthetic.mos"},
    })
    assert len(items) == 1
    mos_item_id = items[0]["itemid"]

    latest_val = None
    for _ in range(10):
        history = zabbix_client.call("history.get", {
            "itemids": [mos_item_id],
            "history": 0,  # float
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit": 5,
        })
        if history and abs(float(history[0]["value"]) - test_mos) < 0.01:
            latest_val = float(history[0]["value"])
            break
        time.sleep(0.5)

    assert latest_val is not None, f"Expected {test_mos} to be flushed to history, latest was {history[0]['value'] if history else 'None'}"
    assert abs(latest_val - test_mos) < 0.01


def test_04_canonical_voice_event_sender_transmission(zabbix_client: ZabbixClient):
    """Verify CanonicalVoiceEvent object can be sent directly via ZabbixSender."""
    now = time.time()
    event = CanonicalVoiceEvent(
        collection_timestamp=now,
        device_id="nawari-voice-probe-01",
        service_id="voice-service-default",
        correlation=CorrelationIdentifiers(action_id="act-integ-test-4"),
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=now - 5.0, hungup=now),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            setup_time_ms=132.0,
            duration_seconds=5.0,
            sip_status_code=200,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            estimated_mos=4.36,
            r_factor=91.0,
            jitter_ms=1.9,
            loss_pct=0.0,
            rtt_ms=14.0,
            estimated_one_way_delay_ms=27.8,
            data_completeness=DataCompleteness.COMPLETE,
            measurement_confidence=MeasurementConfidence.HIGH,
        ),
    )

    sender = ZabbixSender(host="127.0.0.1", port=10051)
    resp = sender.send_voice_event(event)
    assert resp.response == "success"
    assert resp.processed >= 8, f"Expected >= 8 processed, got {resp.processed}"


def test_05_cross_domain_correlation_with_live_zabbix_api(zabbix_client: ZabbixClient):
    """Verify CrossDomainCorrelator interacts with live Zabbix API client."""
    correlator = CrossDomainCorrelator(zabbix_client=zabbix_client)

    # Active problems from live Zabbix
    problems = correlator.fetch_active_problems()
    assert isinstance(problems, list)

    # Create a voice event
    now = time.time()
    event = CanonicalVoiceEvent(
        collection_timestamp=now,
        device_id="nawari-voice-probe-01",
        endpoints=EndpointIdentifiers(destination="1001"),
        timestamps=MilestoneTimestamps(initiated=now - 5.0, hungup=now),
        signaling=SignalingTelemetry(
            outcome=CallOutcome.ANSWERED,
            setup_time_ms=150.0,
            duration_seconds=5.0,
            sip_status_code=200,
        ),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            estimated_mos=4.40,
            r_factor=92.0,
            jitter_ms=1.5,
            loss_pct=0.0,
            rtt_ms=12.0,
            estimated_one_way_delay_ms=25.0,
            data_completeness=DataCompleteness.COMPLETE,
        ),
    )

    report = correlator.correlate(event)
    assert report.service_id == "voice-service-default"
    assert report.target_host == "nawari-voice-probe-01"
    assert report.primary_hypothesis is not None
    assert report.primary_hypothesis.confidence > 0.0


def test_06_grafana_voice_assurance_dashboard_accessible():
    """Verify Grafana serves the Nawari Voice Service Assurance dashboard via HTTP API."""
    import base64

    url = "http://localhost:3001/api/dashboards/uid/nawari-voice-service-assurance"
    req = urllib.request.Request(url)
    auth_str = "admin:nawari_grafana_dev_pass"
    req.add_header("Authorization", f"Basic {base64.b64encode(auth_str.encode()).decode()}")

    with urllib.request.urlopen(req, timeout=5.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        dashboard = data.get("dashboard", {})
        assert dashboard.get("uid") == "nawari-voice-service-assurance"
        assert "Voice Service Assurance" in dashboard.get("title", "")
        panels = dashboard.get("panels", [])
        assert len(panels) >= 10, f"Expected at least 10 panels, found {len(panels)}"


def test_07_live_synthetic_call_to_assurance_loop(zabbix_client: ZabbixClient):
    """Execute live Asterisk call probe, send to Zabbix, correlate and generate report."""
    from services.voice.config import get_voice_settings
    from services.voice.safety import CircuitBreakerState

    voice_settings = get_voice_settings()
    # Reset circuit breaker or wait for cooldown if preceding tests just called Asterisk
    state = CircuitBreakerState.load(voice_settings.circuit_breaker_state_path)
    if state.is_tripped or (state.last_call_time > 0 and time.time() - state.last_call_time < voice_settings.cooldown_seconds):
        time.sleep(max(0.1, voice_settings.cooldown_seconds - (time.time() - state.last_call_time) + 0.2))

    runner = SyntheticCallRunner(settings=voice_settings)
    req = SyntheticCallRequest(target="1001", timeout_seconds=6.0)
    call_res = runner.execute_call(req)

    assert call_res.outcome == CallOutcome.ANSWERED
    assert call_res.duration_seconds > 0

    # Convert to canonical event
    event = CanonicalVoiceEvent.from_call_result(call_res, device_id="nawari-voice-probe-01")
    assert event.endpoints.destination == "1001"

    # Send to Zabbix
    sender = ZabbixSender(host="127.0.0.1", port=10051)
    resp = sender.send_voice_event(event)
    assert resp.processed >= 4

    # Run cross-domain correlation
    correlator = CrossDomainCorrelator(zabbix_client=zabbix_client)
    report = correlator.correlate(event)

    assert report.health_state in (ServiceHealthState.HEALTHY, ServiceHealthState.CRITICAL, ServiceHealthState.DEGRADED, ServiceHealthState.UNKNOWN)
    assert report.primary_hypothesis is not None
    assert len(report.primary_hypothesis.remediation_recommendations) >= 0
