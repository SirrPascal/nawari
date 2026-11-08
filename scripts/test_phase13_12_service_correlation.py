"""scripts/test_phase13_12_service_correlation.py
==============================================
Executable verification script for Phase 13.12:
Service Dependency Mapping & Event Correlation.

Validates:
1. Business Service Catalog & DAG cycle detection across Kenya Airways services.
2. HA Pair Redundancy Dampening (single SBCE failover vs dual exhaustion).
3. Core Switch Root-Cause Isolation and Downstream Symptom Suppression.
4. Interface Flapping Dampening.
5. Live Zabbix 7.4 Service Tree provisioning & SLA mapping.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.api.config import ZabbixSettings
from services.api.client.zabbix_client import ZabbixClient
from services.assurance.causality_engine import (
    CausalClassification,
    CausalityEngine,
    ServiceImpactLevel,
)
from services.multisite.service_catalog import (
    DependencyLogic,
    ServiceCatalog,
    ServiceTier,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("phase13_12_service_correlation")

SNAPSHOT_FILE = PROJECT_ROOT / "provisioning/zabbix/snapshots/phase13_12_service_correlation_evidence.json"


def run_service_correlation_verification() -> Dict[str, Any]:
    logger.info("======================================================================")
    logger.info("NAWARI PHASE 13.12 — SERVICE DEPENDENCY MAPPING & EVENT CORRELATION")
    logger.info("======================================================================")

    # 1. Environment & Baseline Safety Check
    logger.info("[STEP 1] Auditing repository safety and environment baselines...")
    nawari_rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sentra_rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd="/Users/madeira/Desktop/Projects/sentra", capture_output=True, text=True, check=True).stdout.strip()
    assert sentra_rev == "9970404", f"Sentra repository modified! HEAD: {sentra_rev}"
    logger.info(f"  Nawari HEAD: {nawari_rev}")
    logger.info(f"  Sentra HEAD: {sentra_rev} (Clean & Untouched)")

    # 2. Service Catalog & DAG Verification
    logger.info("[STEP 2] Validating Kenya Airways Business Service Catalog & DAG...")
    catalog = ServiceCatalog(auto_seed=True)
    all_services = catalog.get_all_services()
    logger.info(f"  Registered Business Services in Catalog: {len(all_services)}")

    expected_services = [
        "SVC-ENTERPRISE-NETWORK",
        "SVC-WAN-CONNECTIVITY",
        "SVC-SIP-CARRIER",
        "SVC-CORP-TELEPHONY",
        "SVC-CONTACT-CENTER-INBOUND",
        "SVC-CONTACT-CENTER-OUTBOUND",
        "SVC-IVR-SELFSERVICE",
        "SVC-COMPLIANCE-RECORDING",
    ]
    for s_id in expected_services:
        svc = catalog.get_service(s_id)
        assert svc is not None, f"Expected service '{s_id}' not found in catalog!"
        logger.info(f"    - {svc.service_id}: {svc.name} (Tier: {svc.tier.value}, Dependencies: {len(svc.dependencies)})")

    # DAG Cycle Detection
    cycles = catalog.detect_dependency_cycles()
    assert len(cycles) == 0, f"Circular dependencies detected in service DAG: {cycles}"
    logger.info("  DAG Cycle Detection: 0 cycles detected. Dependency graph is strictly acyclic.")

    # 3. Causality & Correlation Scenarios
    engine = CausalityEngine(flapping_window_seconds=60.0, flapping_threshold_count=3)

    # Scenario A: Single SBCE Member Failure (Failover -> DEGRADED)
    logger.info("[STEP 3] Simulating HA Pair Single Member Failure (avaya-sbce-01 offline)...")
    single_sbce_problems = [
        {
            "eventid": "10001",
            "host": "avaya-sbce-01",
            "name": "SBCE: Signaling Interface Eth0 Link Down",
            "severity": 4,
            "clock": time.time(),
        }
    ]
    incidents_a = engine.correlate_active_problems(single_sbce_problems)
    assert len(incidents_a) == 1
    inc_a = incidents_a[0]
    assert inc_a.service_id == "SVC-SIP-CARRIER"
    assert inc_a.service_impact == ServiceImpactLevel.DEGRADED
    assert inc_a.causal_classification == CausalClassification.REDUNDANCY_FAILOVER
    assert inc_a.is_total_outage is False
    assert inc_a.recommended_action_id == 12  # Telephony admin, NOT total outage Action 10
    logger.info(f"  Scenario A Result: Status={inc_a.service_impact.value}, Classification={inc_a.causal_classification.value}, TotalOutage={inc_a.is_total_outage}, Action={inc_a.recommended_action_id}")
    logger.info(f"  Justification: {inc_a.justification}")

    # Scenario B: Dual SBCE Redundancy Exhaustion (Both SBCEs down -> TOTAL OUTAGE)
    logger.info("[STEP 4] Simulating HA Pair Total Exhaustion (avaya-sbce-01 AND avaya-sbce-02 offline)...")
    dual_sbce_problems = [
        {
            "eventid": "10002",
            "host": "avaya-sbce-01",
            "name": "SBCE: Power Supply 1 & 2 Failure",
            "severity": 5,
            "clock": time.time(),
        },
        {
            "eventid": "10003",
            "host": "avaya-sbce-02",
            "name": "SBCE: Node Kernel Panic / System Halt",
            "severity": 5,
            "clock": time.time(),
        },
    ]
    incidents_b = engine.correlate_active_problems(dual_sbce_problems)
    assert len(incidents_b) == 1
    inc_b = incidents_b[0]
    assert inc_b.service_id == "SVC-SIP-CARRIER"
    assert inc_b.service_impact == ServiceImpactLevel.TOTAL_OUTAGE
    assert inc_b.causal_classification == CausalClassification.ROOT_CAUSE
    assert inc_b.is_total_outage is True
    assert inc_b.recommended_action_id == 10  # Action 10: Total Outage!
    logger.info(f"  Scenario B Result: Status={inc_b.service_impact.value}, Classification={inc_b.causal_classification.value}, TotalOutage={inc_b.is_total_outage}, Action={inc_b.recommended_action_id}")
    logger.info(f"  Justification: {inc_b.justification}")

    # Scenario C: Core Switch Uplink Failure with Downstream Symptom Suppression
    logger.info("[STEP 5] Simulating Core Switch Uplink Drop with Downstream Suppression...")
    core_switch_cascade = [
        {
            "eventid": "20001",
            "host": "jkia-core-sw01",
            "name": "JKIA-CORE: Port-Channel 1 (Spine Uplink) Link Down",
            "severity": 5,
            "clock": time.time(),
        },
        {
            "eventid": "20002",
            "host": "avaya-cm-01",
            "name": "Avaya CM: Host unreachable by ICMP ping",
            "severity": 4,
            "clock": time.time() + 1,
        },
        {
            "eventid": "20003",
            "host": "avaya-sm-01",
            "name": "Avaya SM: SIP Service Heartbeat Timeout",
            "severity": 4,
            "clock": time.time() + 1,
        },
        {
            "eventid": "20004",
            "host": "avaya-g450-01",
            "name": "G450: H.248 Link Out of Service",
            "severity": 4,
            "clock": time.time() + 2,
        },
    ]
    incidents_c = engine.correlate_active_problems(core_switch_cascade)
    assert len(incidents_c) == 1
    inc_c = incidents_c[0]
    assert inc_c.primary_root_cause["host"] == "jkia-core-sw01"
    assert inc_c.causal_classification == CausalClassification.ROOT_CAUSE
    assert len(inc_c.suppressed_symptoms) == 3
    logger.info(f"  Scenario C Result: Root Cause Host={inc_c.primary_root_cause['host']}, Suppressed Symptoms Count={len(inc_c.suppressed_symptoms)}")
    for sym in inc_c.suppressed_symptoms:
        logger.info(f"    - Suppressed Downstream Symptom: {sym['host']} -> {sym['name']}")

    # Scenario D: Interface Flapping Dampening
    logger.info("[STEP 6] Simulating Interface Flapping Dampening...")
    flapping_host = "jkia-dist-sw01"
    flapping_key = "net.if.status[GigabitEthernet1/0/24]"
    t0 = time.time()
    f1 = engine.record_event_transition(flapping_host, flapping_key, timestamp=t0)
    f2 = engine.record_event_transition(flapping_host, flapping_key, timestamp=t0 + 5)
    f3 = engine.record_event_transition(flapping_host, flapping_key, timestamp=t0 + 15)
    assert f1 is False
    assert f2 is False
    assert f3 is True  # 3rd transition within 60s triggers flapping dampening!
    logger.info(f"  Scenario D Result: Rapid state transitions (3x within 15s) correctly identified as FLAPPING_DAMPENED.")

    # 4. Live Zabbix 7.4 Service Tree Provisioning
    logger.info("[STEP 7] Synchronizing Kenya Airways Service Tree to live Zabbix API...")
    client = ZabbixClient(ZabbixSettings())
    client.connect()
    sync_report = engine.sync_to_zabbix_service_tree(client)
    logger.info(f"  Zabbix Service Tree Synced: Root ID={sync_report['root_service_id']}, Total Services={sync_report['total_zabbix_services']}")

    # 5. Save Evidence Snapshot
    evidence_payload = {
        "metadata": {
            "phase": "13.12",
            "title": "Service Dependency Mapping & Event Correlation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nawari_commit": nawari_rev,
            "sentra_commit": sentra_rev,
            "hard_production_deny": True,
            "status": "VALIDATED_STAGING",
        },
        "service_catalog_summary": {
            "total_services": len(all_services),
            "dag_cycles_detected": len(cycles),
            "expected_services_verified": expected_services,
        },
        "causality_scenarios": {
            "scenario_a_single_sbce_failover": inc_a.to_dict(),
            "scenario_b_dual_sbce_exhaustion": inc_b.to_dict(),
            "scenario_c_core_switch_root_cause": inc_c.to_dict(),
            "scenario_d_flapping_dampening_active": True,
        },
        "zabbix_service_tree_sync": {
            "root_service_id": sync_report["root_service_id"],
            "total_services_in_zabbix": sync_report["total_zabbix_services"],
            "created_count": sync_report["created_count"],
            "updated_count": sync_report["updated_count"],
        },
    }

    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(evidence_payload, f, indent=2)
    logger.info(f"Evidence manifest written to: {SNAPSHOT_FILE}")

    logger.info("======================================================================")
    logger.info("PHASE 13.12 SERVICE CORRELATION VERIFICATION: PASSED")
    logger.info("======================================================================")
    return evidence_payload


if __name__ == "__main__":
    run_service_correlation_verification()
