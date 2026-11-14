CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS assets (
    tenant TEXT NOT NULL, asset_id TEXT NOT NULL, name TEXT NOT NULL,
    site_id TEXT NOT NULL, routing_domain_id TEXT NOT NULL,
    PRIMARY KEY (tenant, asset_id)
);
CREATE TABLE IF NOT EXISTS enrollments (
    tenant TEXT NOT NULL, enrollment_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    producer_id TEXT NOT NULL, observation_point_id TEXT NOT NULL,
    point_kind TEXT NOT NULL CHECK (point_kind IN ('endpoint','regional','infrastructure')),
    valid_from DOUBLE PRECISION NOT NULL, valid_until DOUBLE PRECISION NOT NULL,
    revoked_at DOUBLE PRECISION,
    PRIMARY KEY (tenant, enrollment_id)
);
CREATE TABLE IF NOT EXISTS identity_mappings (
    tenant TEXT NOT NULL, enrollment_id TEXT NOT NULL, asset_id TEXT NOT NULL,
    valid_from DOUBLE PRECISION NOT NULL, valid_until DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant, enrollment_id, valid_from),
    FOREIGN KEY (tenant, enrollment_id) REFERENCES enrollments(tenant, enrollment_id),
    FOREIGN KEY (tenant, asset_id) REFERENCES assets(tenant, asset_id)
);
CREATE TABLE IF NOT EXISTS operators (
    token_hash TEXT PRIMARY KEY, tenant TEXT NOT NULL, role TEXT NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL, revoked_at DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS operations (
    tenant TEXT NOT NULL, service_id TEXT NOT NULL, operation_id TEXT NOT NULL,
    definition TEXT NOT NULL,
    PRIMARY KEY (tenant, service_id, operation_id)
);
CREATE TABLE IF NOT EXISTS evidence (
    tenant TEXT NOT NULL, enrollment_id TEXT NOT NULL, producer_id TEXT NOT NULL,
    record_id TEXT NOT NULL, content_hash TEXT NOT NULL, payload_type TEXT NOT NULL,
    asset_id TEXT NOT NULL, service_id TEXT, observed_at DOUBLE PRECISION NOT NULL,
    received_at DOUBLE PRECISION NOT NULL, first_trusted_received_at DOUBLE PRECISION NOT NULL,
    timestamp_quality TEXT NOT NULL, retention_basis_at DOUBLE PRECISION NOT NULL,
    expires_at DOUBLE PRECISION NOT NULL, dedup_until DOUBLE PRECISION NOT NULL,
    body TEXT, state TEXT NOT NULL,
    PRIMARY KEY (tenant, enrollment_id, producer_id, record_id)
);
CREATE INDEX IF NOT EXISTS evidence_query ON evidence(tenant, asset_id, observed_at);
CREATE INDEX IF NOT EXISTS evidence_expiry ON evidence(expires_at);
CREATE TABLE IF NOT EXISTS outbox (
    tenant TEXT NOT NULL, enrollment_id TEXT NOT NULL, producer_id TEXT NOT NULL,
    record_id TEXT NOT NULL, destination TEXT NOT NULL, state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, next_attempt DOUBLE PRECISION NOT NULL,
    lease_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant, enrollment_id, producer_id, record_id),
    FOREIGN KEY (tenant, enrollment_id, producer_id, record_id)
        REFERENCES evidence(tenant, enrollment_id, producer_id, record_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS incidents (
    tenant TEXT NOT NULL, incident_id TEXT NOT NULL, asset_id TEXT NOT NULL,
    service_id TEXT NOT NULL, opened_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL, suspected_domain TEXT NOT NULL,
    state TEXT NOT NULL, revision INTEGER NOT NULL, evidence_until DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant, incident_id)
);
INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT (version) DO NOTHING;
