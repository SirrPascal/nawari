#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 6 Acceptance Verification Script
# End-to-End Media Quality and Voice Service Assurance
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3}"

PASS=0
FAIL=0

run_check() {
    local title="$1"
    local func="$2"
    printf "[TEST] %-65s ... " "${title}"
    if "${func}" > /tmp/nawari_phase6_check.log 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
        echo "  [ERROR LOG]:"
        cat /tmp/nawari_phase6_check.log | sed 's/^/    /'
    fi
}

echo "======================================================================"
echo "NAWARI PHASE 6 ACCEPTANCE VERIFICATION: VOICE SERVICE ASSURANCE"
echo "======================================================================"

check_zabbix_template_items() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.api.client import ZabbixClient
from services.api.config import get_settings
client = ZabbixClient(get_settings().zabbix)
client.connect()
templates = client.call('template.get', {
    'filter': {'host': 'Nawari Voice Synthetic Probe by Zabbix Trapper'},
    'selectItems': ['key_']
})
assert len(templates) == 1, 'Template missing'
keys = {i['key_'] for i in templates[0].get('items', [])}
required = {'voice.synthetic.outcome', 'voice.synthetic.sip_status', 'voice.synthetic.setup_time', 'voice.synthetic.duration', 'voice.synthetic.media_status', 'voice.synthetic.mos', 'voice.synthetic.r_factor', 'voice.synthetic.jitter', 'voice.synthetic.packet_loss', 'voice.synthetic.rtt', 'voice.synthetic.one_way_delay', 'voice.synthetic.environment'}
diff = required - keys
assert not diff, f'Missing keys: {diff}'
"
}

check_zabbix_host_linked() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.api.client import ZabbixClient
from services.api.config import get_settings
client = ZabbixClient(get_settings().zabbix)
client.connect()
hosts = client.call('host.get', {
    'filter': {'host': 'nawari-voice-probe-01'},
    'selectParentTemplates': ['name']
})
assert len(hosts) == 1, 'Host missing'
tpl_names = {t['name'] for t in hosts[0].get('parentTemplates', [])}
assert 'Nawari Voice Synthetic Probe by Zabbix Trapper' in tpl_names, 'Template not linked'
"
}

check_zabbix_trapper_port() {
    nc -z -w 3 127.0.0.1 10051
}

check_zabbix_sender_transmission() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
import time
from services.voice.zabbix_sender import ZabbixSender, ZabbixMetric
sender = ZabbixSender(host='127.0.0.1', port=10051)
now = int(time.time())
metrics = [
    ZabbixMetric('nawari-voice-probe-01', 'voice.synthetic.outcome', 'ANSWERED', now),
    ZabbixMetric('nawari-voice-probe-01', 'voice.synthetic.sip_status', 200, now),
    ZabbixMetric('nawari-voice-probe-01', 'voice.synthetic.mos', 4.35, now),
]
resp = sender.send(metrics)
assert resp.response == 'success'
assert resp.processed == 3, f'Expected 3 processed, got {resp.processed}'
"
}

check_history_db_persistence() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
import time
from services.api.client import ZabbixClient
from services.api.config import get_settings
client = ZabbixClient(get_settings().zabbix)
client.connect()
items = client.call('item.get', {'host': 'nawari-voice-probe-01', 'filter': {'key_': 'voice.synthetic.mos'}})
assert len(items) == 1
hist = client.call('history.get', {'itemids': [items[0]['itemid']], 'history': 0, 'sortfield': 'clock', 'sortorder': 'DESC', 'limit': 1})
assert len(hist) > 0, 'No history records found for MOS'
"
}

check_canonical_schema_invariants() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
import pytest
from services.voice.models import MediaVerificationLevel
from services.voice.telemetry_schema import CanonicalVoiceEvent, DataCompleteness, MediaTelemetry, MilestoneTimestamps, EndpointIdentifiers
# Invariant: Incomplete RTCP cannot have estimated_mos
try:
    ev = CanonicalVoiceEvent(
        device_id='test',
        endpoints=EndpointIdentifiers(destination='1001'),
        timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
        media=MediaTelemetry(
            verification_level=MediaVerificationLevel.BIDIRECTIONAL,
            data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA,
            estimated_mos=4.2
        ),
    )
    ev.validate()
    raise AssertionError('Should have failed validation')
except ValueError:
    pass
"
}

check_correlator_link_failure() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import HypothesisStatus, RootCauseDomain, ServiceHealthState
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import CanonicalVoiceEvent, EndpointIdentifiers, MilestoneTimestamps, SignalingTelemetry, MediaTelemetry, DataCompleteness

