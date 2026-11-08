"""scripts/test_phase13_13_slo_engine.py
======================================
Executable verification script for Phase 13.13:
SLI, SLO & Error-Budget Implementation.

Validates:
1. Formalized SLO specifications across 7 Kenya Airways telecommunications services.
2. Multi-dimensional SLI measurement (Availability, Performance, Quality, Coverage).
3. Telemetry Integrity guard (missing data penalizes availability and flags coverage deficit).
4. Google SRE Multi-Window Multi-Burn-Rate alerting (14.4x Critical Page vs 6.0x Warning Ticket).
5. Error budget consumption and time-to-exhaustion forecasting.
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

from services.assurance.slo_burn_rate_engine import (
    BurnRateAlertLevel,
    SloBurnRateEngine,
)
from services.multisite.service_catalog import (
    SLIEvaluationEngine,
    SLOSpecification,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("phase13_13_slo_engine")

SNAPSHOT_FILE = PROJECT_ROOT / "provisioning/zabbix/snapshots/phase13_13_slo_evidence.json"


def run_slo_verification() -> Dict[str, Any]:
    logger.info("======================================================================")
    logger.info("NAWARI PHASE 13.13 — SLI, SLO & ERROR-BUDGET IMPLEMENTATION")
    logger.info("======================================================================")

    # 1. Environment & Baseline Safety Check
    logger.info("[STEP 1] Auditing repository safety and environment baselines...")
    nawari_rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sentra_rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd="/Users/madeira/Desktop/Projects/sentra", capture_output=True, text=True, check=True).stdout.strip()
    assert sentra_rev == "9970404", f"Sentra repository modified! HEAD: {sentra_rev}"
    logger.info(f"  Nawari HEAD: {nawari_rev}")
    logger.info(f"  Sentra HEAD: {sentra_rev} (Clean & Untouched)")

    # 2. Authoritative SLO Register
    logger.info("[STEP 2] Auditing authoritative Kenya Airways SLO register...")
    engine = SloBurnRateEngine()
    slos = engine.AUTHORITATIVE_SLOS
    assert len(slos) == 7
    for sid, s in slos.items():
        logger.info(f"    - {sid}: SLO={s['slo']}%, SLA={s['sla']}%, 30d Budget={s['allowed_downtime_minutes_30d']} min ({s['name']})")

    # 3. Multi-Dimensional SLI Engine Baseline Evaluation
    logger.info("[STEP 3] Validating Multi-Dimensional SLI engine (Availability, Performance, Quality, Coverage)...")
    sli_evaluator = SLIEvaluationEngine()
    for sid, s in slos.items():
        sli_evaluator.register_slo(SLOSpecification(
            service_id=sid,
            target_slo_percent=s["slo"],
            contractual_sla_percent=s["sla"],
            measurement_window_days=30,
        ))

    # Record 1000 operational minutes of pristine operations for SIP Carrier
    sli_evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=1000.0, health_index=1.0, is_available=True, is_performance_met=True)
    res_pristine = sli_evaluator.evaluate_sli("SVC-SIP-CARRIER")
    assert res_pristine.availability_sli == 100.0
    assert res_pristine.performance_sli == 100.0
    assert res_pristine.quality_sli == 100.0
    assert res_pristine.coverage_percent == 100.0
    assert res_pristine.is_slo_breached is False
    logger.info(f"  Pristine SLI Baseline: Availability={res_pristine.availability_sli}%, Coverage={res_pristine.coverage_percent}%, Budget Remaining={res_pristine.remaining_error_budget_minutes:.2f}m")

    # 4. Telemetry Integrity & Missing Telemetry Safeguard
    logger.info("[STEP 4] Validating Telemetry Integrity & Coverage Deficit guard...")
    sli_evaluator.record_interval("SVC-SIP-CARRIER", duration_minutes=300.0, health_index=0.0, is_available=False, is_unknown=True)
    res_with_missing = sli_evaluator.evaluate_sli("SVC-SIP-CARRIER")
    # Coverage must drop and missing telemetry must NOT inflate availability
    assert res_with_missing.coverage_percent < 100.0
    assert res_with_missing.availability_sli < 100.0
    assert res_with_missing.unknown_minutes == 300.0
    logger.info(f"  Missing Telemetry Guard Verified: Coverage dropped to {res_with_missing.coverage_percent:.1f}%, Unknown Minutes={res_with_missing.unknown_minutes}m, Availability clamped to {res_with_missing.availability_sli:.2f}%")

    # 5. Multi-Window Multi-Burn-Rate Alerting
    logger.info("[STEP 5] Validating Google SRE Multi-Window Multi-Burn-Rate alerting...")
    burn_engine = SloBurnRateEngine(sli_engine=sli_evaluator)

    # Scenario A: Critical Page (14.4x burn rate in 1h window)
    # For SVC-SIP-CARRIER (SLO 99.99%, allowed 4.32 min/mo):
    # 2% of budget = 0.0864 min. If outage is 1.0 min in 1h: error_rate = 1/60 = 0.01667; unreliability = 0.0001 -> burn_rate = 166.7x!
    alerts_crit = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-SIP-CARRIER",
        recent_1h_outage_minutes=1.0,
        recent_6h_outage_minutes=1.0,
    )
    assert len(alerts_crit) == 1
    alert_c = alerts_crit[0]
    assert alert_c.alert_level == BurnRateAlertLevel.CRITICAL_PAGE
    assert alert_c.burn_rate >= 14.4
    assert alert_c.recommended_action_id in (10, 12)
    logger.info(f"  Scenario A (1h / 14.4x Burn): Level={alert_c.alert_level.value}, BurnRate={alert_c.burn_rate:.1f}x, TTX={alert_c.time_to_exhaustion_hours:.1f}h")
    logger.info(f"  Justification: {alert_c.justification}")

    # Scenario B: Warning Ticket (6.0x burn rate in 6h window)
    # For SVC-IVR-SELFSERVICE (SLO 99.80%, allowed 86.4 min/mo):
    # 5% of budget = 4.32 min. If outage is 5.0 min over 6h: error_rate = 5/360 = 0.01389; unreliability = 0.002 -> burn_rate = 6.94x.
    sli_evaluator.record_interval("SVC-IVR-SELFSERVICE", duration_minutes=1000.0, health_index=1.0, is_available=True)
    alerts_warn = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-IVR-SELFSERVICE",
        recent_1h_outage_minutes=0.0,  # 1h is quiet
        recent_6h_outage_minutes=5.0,  # 6h accumulated 5 min outage
    )
    assert len(alerts_warn) == 1
    alert_w = alerts_warn[0]
    assert alert_w.alert_level == BurnRateAlertLevel.WARNING_TICKET
    assert alert_w.burn_rate >= 6.0
    assert alert_w.recommended_action_id == 13
    logger.info(f"  Scenario B (6h / 6.0x Burn): Level={alert_w.alert_level.value}, BurnRate={alert_w.burn_rate:.1f}x, TTX={alert_w.time_to_exhaustion_hours:.1f}h")
    logger.info(f"  Justification: {alert_w.justification}")

    # Scenario C: Nominal operation (Zero burn)
    alerts_nom = burn_engine.evaluate_burn_rate_alerts(
        service_id="SVC-IVR-SELFSERVICE",
        recent_1h_outage_minutes=0.0,
        recent_6h_outage_minutes=0.0,
    )
    assert len(alerts_nom) == 0
    logger.info("  Scenario C (Nominal): 0 burn rate alerts triggered; operations within budget.")

    # 6. Save Evidence Snapshot
    evidence_payload = {
        "metadata": {
            "phase": "13.13",
            "title": "SLI, SLO & Error-Budget Implementation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nawari_commit": nawari_rev,
            "sentra_commit": sentra_rev,
            "hard_production_deny": True,
            "status": "VALIDATED_STAGING",
        },
        "authoritative_slos": slos,
        "sli_pristine_sample": res_pristine.to_dict(),
        "sli_missing_telemetry_sample": res_with_missing.to_dict(),
        "burn_rate_scenarios": {
            "critical_14_4x_page": alert_c.to_dict(),
            "warning_6_0x_ticket": alert_w.to_dict(),
            "nominal_quiescent": True,
        },
    }

    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(evidence_payload, f, indent=2)
    logger.info(f"Evidence manifest written to: {SNAPSHOT_FILE}")

    logger.info("======================================================================")
    logger.info("PHASE 13.13 SLI/SLO VERIFICATION: PASSED")
    logger.info("======================================================================")
    return evidence_payload


if __name__ == "__main__":
    run_slo_verification()

