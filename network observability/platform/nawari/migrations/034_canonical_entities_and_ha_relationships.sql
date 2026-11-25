-- Migration 034: Canonical Entities, HA Clusters, Sites, and Evidence States

-- 1. High Availability (HA) Clusters (SBCE HA pairs, CM Duplex, Firewall clusters, Switch stacks)
CREATE TABLE IF NOT EXISTS canonical_ha_clusters (
    cluster_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cluster_type TEXT NOT NULL, -- sbce_ha_pair, cm_duplex_cluster, firewall_ha_pair, switch_stack
    vip_ip TEXT,
    primary_canonical_id TEXT REFERENCES canonical_devices(canonical_id),
    secondary_canonical_id TEXT REFERENCES canonical_devices(canonical_id),
    failover_mode TEXT NOT NULL DEFAULT 'active_standby', -- active_standby, active_active, duplex
    status TEXT NOT NULL DEFAULT 'healthy', -- healthy, degraded, split_brain, failed
    attributes_json TEXT DEFAULT '{}',
    observed_at DOUBLE PRECISION NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_canonical_ha_clusters_type ON canonical_ha_clusters(cluster_type);
CREATE INDEX IF NOT EXISTS idx_canonical_ha_clusters_vip ON canonical_ha_clusters(vip_ip);

-- 2. Device Site & Network Segment Association
CREATE TABLE IF NOT EXISTS canonical_device_sites (
    canonical_id TEXT NOT NULL REFERENCES canonical_devices(canonical_id),
    site_id TEXT NOT NULL,
    location_name TEXT,
    rack_unit TEXT,
    network_segment TEXT,
    valid_from DOUBLE PRECISION NOT NULL,
    valid_until DOUBLE PRECISION,
    PRIMARY KEY (canonical_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_device_sites_site ON canonical_device_sites(site_id);

-- 3. Canonical Entity Measurement States & Operational Health
CREATE TABLE IF NOT EXISTS canonical_entity_states (
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL, -- device, interface, cluster, service, trunk, ap
    measurement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    operational_health TEXT NOT NULL DEFAULT 'UNKNOWN',
    evidence_category TEXT NOT NULL DEFAULT 'observed',
    last_measured_at DOUBLE PRECISION,
    source_system TEXT NOT NULL,
    evidence_summary TEXT,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (entity_id, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_canonical_entity_states_meas ON canonical_entity_states(measurement_state);
CREATE INDEX IF NOT EXISTS idx_canonical_entity_states_health ON canonical_entity_states(operational_health);

INSERT INTO schema_migrations(version) VALUES (34) ON CONFLICT (version) DO NOTHING;
