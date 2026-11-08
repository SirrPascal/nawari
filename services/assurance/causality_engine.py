"""services/assurance/causality_engine.py
======================================
Cross-Domain Event Causality & Service Dependency Correlation Engine.

Implements Workstream 13E & Phase 13.12:
1. Multi-tier Service Dependency Graph (DAG) for Kenya Airways Telecommunications.
2. Root Cause Localization vs Downstream Symptom Suppression.
3. High-Availability (HA) Pair Redundancy Dampening:
   - Single SBCE / CM / Core Switch failure yields DEGRADED service (Actions 11-13).
   - Dual HA failure yields TOTAL_OUTAGE (Action 10).
4. Interface & Flapping Dampening.
5. Bidirectional synchronization with Zabbix 7.4 Service Tree (SLA calculation).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nawari.assurance.causality")


class CausalClassification(str, Enum):
    ROOT_CAUSE = "ROOT_CAUSE"
    DOWNSTREAM_SYMPTOM = "DOWNSTREAM_SYMPTOM"
    REDUNDANCY_FAILOVER = "REDUNDANCY_FAILOVER"
    FLAPPING_DAMPENED = "FLAPPING_DAMPENED"
    INDEPENDENT_EVENT = "INDEPENDENT_EVENT"


class ServiceImpactLevel(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    TOTAL_OUTAGE = "TOTAL_OUTAGE"


@dataclass
class CorrelatedIncident:
    """Represents a causality-correlated incident group with isolated root cause and suppressed symptoms."""
    incident_id: str
    primary_root_cause: Dict[str, Any]
    service_id: str
    service_name: str
    service_impact: ServiceImpactLevel
    causal_classification: CausalClassification
    suppressed_symptoms: List[Dict[str, Any]] = field(default_factory=list)
    is_total_outage: bool = False
    recommended_action_id: int = 12
    justification: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "primary_root_cause": self.primary_root_cause,
            "service_id": self.service_id,
            "service_name": self.service_name,
            "service_impact": self.service_impact.value,
            "causal_classification": self.causal_classification.value,
            "is_total_outage": self.is_total_outage,
            "recommended_action_id": self.recommended_action_id,
            "suppressed_symptoms_count": len(self.suppressed_symptoms),
            "suppressed_symptoms": self.suppressed_symptoms,
            "justification": self.justification,
            "timestamp": self.timestamp,
        }


class CausalityEngine:
    """Evaluates multi-source alarms against dependency graphs to isolate root causes and determine service impact."""

    # Redundancy pairs in Kenya Airways telephony infrastructure
    HA_PAIRS: Dict[str, Dict[str, Any]] = {
        "SBCE_HA_CLUSTER": {
            "members": {"avaya-sbce-01", "avaya-sbce-02"},
            "service_id": "SVC-SIP-CARRIER",
            "service_name": "Carrier Ingress & SIP Trunking",
        },
        "CM_DUPLEX": {
            "members": {"avaya-cm-01", "avaya-cm-02"},
            "service_id": "SVC-CORP-TELEPHONY",
            "service_name": "Corporate Telephony Core (Avaya Aura)",
        },
        "SM_DUPLEX": {
            "members": {"avaya-sm-01", "avaya-sm-02"},
            "service_id": "SVC-CORP-TELEPHONY",
            "service_name": "Corporate Telephony Core (Avaya Aura)",
        },
        "CORE_SWITCHES": {
            "members": {"jkia-core-sw01", "jkia-core-sw02"},
            "service_id": "SVC-ENTERPRISE-NETWORK",
            "service_name": "Kenya Airways Enterprise Network Core",
        },
        "WAN_CORE_CIRCUITS": {
            "members": {"CIR-MPLS-SAFARICOM-01", "CIR-MPLS-TELKOM-01"},
            "service_id": "SVC-WAN-CONNECTIVITY",
            "service_name": "WAN & Regional Outstation Connectivity",
        },
    }

    # Upstream -> Downstream topology mapping
    UPSTREAM_DEPENDENCIES: Dict[str, List[str]] = {
        "jkia-core-sw01": [
            "avaya-sbce-01", "avaya-cm-01", "avaya-sm-01", "avaya-g450-01", "avaya-cms-01"
        ],
        "jkia-core-sw02": [
            "avaya-sbce-02", "avaya-cm-02", "avaya-sm-02", "avaya-g450-02"
        ],
    }

    def __init__(self, flapping_window_seconds: float = 60.0, flapping_threshold_count: int = 3):
        self.flapping_window_seconds = flapping_window_seconds
        self.flapping_threshold_count = flapping_threshold_count
        self._event_history: List[Tuple[float, str, str]] = []  # (timestamp, host, trigger_key)

    def record_event_transition(self, host: str, key: str, timestamp: Optional[float] = None) -> bool:
        """Record an event transition and determine if the entity is flapping."""
        t = timestamp or time.time()
        self._event_history.append((t, host, key))
        # Filter to recent window
        recent = [
            ev for ev in self._event_history
            if ev[1] == host and ev[2] == key and (t - ev[0]) <= self.flapping_window_seconds
        ]
        return len(recent) >= self.flapping_threshold_count

    def correlate_active_problems(self, problems: List[Dict[str, Any]]) -> List[CorrelatedIncident]:
        """Correlate active Zabbix problems into grouped incidents with root causes and suppressed symptoms."""
        if not problems:
            return []

        correlated_incidents: List[CorrelatedIncident] = []
        handled_event_ids: Set[str] = set()

        # Group problems by host
        problems_by_host: Dict[str, List[Dict[str, Any]]] = {}
        for p in problems:
            h = p.get("host", p.get("hostname", "unknown"))
            problems_by_host.setdefault(h, []).append(p)

        # 1. Check for Core Switch / Upstream Infrastructure Outages
        for core_host, downstreams in self.UPSTREAM_DEPENDENCIES.items():
            core_probs = problems_by_host.get(core_host, [])
            critical_core_probs = [
                p for p in core_probs
                if int(p.get("severity", 0)) >= 4 or "down" in p.get("name", "").lower()
            ]

            if critical_core_probs:
                primary = critical_core_probs[0]
                handled_event_ids.add(str(primary.get("eventid", "")))

                # Collect downstream symptoms
                suppressed: List[Dict[str, Any]] = []
                for d_host in downstreams:
                    for d_prob in problems_by_host.get(d_host, []):
                        suppressed.append(d_prob)
                        handled_event_ids.add(str(d_prob.get("eventid", "")))

                incident = CorrelatedIncident(
                    incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                    primary_root_cause=primary,
                    service_id="SVC-ENTERPRISE-NETWORK",
                    service_name="Kenya Airways Enterprise Network Core",
                    service_impact=ServiceImpactLevel.DEGRADED if "01" in core_host else ServiceImpactLevel.DEGRADED,
                    causal_classification=CausalClassification.ROOT_CAUSE,
                    suppressed_symptoms=suppressed,
                    is_total_outage=False,
                    recommended_action_id=14,  # Network infra action
                    justification=f"Core switch '{core_host}' interface failure triggered downstream unreachable symptoms for {len(suppressed)} child hosts.",
                )
                correlated_incidents.append(incident)

        # 2. Check HA Pairs (Redundancy Evaluation)
        for group_name, group_cfg in self.HA_PAIRS.items():
            members: Set[str] = group_cfg["members"]
            failing_members: Set[str] = set()
            group_problems: List[Dict[str, Any]] = []

            for m in members:
                m_probs = [p for p in problems_by_host.get(m, []) if str(p.get("eventid")) not in handled_event_ids]
                if m_probs:
                    failing_members.add(m)
                    group_problems.extend(m_probs)

            if not failing_members:
                continue

            # Case A: Partial Member Failure (Single SBC or SM or CM down) -> REDUNDANCY DEGRADED
            if len(failing_members) < len(members):
                primary_prob = group_problems[0]
                handled_event_ids.update(str(p.get("eventid")) for p in group_problems)
                surviving = list(members - failing_members)[0]

                incident = CorrelatedIncident(
                    incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                    primary_root_cause=primary_prob,
                    service_id=group_cfg["service_id"],
                    service_name=group_cfg["service_name"],
                    service_impact=ServiceImpactLevel.DEGRADED,
                    causal_classification=CausalClassification.REDUNDANCY_FAILOVER,
                    suppressed_symptoms=group_problems[1:],
                    is_total_outage=False,
                    recommended_action_id=12,  # Action 12: Telephony Admins (NOT Action 10!)
                    justification=(
                        f"HA Pair '{group_name}' member '{list(failing_members)[0]}' offline. "
                        f"Traffic absorbed by active partner '{surviving}'. Service is DEGRADED, NOT a total outage."
                    ),
                )
                correlated_incidents.append(incident)

            # Case B: Exhaustion of Redundancy Group (Both members down!) -> TOTAL OUTAGE
            else:
                primary_prob = group_problems[0]
                handled_event_ids.update(str(p.get("eventid")) for p in group_problems)

                incident = CorrelatedIncident(
                    incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                    primary_root_cause=primary_prob,
                    service_id=group_cfg["service_id"],
                    service_name=group_cfg["service_name"],
                    service_impact=ServiceImpactLevel.TOTAL_OUTAGE,
                    causal_classification=CausalClassification.ROOT_CAUSE,
                    suppressed_symptoms=group_problems[1:],
                    is_total_outage=True,
                    recommended_action_id=10,  # Action 10: Total Outage!
                    justification=(
                        f"CRITICAL REDUNDANCY EXHAUSTION: All members of HA pair '{group_name}' "
                        f"({', '.join(members)}) are down! Immediate total service outage."
                    ),
                )
                correlated_incidents.append(incident)

        # 3. Handle Remaining Independent Problems
        for p in problems:
            eid = str(p.get("eventid"))
            if eid in handled_event_ids:
                continue

            host = p.get("host", p.get("hostname", "unknown"))
            is_flapping = self.record_event_transition(host, p.get("key_", p.get("name", "")))

            classification = CausalClassification.FLAPPING_DAMPENED if is_flapping else CausalClassification.INDEPENDENT_EVENT
            rec_action = 13  # Default warning/incident action

            incident = CorrelatedIncident(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                primary_root_cause=p,
                service_id="SVC-UNMAPPED",
                service_name=f"Independent Host Issue ({host})",
                service_impact=ServiceImpactLevel.DEGRADED if int(p.get("severity", 0)) >= 4 else ServiceImpactLevel.HEALTHY,
                causal_classification=classification,
                suppressed_symptoms=[],
                is_total_outage=False,
                recommended_action_id=rec_action,
                justification=f"Standalone event on host '{host}'. Flapping={is_flapping}.",
            )
            correlated_incidents.append(incident)
            handled_event_ids.add(eid)

        return correlated_incidents

    def sync_to_zabbix_service_tree(self, zabbix_client: Any) -> Dict[str, Any]:
        """Synchronize the 8 Kenya Airways services into the Zabbix 7.4 Service Tree."""
        # 1. Fetch existing services
        existing = zabbix_client.call("service.get", {"output": ["serviceid", "name"]})
        existing_by_name = {s["name"]: s["serviceid"] for s in existing}

        created_count = 0
        updated_count = 0

        # Root Service
        root_name = "Kenya Airways Telecommunications & Network Services"
        if root_name not in existing_by_name:
            res = zabbix_client.call("service.create", {
                "name": root_name,
                "algorithm": 1,  # Problem if at least one child has a problem
                "sortorder": 1,
                "weight": 100,
                "description": "Kenya Airways Enterprise Communications & Network Observability Root",
            })
            root_id = res["serviceids"][0]
            created_count += 1
        else:
            root_id = existing_by_name[root_name]

        # 8 Business Services to register under root
        services_to_sync = [
            {"name": "Kenya Airways Enterprise Network Core", "algo": 1, "weight": 90, "tag": "network"},
            {"name": "WAN & Regional Outstation Connectivity", "algo": 1, "weight": 85, "tag": "wan"},
            {"name": "Carrier Ingress & SIP Trunking", "algo": 2, "weight": 95, "tag": "sip"}, # algo 2 = problem if all children fail
            {"name": "Corporate Telephony Core (Avaya Aura)", "algo": 1, "weight": 90, "tag": "voice"},
            {"name": "Inbound Customer Contact Center (Elite ACD)", "algo": 1, "weight": 95, "tag": "contact_center"},
            {"name": "Outbound Contact Center & Automated Dialling", "algo": 1, "weight": 70, "tag": "outbound"},
            {"name": "Interactive Voice Response (Experience Portal)", "algo": 1, "weight": 80, "tag": "ivr"},
            {"name": "Call Recording & Compliance (Verint WFO / CMS)", "algo": 1, "weight": 80, "tag": "wfo"},
        ]

        for s_def in services_to_sync:
            name = s_def["name"]
            if name not in existing_by_name:
                zabbix_client.call("service.create", {
                    "name": name,
                    "algorithm": s_def["algo"],
                    "sortorder": 2,
                    "weight": s_def["weight"],
                    "parents": [{"serviceid": root_id}],
                    "problem_tags": [{"tag": "service", "operator": 0, "value": s_def["tag"]}],
                    "description": f"Kenya Airways SLA Service: {name}",
                })
                created_count += 1
            else:
                updated_count += 1

        # Re-fetch all
        all_services = zabbix_client.call("service.get", {"output": "extend", "selectParents": "extend"})

        return {
            "root_service_id": root_id,
            "created_count": created_count,
            "updated_count": updated_count,
            "total_zabbix_services": len(all_services),
            "services": all_services,
        }
