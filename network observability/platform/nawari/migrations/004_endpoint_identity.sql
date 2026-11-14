-- 004_endpoint_identity.sql
-- Enterprise Endpoint & Infrastructure Identity Registry
-- Establishes canonical endpoint identity independent of volatile hostnames or IPs.

CREATE TABLE IF NOT EXISTS endpoint_registry (
    tenant TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    primary_hostname TEXT NOT NULL,
    serial_number TEXT,
    chassis_uuid TEXT,
    mac_address TEXT,
    device_kind TEXT NOT NULL CHECK (device_kind IN ('laptop','workstation','server','mobile','appliance','synthetic_probe','unknown')),
    os_family TEXT NOT NULL,
    os_version TEXT NOT NULL,
    site_id TEXT NOT NULL,
    routing_domain_id TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('enrolled','active','stale','quarantined','retired')),
    trust_level TEXT NOT NULL CHECK (trust_level IN ('trusted_enrollment','authorized_inventory','authenticated_collector','unverified_telemetry')),
    authoritative_source TEXT NOT NULL CHECK (authoritative_source IN ('nawari_agent','intune','solarwinds','zabbix','manual_inventory','telemetry_observed')),
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    last_seen_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant, endpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_endpoint_registry_search 
    ON endpoint_registry(tenant, lifecycle_state, site_id, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_endpoint_registry_hostname 
    ON endpoint_registry(tenant, primary_hostname);
CREATE INDEX IF NOT EXISTS idx_endpoint_registry_serial 
    ON endpoint_registry(tenant, serial_number);

CREATE TABLE IF NOT EXISTS endpoint_source_mappings (
    tenant TEXT NOT NULL,
    mapping_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    source_system TEXT NOT NULL CHECK (source_system IN ('netdata_guid','zabbix_hostid','nawari_agent_id','intune_device_id','solarwinds_nodeid')),
    source_identifier TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 1,
    trust_level TEXT NOT NULL CHECK (trust_level IN ('trusted_enrollment','authorized_inventory','authenticated_collector','unverified_telemetry')),
    discovered_at DOUBLE PRECISION NOT NULL,
    last_verified_at DOUBLE PRECISION NOT NULL,
    valid_from DOUBLE PRECISION NOT NULL,
    valid_until DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant, mapping_id),
    FOREIGN KEY (tenant, endpoint_id) REFERENCES endpoint_registry(tenant, endpoint_id) ON DELETE CASCADE,
    UNIQUE (tenant, source_system, source_identifier, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_endpoint_mappings_lookup
    ON endpoint_source_mappings(tenant, source_system, source_identifier, valid_until);

CREATE TABLE IF NOT EXISTS endpoint_network_observations (
    tenant TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    interface_name TEXT NOT NULL,
    interface_type TEXT NOT NULL CHECK (interface_type IN ('ETHERNET','WIFI','VPN','LOOPBACK','CELLULAR','OTHER')),
    mac_address TEXT,
    ip_address TEXT NOT NULL,
    subnet_mask TEXT,
    gateway_ip TEXT,
    ssid TEXT,
    bssid TEXT,
    observed_at DOUBLE PRECISION NOT NULL,
    valid_until DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (tenant, observation_id),
    FOREIGN KEY (tenant, endpoint_id) REFERENCES endpoint_registry(tenant, endpoint_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_endpoint_network_obs
    ON endpoint_network_observations(tenant, endpoint_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_endpoint_network_ip
    ON endpoint_network_observations(tenant, ip_address, observed_at);

CREATE TABLE IF NOT EXISTS endpoint_hostname_history (
    tenant TEXT NOT NULL,
    history_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    hostname TEXT NOT NULL,
    first_seen_at DOUBLE PRECISION NOT NULL,
    last_seen_at DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (tenant, history_id),
    FOREIGN KEY (tenant, endpoint_id) REFERENCES endpoint_registry(tenant, endpoint_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_endpoint_hostname_hist
    ON endpoint_hostname_history(tenant, endpoint_id, hostname);

CREATE TABLE IF NOT EXISTS endpoint_identity_conflicts (
    tenant TEXT NOT NULL,
    conflict_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    conflicting_identifier TEXT NOT NULL,
    claimed_endpoint_id TEXT,
    existing_endpoint_id TEXT,
    conflict_reason TEXT NOT NULL CHECK (conflict_reason IN ('duplicate_machine_guid','mac_address_conflict','hostname_clash_different_hw','unauthorized_reassignment','untrusted_reclaim','spoofed_serial_claim','retired_asset_reappearance')),
    detected_at DOUBLE PRECISION NOT NULL,
    resolved_at DOUBLE PRECISION,
    resolution_action TEXT,
    details TEXT NOT NULL,
    PRIMARY KEY (tenant, conflict_id)
);

CREATE INDEX IF NOT EXISTS idx_endpoint_conflicts
    ON endpoint_identity_conflicts(tenant, source_system, conflicting_identifier);

INSERT INTO schema_migrations(version) VALUES (4) ON CONFLICT (version) DO NOTHING;
