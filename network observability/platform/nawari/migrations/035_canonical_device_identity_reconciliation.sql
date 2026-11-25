-- Migration 035: Canonical Device Identity Reconciliation and SolarWinds/Zabbix Naming Alignment

-- 1. Canonical Device Identity Registry
CREATE TABLE IF NOT EXISTS canonical_device_identities (
    canonical_id TEXT PRIMARY KEY,
    solarwinds_node_id TEXT,
    zabbix_host_id TEXT,
    preferred_display_name TEXT NOT NULL,
    solarwinds_caption TEXT,
    zabbix_technical_host TEXT,
    zabbix_visible_name TEXT,
    dns_names TEXT DEFAULT '[]', -- JSON array of known DNS names
    management_ips TEXT DEFAULT '[]', -- JSON array of management and SVI IPs
    primary_ip TEXT,
    serial_number TEXT,
    snmp_sys_name TEXT,
    vendor TEXT,
    model TEXT,
    site TEXT,
    device_role TEXT,
    identity_confidence TEXT NOT NULL DEFAULT 'POSSIBLE_MATCH',
    -- EXACT_VERIFIED_MATCH, HIGH_CONFIDENCE_MATCH, POSSIBLE_MATCH, CONFLICTING_MATCH,
    -- SOLARWINDS_ONLY, ZABBIX_ONLY, DUPLICATE_CANDIDATE, MANUAL_REVIEW_REQUIRED
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    -- verified, candidate, conflicted, manual_review
    reconciliation_evidence TEXT,
    proposed_visible_name TEXT,
    rename_status TEXT DEFAULT 'pending', -- pending, approved, applied, rejected, rolled_back
    last_reconciled_at DOUBLE PRECISION NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_canonical_device_identities_sw_node ON canonical_device_identities(solarwinds_node_id);
CREATE INDEX IF NOT EXISTS idx_canonical_device_identities_zbx_host ON canonical_device_identities(zabbix_host_id);
CREATE INDEX IF NOT EXISTS idx_canonical_device_identities_primary_ip ON canonical_device_identities(primary_ip);
CREATE INDEX IF NOT EXISTS idx_canonical_device_identities_confidence ON canonical_device_identities(identity_confidence);
CREATE INDEX IF NOT EXISTS idx_canonical_device_identities_display ON canonical_device_identities(preferred_display_name);

-- 2. Audit Log for Reconciliation and Rollback
CREATE TABLE IF NOT EXISTS canonical_identity_audit_log (
    log_id SERIAL PRIMARY KEY,
    canonical_id TEXT NOT NULL,
    target_system TEXT NOT NULL, -- zabbix, grafana, nawari
    target_id TEXT NOT NULL, -- e.g. zabbix hostid
    attribute_name TEXT NOT NULL, -- e.g. visible_name
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT,
    applied_by TEXT NOT NULL DEFAULT 'nawari_reconciler',
    applied_at DOUBLE PRECISION NOT NULL,
    reverted_at DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_canonical_identity_audit_canonical ON canonical_identity_audit_log(canonical_id);
CREATE INDEX IF NOT EXISTS idx_canonical_identity_audit_target ON canonical_identity_audit_log(target_system, target_id);

INSERT INTO schema_migrations(version) VALUES (35) ON CONFLICT (version) DO NOTHING;
