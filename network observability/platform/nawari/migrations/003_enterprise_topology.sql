CREATE TABLE IF NOT EXISTS source_references (
    tenant TEXT NOT NULL, source TEXT NOT NULL, source_object_id TEXT NOT NULL,
    source_schema_version TEXT NOT NULL, source_url TEXT,
    observed_at DOUBLE PRECISION NOT NULL, received_at DOUBLE PRECISION NOT NULL,
    freshness_state TEXT NOT NULL, collection_outcome TEXT NOT NULL,
    payload_hash TEXT NOT NULL, metadata TEXT NOT NULL,
    PRIMARY KEY (tenant, source, source_object_id, observed_at)
);
CREATE INDEX IF NOT EXISTS source_references_freshness
    ON source_references(tenant, source, freshness_state, observed_at);

CREATE TABLE IF NOT EXISTS topology_entities (
    tenant TEXT NOT NULL, entity_id TEXT NOT NULL, entity_kind TEXT NOT NULL,
    authoritative_source TEXT NOT NULL, authoritative_id TEXT NOT NULL,
    site_id TEXT NOT NULL, routing_domain_id TEXT NOT NULL, attributes TEXT NOT NULL,
    PRIMARY KEY (tenant, entity_id),
    UNIQUE (tenant, authoritative_source, authoritative_id)
);

CREATE TABLE IF NOT EXISTS topology_relationships (
    tenant TEXT NOT NULL, relationship_id TEXT NOT NULL,
    subject_id TEXT NOT NULL, predicate TEXT NOT NULL, object_id TEXT NOT NULL,
    relationship_class TEXT NOT NULL CHECK (relationship_class IN
      ('measured_l3_path','discovered_l2_topology','controller_association','configured_dependency','inferred_relationship')),
    provenance_source TEXT NOT NULL, provenance_object_id TEXT NOT NULL,
    valid_from DOUBLE PRECISION NOT NULL, valid_until DOUBLE PRECISION NOT NULL,
    first_observed DOUBLE PRECISION NOT NULL, last_observed DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    attributes TEXT NOT NULL,
    PRIMARY KEY (tenant, relationship_id),
    FOREIGN KEY (tenant, subject_id) REFERENCES topology_entities(tenant, entity_id),
    FOREIGN KEY (tenant, object_id) REFERENCES topology_entities(tenant, entity_id),
    CHECK (valid_until > valid_from),
    CHECK (last_observed >= first_observed)
);
CREATE INDEX IF NOT EXISTS topology_relationships_time
    ON topology_relationships(tenant, subject_id, valid_from, valid_until);

CREATE TABLE IF NOT EXISTS integration_cursors (
    tenant TEXT NOT NULL, source TEXT NOT NULL, stream_id TEXT NOT NULL,
    cursor_value TEXT NOT NULL, overlap_seconds INTEGER NOT NULL,
    schema_version TEXT NOT NULL, query_version TEXT NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tenant, source, stream_id)
);

CREATE TABLE IF NOT EXISTS audit_records (
    tenant TEXT NOT NULL, audit_id TEXT NOT NULL, actor_id TEXT NOT NULL,
    action TEXT NOT NULL, scope TEXT NOT NULL, outcome TEXT NOT NULL,
    occurred_at DOUBLE PRECISION NOT NULL, details TEXT NOT NULL,
    PRIMARY KEY (tenant, audit_id)
);
CREATE INDEX IF NOT EXISTS audit_records_time ON audit_records(tenant, occurred_at);

INSERT INTO schema_migrations(version) VALUES (3) ON CONFLICT (version) DO NOTHING;