ev = CanonicalVoiceEvent(
    device_id='nawari-voice-probe-01',
    endpoints=EndpointIdentifiers(destination='1001'),
    timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
    signaling=SignalingTelemetry(outcome=CallOutcome.TIMEOUT, sip_status_code=408),
    media=MediaTelemetry(verification_level=MediaVerificationLevel.NO_MEDIA, data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA),
)
problems = [{'eventid': '101', 'name': 'Interface B1 link down on mock-avaya-sbce-01', 'severity': '4'}]
corr = CrossDomainCorrelator()
report = corr.correlate(ev, active_problems=problems)
assert report.health_state == ServiceHealthState.CRITICAL
assert report.primary_hypothesis.status == HypothesisStatus.PROBABLE
assert report.primary_hypothesis.root_cause_domain == RootCauseDomain.NETWORK_LINK
"
}

check_correlator_cpu_overload() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import HypothesisStatus, RootCauseDomain, ServiceHealthState
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import CanonicalVoiceEvent, EndpointIdentifiers, MilestoneTimestamps, SignalingTelemetry, MediaTelemetry, DataCompleteness

ev = CanonicalVoiceEvent(
    device_id='nawari-voice-probe-01',
    endpoints=EndpointIdentifiers(destination='1001'),
    timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
    signaling=SignalingTelemetry(outcome=CallOutcome.CONGESTION, setup_time_ms=5800.0),
    media=MediaTelemetry(verification_level=MediaVerificationLevel.NO_MEDIA, data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA),
)
problems = [{'eventid': '201', 'name': 'High CPU utilization (>90%) on mock-avaya-sbce-01', 'severity': '4'}]
corr = CrossDomainCorrelator()
report = corr.correlate(ev, active_problems=problems)
assert report.health_state == ServiceHealthState.CRITICAL
assert report.primary_hypothesis.status == HypothesisStatus.PROBABLE
assert report.primary_hypothesis.root_cause_domain == RootCauseDomain.APPLIANCE_OVERLOAD
"
}

check_correlator_one_way_audio() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.assurance.correlator import CrossDomainCorrelator
from services.assurance.models import HypothesisStatus, RootCauseDomain, ServiceHealthState
from services.voice.models import CallOutcome, MediaVerificationLevel
from services.voice.telemetry_schema import CanonicalVoiceEvent, EndpointIdentifiers, MilestoneTimestamps, SignalingTelemetry, MediaTelemetry, DataCompleteness

ev = CanonicalVoiceEvent(
    device_id='nawari-voice-probe-01',
    endpoints=EndpointIdentifiers(destination='1001'),
    timestamps=MilestoneTimestamps(initiated=100.0, hungup=110.0),
    signaling=SignalingTelemetry(outcome=CallOutcome.ANSWERED, sip_status_code=200),
    media=MediaTelemetry(verification_level=MediaVerificationLevel.TRANSMIT_ONLY, data_completeness=DataCompleteness.PARTIAL_MISSING_MEDIA),
)
corr = CrossDomainCorrelator()
report = corr.correlate(ev, active_problems=[])
assert report.health_state == ServiceHealthState.CRITICAL
assert report.primary_hypothesis.status == HypothesisStatus.PROBABLE
assert report.primary_hypothesis.root_cause_domain == RootCauseDomain.FIREWALL_NAT_ASYMMETRY
"
}

check_grafana_dashboard_accessible() {
    curl -s -f -u admin:nawari_grafana_dev_pass http://localhost:3001/api/dashboards/uid/nawari-voice-service-assurance > /dev/null
}

run_check "Gate 1: Zabbix synthetic voice probe template and items" check_zabbix_template_items
run_check "Gate 2: Zabbix synthetic voice probe host provisioned"    check_zabbix_host_linked
run_check "Gate 3: Zabbix Server Trapper port (TCP 10051) healthy"   check_zabbix_trapper_port
run_check "Gate 4: Pure Python ZabbixSender live ingestion"         check_zabbix_sender_transmission
run_check "Gate 5: Database metric persistence in PostgreSQL"        check_history_db_persistence
run_check "Gate 6: Canonical Voice Telemetry Schema invariants"     check_canonical_schema_invariants
run_check "Gate 7: Incident Correlation Scenario A (Link Outage)"   check_correlator_link_failure
run_check "Gate 8: Incident Correlation Scenario B (CPU Overload)"   check_correlator_cpu_overload
run_check "Gate 9: Incident Correlation Scenario C (One-Way Audio)" check_correlator_one_way_audio
run_check "Gate 10: Grafana Voice Service Assurance dashboard"      check_grafana_dashboard_accessible

echo "======================================================================"
echo "PHASE 6 VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [ "${FAIL}" -gt 0 ]; then
    exit 1
fi
exit 0
