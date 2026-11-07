"""
Nawari Phase 8 — Configuration Management Database (CMDB) Adapter (Workstream 8E)
Enriches network and endpoint assets with enterprise location, criticality, and inventory data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional

from services.integrations.base_adapter import BaseEnterpriseAdapter, AdapterResult


@dataclass
class CMDBAsset:
    entity_id: str
    hostname: str
    ip_address: str
    site_id: str
    building: str
    rack_unit: str
    criticality: str
    asset_tag: str
    vendor: str
    model: str
    support_contract: str


class CMDBAdapter(BaseEnterpriseAdapter):
    def __init__(self):
        super().__init__(name="cmdb-adapter", failure_threshold=5, max_retries=2)
        # Default enterprise asset directory for Kenya Airways infrastructure
        self._assets: Dict[str, CMDBAsset] = {
            "10.2.1.58": CMDBAsset(
                entity_id="mon-grafana01",
                hostname="mon-grafana01.kenya-airways.com",
                ip_address="10.2.1.58",
                site_id="NBO-HQ",
                building="Pride Centre Data Centre",
                rack_unit="Rack-04-U12",
                criticality="TIER_1_MISSION_CRITICAL",
                asset_tag="KQ-SRV-9821",
                vendor="Canonical/Ubuntu",
                model="VMware VM 2vCPU 8GB",
                support_contract="ENT-SLA-24X7",
            ),
            "10.2.156.45": CMDBAsset(
                entity_id="sw-core01",
                hostname="sw-core01.kq.internal",
                ip_address="10.2.156.45",
                site_id="NBO-HQ",
                building="Pride Centre Data Centre",
                rack_unit="Rack-01-U01",
                criticality="TIER_1_MISSION_CRITICAL",
                asset_tag="KQ-NET-0101",
                vendor="Cisco Systems",
                model="Catalyst 9500-48Y4C",
                support_contract="CISCO-SMARTNET-24X7",
            ),
            "10.2.156.60": CMDBAsset(
                entity_id="sbce01",
                hostname="sbce01.kq.internal",
                ip_address="10.2.156.60",
                site_id="JKIA-T1A",
                building="Terminal 1A Tech Room",
                rack_unit="Rack-02-U10",
                criticality="TIER_1_MISSION_CRITICAL",
                asset_tag="KQ-VOICE-0052",
                vendor="Avaya",
                model="Session Border Controller Enterprise 8.1",
                support_contract="AVAYA-COE-PREMIUM",
            ),
        }

    def get_asset_metadata(self, entity_id_or_ip: str) -> AdapterResult:
        idempotency_key = f"cmdb-{entity_id_or_ip}"

        def _do_lookup() -> Dict[str, Any]:
            # Search by IP or entity_id
            for key, asset in self._assets.items():
                if entity_id_or_ip in (key, asset.entity_id, asset.hostname):
                    return asset.__dict__
            # Default fallback for unlisted corporate assets
            return {
                "entity_id": entity_id_or_ip,
                "hostname": entity_id_or_ip,
                "site_id": "KQ-GENERIC",
                "building": "General Corporate",
                "criticality": "TIER_3_OFFICE",
            }

        return self.execute_with_resilience("get_asset_metadata", _do_lookup, idempotency_key=idempotency_key)
