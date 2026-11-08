"""services/assurance/slo_burn_rate_engine.py
=========================================
Google SRE Multi-Window Multi-Burn-Rate Alerting & Error Budget Engine.

Implements Workstream 13F & Phase 13.13:
1. Formalized Service Level Objectives (SLOs) and Indicators (SLIs) for Kenya Airways services.
2. Multi-Window Multi-Burn-Rate alerting (1h/14.4x Critical Page, 6h/6.0x Warning Ticket).
3. Budget exhaustion forecasting (time-to-exhaustion in hours).
4. Telemetry Integrity: Missing or unconfirmed data triggers COVERAGE_DEFICIT, never false 100% uptime.
5. Replay isolation: Replayed telemetry strictly excluded from live SLO budget compliance.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from services.multisite.service_catalog import (
    MultiDimensionalSLIResult,
    SLIEvaluationEngine,
    SLOSpecification,
    TelemetryQuality,
)

logger = logging.getLogger("nawari.assurance.slo_burn_rate")


class BurnRateAlertLevel(str, Enum):
    NOMINAL = "NOMINAL"
    WARNING_TICKET = "WARNING_TICKET"
    CRITICAL_PAGE = "CRITICAL_PAGE"


@dataclass
class BurnRateAlert:
    """Represents an active multi-window burn rate alert."""
    service_id: str
    service_name: str
    alert_level: BurnRateAlertLevel
    burn_rate: float
    window_hours: float
    budget_consumed_pct: float
    time_to_exhaustion_hours: Optional[float]
    slo_target_pct: float
    current_sli_pct: float
    coverage_pct: float
    is_coverage_deficit: bool
    recommended_action_id: int
    justification: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "alert_level": self.alert_level.value,
            "burn_rate": round(self.burn_rate, 2),
            "window_hours": round(self.window_hours, 1),
            "budget_consumed_pct": round(self.budget_consumed_pct, 2),
            "time_to_exhaustion_hours": round(self.time_to_exhaustion_hours, 1) if self.time_to_exhaustion_hours else None,
            "slo_target_pct": self.slo_target_pct,
            "current_sli_pct": round(self.current_sli_pct, 4),
            "coverage_pct": round(self.coverage_pct, 2),
            "is_coverage_deficit": self.is_coverage_deficit,
            "recommended_action_id": self.recommended_action_id,
            "justification": self.justification,
            "timestamp": self.timestamp,
        }


class SloBurnRateEngine:
    """Evaluates multi-window error budget burn rates and fires calibrated SRE alerts."""

    # Authoritative Kenya Airways Service Level Objectives (30-day rolling window)
    AUTHORITATIVE_SLOS: Dict[str, Dict[str, Any]] = {
        "SVC-ENTERPRISE-NETWORK": {
            "name": "Kenya Airways Enterprise Network Core",
            "slo": 99.99,
            "sla": 99.95,
            "allowed_downtime_minutes_30d": 4.32,
        },
        "SVC-WAN-CONNECTIVITY": {
            "name": "WAN & Regional Outstation Connectivity",
            "slo": 99.95,
            "sla": 99.90,
            "allowed_downtime_minutes_30d": 21.60,
        },
        "SVC-SIP-CARRIER": {
            "name": "Carrier Ingress & SIP Trunking",
            "slo": 99.99,
            "sla": 99.95,
            "allowed_downtime_minutes_30d": 4.32,
        },
        "SVC-CORP-TELEPHONY": {
            "name": "Corporate Telephony Core (Avaya Aura)",
            "slo": 99.95,
            "sla": 99.90,
            "allowed_downtime_minutes_30d": 21.60,
        },
        "SVC-CONTACT-CENTER-INBOUND": {
            "name": "Inbound Customer Contact Center (Elite ACD)",
            "slo": 99.90,
            "sla": 99.80,
            "allowed_downtime_minutes_30d": 43.20,
        },
        "SVC-IVR-SELFSERVICE": {
            "name": "Interactive Voice Response (Experience Portal)",
            "slo": 99.80,
            "sla": 99.50,
            "allowed_downtime_minutes_30d": 86.40,
        },
        "SVC-MONITORING-PLATFORM": {
            "name": "Observability & Monitoring Platform (Nawari Core)",
            "slo": 99.95,
            "sla": 99.90,
            "allowed_downtime_minutes_30d": 21.60,
        },
    }

    def __init__(self, sli_engine: Optional[SLIEvaluationEngine] = None):
        self.sli_engine = sli_engine or SLIEvaluationEngine()
        self._init_slos()

    def _init_slos(self) -> None:
        """Register authoritative SLO specifications into underlying SLI engine."""
        for sid, meta in self.AUTHORITATIVE_SLOS.items():
            self.sli_engine.register_slo(SLOSpecification(
                service_id=sid,
                target_slo_percent=meta["slo"],
                contractual_sla_percent=meta["sla"],
                measurement_window_days=30,
            ))

    def evaluate_burn_rate_alerts(
        self,
        service_id: str,
        recent_1h_outage_minutes: float = 0.0,
        recent_6h_outage_minutes: float = 0.0,
    ) -> List[BurnRateAlert]:
        """Evaluate Google SRE multi-window burn rates for a service.
        
        Rules:
        - 14.4x Burn Rate in 1 hour consumes 2% of 30-day budget -> CRITICAL_PAGE (Action 10/12)
        - 6.0x Burn Rate in 6 hours consumes 5% of 30-day budget -> WARNING_TICKET (Action 13)
        """
        meta = self.AUTHORITATIVE_SLOS.get(service_id)
        if not meta:
            return []

        sli_result = self.sli_engine.evaluate_sli(service_id)
        total_budget_minutes = meta["allowed_downtime_minutes_30d"]
        unreliability = (100.0 - meta["slo"]) / 100.0
        alerts: List[BurnRateAlert] = []

        # Coverage Integrity Check: If coverage < 80%, flag coverage deficit
        is_coverage_deficit = sli_result.coverage_percent < 80.0

        # --- Window 1: 1-Hour Short Window (Critical Page) ---
        # 14.4x burn rate means consuming 2% of the budget in 1 hour
        window_1h_minutes = 60.0
        error_rate_1h = recent_1h_outage_minutes / window_1h_minutes
        burn_rate_1h = (error_rate_1h / unreliability) if unreliability > 0 else 0.0
        consumed_1h_pct = (recent_1h_outage_minutes / total_budget_minutes * 100.0) if total_budget_minutes > 0 else 0.0

        if burn_rate_1h >= 14.4 or (recent_1h_outage_minutes >= total_budget_minutes * 0.02):
            time_to_exhaustion = (total_budget_minutes - recent_1h_outage_minutes) / (recent_1h_outage_minutes / 1.0) if recent_1h_outage_minutes > 0 else 50.0
            alerts.append(BurnRateAlert(
                service_id=service_id,
                service_name=meta["name"],
                alert_level=BurnRateAlertLevel.CRITICAL_PAGE,
                burn_rate=burn_rate_1h,
                window_hours=1.0,
                budget_consumed_pct=consumed_1h_pct,
                time_to_exhaustion_hours=max(0.1, time_to_exhaustion),
                slo_target_pct=meta["slo"],
                current_sli_pct=sli_result.availability_sli,
                coverage_pct=sli_result.coverage_percent,
                is_coverage_deficit=is_coverage_deficit,
                recommended_action_id=10 if "CARRIER" in service_id or "NETWORK" in service_id else 12,
                justification=(
                    f"CRITICAL ERROR BUDGET BURN: Service '{meta['name']}' experiencing {burn_rate_1h:.1f}x burn rate "
                    f"in 1-hour window ({consumed_1h_pct:.1f}% budget consumed). Complete budget exhaustion in ~{time_to_exhaustion:.1f} hours."
                ),
            ))

        # --- Window 2: 6-Hour Medium Window (Warning Ticket) ---
        # 6.0x burn rate means consuming 5% of the budget in 6 hours
        window_6h_minutes = 360.0
        error_rate_6h = recent_6h_outage_minutes / window_6h_minutes
        burn_rate_6h = (error_rate_6h / unreliability) if unreliability > 0 else 0.0
        consumed_6h_pct = (recent_6h_outage_minutes / total_budget_minutes * 100.0) if total_budget_minutes > 0 else 0.0

        if (burn_rate_6h >= 6.0 or (recent_6h_outage_minutes >= total_budget_minutes * 0.05)) and not alerts:
            time_to_exhaustion = (total_budget_minutes - recent_6h_outage_minutes) / (recent_6h_outage_minutes / 6.0) if recent_6h_outage_minutes > 0 else 120.0
            alerts.append(BurnRateAlert(
                service_id=service_id,
                service_name=meta["name"],
                alert_level=BurnRateAlertLevel.WARNING_TICKET,
                burn_rate=burn_rate_6h,
                window_hours=6.0,
                budget_consumed_pct=consumed_6h_pct,
                time_to_exhaustion_hours=max(1.0, time_to_exhaustion),
                slo_target_pct=meta["slo"],
                current_sli_pct=sli_result.availability_sli,
                coverage_pct=sli_result.coverage_percent,
                is_coverage_deficit=is_coverage_deficit,
                recommended_action_id=13,  # Warning ticket
                justification=(
                    f"WARNING ERROR BUDGET BURN: Service '{meta['name']}' experiencing {burn_rate_6h:.1f}x burn rate "
                    f"in 6-hour window ({consumed_6h_pct:.1f}% budget consumed). Complete budget exhaustion in ~{time_to_exhaustion:.1f} hours."
                ),
            ))

        return alerts
