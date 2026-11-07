#!/usr/bin/env bash
# ==============================================================================
# NAWARI — Phase 5 Acceptance Verification Script
# Voice Telemetry, SIP Health & Controlled Synthetic Calls
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
    if "${func}" > /tmp/nawari_phase5_check.log 2>&1; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        FAIL=$((FAIL + 1))
        echo "  [ERROR LOG]:"
        cat /tmp/nawari_phase5_check.log | sed 's/^/    /'
    fi
}

echo "======================================================================"
echo "NAWARI PHASE 5 ACCEPTANCE VERIFICATION: VOICE OBSERVABILITY"
echo "======================================================================"

check_compose_profile_isolation() {
    cd "${PROJECT_ROOT}"
    # Verify asterisk is NOT in default compose services
    local default_services
    default_services=$(docker compose --env-file .env -f docker/compose.yaml -f docker/compose.dev.yaml config --services)
    if echo "${default_services}" | grep -q "^asterisk$"; then
        echo "Error: asterisk service is present without profile"
        return 1
    fi

    # Verify asterisk IS in profile services
    local profile_services
    profile_services=$(docker compose --env-file .env -f docker/compose.yaml -f docker/compose.dev.yaml --profile synthetic-voice config --services)
    if ! echo "${profile_services}" | grep -q "^asterisk$"; then
        echo "Error: asterisk service missing from synthetic-voice profile"
        return 1
    fi
}

check_asterisk_container_healthy() {
    docker exec nawari-asterisk asterisk -rx "core show version" | grep -q "Asterisk 22"
}

check_pjsip_endpoints_configured() {
    local endpoints
    endpoints=$(docker exec nawari-asterisk asterisk -rx "pjsip show endpoints")
    for ep in 1001 1002 1003 1004 avaya-sbce-trunk; do
        if ! echo "${endpoints}" | grep -q "${ep}"; then
            echo "Endpoint ${ep} missing in PJSIP"
            return 1
        fi
    done
}

check_ami_authentication() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.voice.config import get_voice_settings
from services.voice.ami_client import AmiClient

settings = get_voice_settings()
with AmiClient(
    host=settings.ami_host,
    port=settings.ami_port,
    username=settings.ami_user,
    secret=settings.ami_secret,
    timeout=5.0,
) as ami:
    resp = ami.ping()
    assert resp.get('Response') == 'Success'
"
}

check_synthetic_call_echo_1001() {
    cd "${PROJECT_ROOT}"
    sleep 6
    "${PYTHON}" -c "
from services.voice.config import get_voice_settings
from services.voice.runner import SyntheticCallRunner
from services.voice.models import SyntheticCallRequest, CallOutcome

runner = SyntheticCallRunner(get_voice_settings())
runner.safety.reset_circuit_breaker()
res = runner.execute_call(SyntheticCallRequest(target='1001', timeout_seconds=10.0))
assert res.success, f'Call failed: {res.error_message}'
assert res.outcome == CallOutcome.ANSWERED
assert res.signaling.sip_status_code == 200
assert res.signaling.hangup_cause in {0, 16}
"
}

check_synthetic_call_fast_answer_1002() {
    cd "${PROJECT_ROOT}"
    sleep 6
    "${PYTHON}" -c "
from services.voice.config import get_voice_settings
from services.voice.runner import SyntheticCallRunner
from services.voice.models import SyntheticCallRequest, CallOutcome

runner = SyntheticCallRunner(get_voice_settings())
res = runner.execute_call(SyntheticCallRequest(target='1002', timeout_seconds=10.0))
assert res.success, f'Call failed: {res.error_message}'
assert res.outcome == CallOutcome.ANSWERED
assert res.signaling.sip_status_code == 200
assert res.duration_seconds >= 2.5
"
}

check_synthetic_call_busy_1003() {
    cd "${PROJECT_ROOT}"
    sleep 6
    "${PYTHON}" -c "
from services.voice.config import get_voice_settings
from services.voice.runner import SyntheticCallRunner
from services.voice.models import SyntheticCallRequest, CallOutcome

runner = SyntheticCallRunner(get_voice_settings())
res = runner.execute_call(SyntheticCallRequest(target='1003', timeout_seconds=10.0))
assert res.outcome == CallOutcome.BUSY
assert res.signaling.sip_status_code == 486
assert res.signaling.hangup_cause in {0, 17}
"
}

