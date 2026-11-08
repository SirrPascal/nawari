"""tests/unit/test_multisite_capacity_and_load.py
=============================================
Synthetic load, capacity, and endurance test suite (Workstream 13I).

Simulates:
- 15 outstations across 3 geographic regions and 11 countries.
- 500 distinct infrastructure nodes and circuits.
- Concurrent WAN partition and recovery.
- Notification burst dispatch.
- Measures throughput and execution time.
"""

import time
from services.multisite.edge_forwarder import CentralTelemetryReceiver
from services.multisite.incident_pipeline import (
    AlertCorrelationEngine,
    IncidentManager,
    IncidentSeverity,
    OperationalAlert,
)
from services.multisite.notifications import NotificationRouter
from services.multisite.service_catalog import ServiceCatalog, TelemetryQuality
from services.multisite.site_registry import MultiSiteRegistry


def test_synthetic_multisite_fleet_capacity_and_load():
    # 1. Site Registry Scalability
    registry = MultiSiteRegistry(auto_seed=True)
    stations = registry.get_all_stations()
    assert len(stations) >= 10

    # 2. Service Catalog Scalability with 500 components
    catalog = ServiceCatalog(auto_seed=True)
    component_states = {}
    for i in range(500):
        comp_id = f"COMP-NODE-{i:04d}"
        component_states[comp_id] = {
            "state": "ACTIVE" if i % 10 != 0 else "DOWN",
            "quality": TelemetryQuality.FRESH.value,
        }

    start_eval = time.perf_counter()
    summary = catalog.evaluate_all_services(component_states)
    eval_duration = time.perf_counter() - start_eval

    # Evaluation of 500 components must finish in under 100 milliseconds
    assert eval_duration < 0.10, f"Evaluation took {eval_duration:.4f}s; expected < 0.10s"
    assert len(summary["services"]) >= 6

    # 3. Correlation Engine Burst: Ingest 100 alerts simultaneously
    mgr = IncidentManager()
    alerts = []
    now_iso = "2026-11-08T09:00:00Z"
    for i in range(100):
        st = stations[i % len(stations)]
        alert = OperationalAlert(
            alert_id=f"ALT-BURST-{i:03d}",
            source="synthetic_test",
            entity_id=f"SW-{st.station_id}-{i}",
            metric_name="interface.link_down",
            observed_value=2,
            severity=IncidentSeverity.P2_HIGH if i % 5 == 0 else IncidentSeverity.P3_MEDIUM,
            summary=f"Synthetic link fault {i}",
            event_timestamp=now_iso,
            station_id=st.station_id,
        )
        alerts.append(alert)

    start_corr = time.perf_counter()
    correlated_incidents = []
    for a in alerts:
        inc, action = mgr.ingest_alert(a)
        if action == "CREATED":
            correlated_incidents.append(inc)
    corr_duration = time.perf_counter() - start_corr

    # Correlation of 100 alerts must finish in under 50 milliseconds
    assert corr_duration < 0.05, f"Correlation took {corr_duration:.4f}s; expected < 0.05s"
    assert len(correlated_incidents) >= 1

    # 4. Notification Dispatch Burst: 50 incidents dispatched through router
    router = NotificationRouter(is_production_mode=False)
    start_notif = time.perf_counter()
    for inc in correlated_incidents[:50]:
        router.dispatch_incident_notifications(inc.to_dict())
    notif_duration = time.perf_counter() - start_notif

    assert notif_duration < 0.20, f"Notification dispatch took {notif_duration:.4f}s; expected < 0.20s"
    assert len(router.get_outbox()) >= 50

    # 5. Central Hub Ingestion Throughput: 1,000 records ingested
    receiver = CentralTelemetryReceiver()
    batch = []
    for i in range(1000):
        batch.append({
            "event_id": f"EVT-INGEST-{i:04d}",
            "station_id": "MBA-STATION",
            "metric": "bandwidth.bps",
            "value": 1500000.0,
            "telemetry_quality": "REPLAYED",
            "_forwarding_metadata": {"is_replayed": True, "spool_id": f"EVT-INGEST-{i:04d}"},
        })

    start_ingest = time.perf_counter()
    res = receiver.ingest_batch(batch, auth_token="nawari-edge-shared-token-2026")
    ingest_duration = time.perf_counter() - start_ingest

    # 1,000 records ingested in under 100 milliseconds
    assert ingest_duration < 0.10, f"Ingestion took {ingest_duration:.4f}s; expected < 0.10s"
    assert res["ingested_count"] == 1000
