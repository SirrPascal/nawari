#!/usr/bin/env python3
"""scripts/test_phase13_8b_runtime_hysteresis.py

Phase 13.8B Runtime Hysteresis and Anti-Flapping Verification Script.
Validates live Zabbix 7.4 trigger dual-expression recovery behavior:
1. Problem trigger activation upon crossing problem threshold.
2. Anti-flapping hysteresis deadband holding problem state without premature clearing.
3. Clean recovery event generation upon crossing recovery threshold.
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.api.client.zabbix_client import ZabbixClient
from services.api.config import ZabbixSettings
from services.voice.zabbix_sender import ZabbixSender, ZabbixMetric

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase13_8b_runtime_hysteresis")

RESULTS_PATH = PROJECT_ROOT / "provisioning/zabbix/snapshots/phase13_8b_runtime_hysteresis_results.json"


def get_trigger_state(client: ZabbixClient, host_name: str, description_substr: str) -> Dict[str, Any]:
    hosts = client.call("host.get", {"filter": {"host": [host_name]}})
    if not hosts:
        raise ValueError(f"Host {host_name} not found")
    host_id = hosts[0]["hostid"]

    triggers = client.call("trigger.get", {
        "hostids": [host_id],
        "output": ["triggerid", "description", "value", "state", "recovery_mode", "expression", "recovery_expression"],
        "selectTags": "extend",
    })
    for t in triggers:
        if description_substr.lower() in t["description"].lower():
            return t
    raise ValueError(f"Trigger matching '{description_substr}' not found on {host_name}")


def run_hysteresis_test() -> Dict[str, Any]:
    client = ZabbixClient(ZabbixSettings())
    client.connect()
    sender = ZabbixSender(host="127.0.0.1", port=10051)

    logger.info("Starting Phase 13.8B live runtime hysteresis test...")
    test_results = []

    # =========================================================================
    # Test Scenario 1: WFO Spool Disk Storage Warning
    # Trigger: "WFO: Compliance Voice Recording Spool Disk Storage Warning (< 15%)"
    # Host: avaya-cms-01
    # Problem: last() < 15
    # Recovery: last() > 20
    # Deadband: [15, 20]
    # =========================================================================
    logger.info(">>> Scenario 1: WFO Disk Free Hysteresis (avaya-cms-01: wfo.recording.disk_free_pct)")
    
    # Step 1.1: Ensure initial healthy baseline
    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.disk_free_pct", value=30.0)])
    time.sleep(3)
    t_init = get_trigger_state(client, "avaya-cms-01", "Compliance Voice Recording Spool Disk Storage")
    logger.info("   1. Initial state (disk=30%%): trigger value=%s (0=OK, 1=PROBLEM)", t_init["value"])

    # Step 1.2: Inject Problem Value (10% < 15%)
    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.disk_free_pct", value=10.0)])
    time.sleep(4)
    t_prob = get_trigger_state(client, "avaya-cms-01", "Compliance Voice Recording Spool Disk Storage")
    logger.info("   2. Problem injected (disk=10%%): trigger value=%s (expected 1)", t_prob["value"])
    assert str(t_prob["value"]) == "1", "Trigger must fire upon crossing problem threshold (< 15%)"

    # Step 1.3: Inject Deadband Value (18% - between 15% and 20%)
    # In classic single-expression without hysteresis, 18% >= 15% would immediately clear the alert.
    # In dual-expression mode (recovery > 20%), 18% MUST KEEP the trigger in PROBLEM state!
    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.disk_free_pct", value=18.0)])
    time.sleep(4)
    t_deadband = get_trigger_state(client, "avaya-cms-01", "Compliance Voice Recording Spool Disk Storage")
    logger.info("   3. Deadband injected (disk=18%% in [15,20]): trigger value=%s (expected 1 - HELD BY HYSTERESIS)", t_deadband["value"])
    assert str(t_deadband["value"]) == "1", "Hysteresis failure: trigger prematurely recovered inside deadband (18%)"

    # Step 1.4: Inject Recovery Value (25% > 20%)
    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.disk_free_pct", value=25.0)])
    time.sleep(4)
    t_rec = get_trigger_state(client, "avaya-cms-01", "Compliance Voice Recording Spool Disk Storage")
    logger.info("   4. Recovery injected (disk=25%% > 20%%): trigger value=%s (expected 0 - RECOVERED)", t_rec["value"])
    assert str(t_rec["value"]) == "0", "Trigger must recover when exceeding recovery threshold (> 20%)"

    test_results.append({
        "scenario": "WFO Disk Storage Hysteresis",
        "host": "avaya-cms-01",
        "metric": "wfo.recording.disk_free_pct",
        "problem_threshold": "< 15%",
        "recovery_threshold": "> 20%",
        "deadband_tested": "18%",
        "problem_fired": str(t_prob["value"]) == "1",
        "deadband_held": str(t_deadband["value"]) == "1",
        "recovery_fired": str(t_rec["value"]) == "0",
        "status": "PASS"
    })

    # =========================================================================
    # Test Scenario 2: Synthetic Voice Outcome State Hysteresis
    # Trigger: "Synthetic voice test failed or congested"
    # Host: nawari-voice-probe-01
    # Problem: "FAILED" or "CONGESTION"
    # Recovery: "SUCCESS"
    # =========================================================================
    logger.info(">>> Scenario 2: Synthetic Voice Outcome (nawari-voice-probe-01: voice.synthetic.outcome)")

    # Baseline SUCCESS
    sender.send([ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.outcome", value="SUCCESS")])
    time.sleep(3)

    # Problem FAILED
    sender.send([ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.outcome", value="FAILED")])
    time.sleep(4)
    t_synth_prob = get_trigger_state(client, "nawari-voice-probe-01", "Synthetic voice test failed or congested")
    logger.info("   1. Problem injected (outcome=FAILED): trigger value=%s (expected 1)", t_synth_prob["value"])
    assert str(t_synth_prob["value"]) == "1", "Synthetic voice failure trigger must activate"

    # Recovery SUCCESS
    sender.send([ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.outcome", value="SUCCESS")])
    time.sleep(4)
    t_synth_rec = get_trigger_state(client, "nawari-voice-probe-01", "Synthetic voice test failed or congested")
    logger.info("   2. Recovery injected (outcome=SUCCESS): trigger value=%s (expected 0)", t_synth_rec["value"])
    assert str(t_synth_rec["value"]) == "0", "Synthetic voice trigger must recover"

    test_results.append({
        "scenario": "Synthetic Voice Outcome Lifecycle",
        "host": "nawari-voice-probe-01",
        "metric": "voice.synthetic.outcome",
        "problem_fired": str(t_synth_prob["value"]) == "1",
        "recovery_fired": str(t_synth_rec["value"]) == "0",
        "status": "PASS"
    })

    # =========================================================================
    # Test Scenario 3: WFO Compliance Recording Pipeline Binary Recovery
    # Trigger: "WFO: Compliance Voice Recording Pipeline Health Failure"
    # Host: avaya-cms-01
    # Problem: =0, Recovery: =1
    # =========================================================================
    logger.info(">>> Scenario 3: WFO Recording Pipeline Status (avaya-cms-01: wfo.recording.pipeline_status)")

    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.pipeline_status", value=1)])
    time.sleep(3)

    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.pipeline_status", value=0)])
    time.sleep(4)
    t_wfo_prob = get_trigger_state(client, "avaya-cms-01", "Compliance Voice Recording Pipeline Health")
    logger.info("   1. Pipeline failure injected (=0): trigger value=%s (expected 1)", t_wfo_prob["value"])
    assert str(t_wfo_prob["value"]) == "1", "Pipeline failure must trigger problem"

    sender.send([ZabbixMetric(host="avaya-cms-01", key="wfo.recording.pipeline_status", value=1)])
    time.sleep(4)
    t_wfo_rec = get_trigger_state(client, "avaya-cms-01", "Compliance Voice Recording Pipeline Health")
    logger.info("   2. Pipeline recovery injected (=1): trigger value=%s (expected 0)", t_wfo_rec["value"])
    assert str(t_wfo_rec["value"]) == "0", "Pipeline recovery must clear problem"

    test_results.append({
        "scenario": "WFO Recording Pipeline Lifecycle",
        "host": "avaya-cms-01",
        "metric": "wfo.recording.pipeline_status",
        "problem_fired": str(t_wfo_prob["value"]) == "1",
        "recovery_fired": str(t_wfo_rec["value"]) == "0",
        "status": "PASS"
    })

    # Restore clean state
    sender.send([
        ZabbixMetric(host="avaya-cms-01", key="wfo.recording.disk_free_pct", value=30.0),
        ZabbixMetric(host="avaya-cms-01", key="wfo.recording.pipeline_status", value=1),
        ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.outcome", value="SUCCESS"),
        ZabbixMetric(host="nawari-voice-probe-01", key="voice.synthetic.mos", value=4.2),
    ])
    time.sleep(2)

    report = {
        "phase": "13.8B",
        "title": "Runtime Hysteresis and Dual-Expression Recovery Validation",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(test_results),
        "all_passed": all(r["status"] == "PASS" for r in test_results),
        "results": test_results,
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Runtime hysteresis test report written to %s", RESULTS_PATH)

    return report


if __name__ == "__main__":
    rep = run_hysteresis_test()
    print(f"\nALL RUNTIME HYSTERESIS TESTS PASSED: {rep['all_passed']} ({rep['total_scenarios']}/{rep['total_scenarios']})")