check_synthetic_call_congestion_1004() {
    cd "${PROJECT_ROOT}"
    sleep 6
    "${PYTHON}" -c "
from services.voice.config import get_voice_settings
from services.voice.runner import SyntheticCallRunner
from services.voice.models import SyntheticCallRequest, CallOutcome

runner = SyntheticCallRunner(get_voice_settings())
res = runner.execute_call(SyntheticCallRequest(target='1004', timeout_seconds=10.0))
assert res.outcome == CallOutcome.CONGESTION
assert res.signaling.sip_status_code == 503
assert res.signaling.hangup_cause in {0, 34}
"
}

check_safety_gate_rejection() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.voice.config import get_voice_settings
from services.voice.runner import SyntheticCallRunner
from services.voice.models import SyntheticCallRequest, CallOutcome

runner = SyntheticCallRunner(get_voice_settings())
# Emergency rejection
res_emerg = runner.execute_call(SyntheticCallRequest(target='911'))
assert res_emerg.outcome == CallOutcome.SAFETY_BLOCKED
assert not res_emerg.success

# Unauthorized destination rejection
res_unauth = runner.execute_call(SyntheticCallRequest(target='0722123456'))
assert res_unauth.outcome == CallOutcome.SAFETY_BLOCKED
assert not res_unauth.success

# Dry run verification
res_dry = runner.execute_call(SyntheticCallRequest(target='1001', dry_run=True))
assert res_dry.outcome == CallOutcome.DRY_RUN
assert res_dry.success
"
}

check_media_quality_invariant() {
    cd "${PROJECT_ROOT}"
    "${PYTHON}" -c "
from services.voice.rtp_analyzer import RtpAnalyzer

# 1. Verify missing RTCP metrics reports UNKNOWN, never fabricated
m1 = RtpAnalyzer.from_metrics(jitter_ms=None, loss_pct=None)
assert not m1.is_valid
assert m1.mos_score is None
assert m1.r_factor is None

# 2. Verify G.107 E-model calculation on valid telemetry
r, mos = RtpAnalyzer.calculate_mos(jitter_ms=2.0, loss_pct=0.0, rtt_ms=10.0)
assert 92.0 <= r <= 93.2
assert 4.35 <= mos <= 4.42
"
}

run_check "Docker Compose Profile Gating (synthetic-voice)" check_compose_profile_isolation
run_check "Asterisk 22 Runtime Engine Health & CLI" check_asterisk_container_healthy
run_check "PJSIP Diagnostic Endpoints (1001-1004, avaya-sbce-trunk)" check_pjsip_endpoints_configured
run_check "Pure Python AMI Socket Authentication (5038/tcp)" check_ami_authentication
run_check "Synthetic Call Loopback 1001 (Echo & Audio Loop)" check_synthetic_call_echo_1001
run_check "Synthetic Call Loopback 1002 (Fast Answer & Disconnect)" check_synthetic_call_fast_answer_1002
run_check "Synthetic Call Loopback 1003 (Busy Simulation & SIP 486)" check_synthetic_call_busy_1003
run_check "Synthetic Call Loopback 1004 (Congestion Simulation & SIP 503)" check_synthetic_call_congestion_1004
run_check "Pre-Call Safety Gate (Emergency 911 & Allowlist Denial)" check_safety_gate_rejection
run_check "Media Quality Invariant (Missing RTCP Reports UNKNOWN)" check_media_quality_invariant

echo "----------------------------------------------------------------------"
echo "VERIFICATION SUMMARY: ${PASS} PASSED, ${FAIL} FAILED"
echo "======================================================================"

if [[ ${FAIL} -eq 0 ]]; then
    echo ">>> PHASE 5 ACCEPTANCE GATES COMPLETED SUCCESSFULLY <<<"
    exit 0
else
    echo ">>> PHASE 5 VERIFICATION FAILED <<<"
    exit 1
fi

