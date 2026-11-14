CREATE TABLE IF NOT EXISTS netdata_nodes (
    tenant TEXT NOT NULL, asset_id TEXT NOT NULL, node_guid TEXT NOT NULL,
    node_name TEXT NOT NULL, agent_version TEXT NOT NULL, os_name TEXT NOT NULL,
    api_generation INTEGER NOT NULL, discovered_at DOUBLE PRECISION NOT NULL,
    last_seen DOUBLE PRECISION NOT NULL, status TEXT NOT NULL, capabilities TEXT NOT NULL,
    PRIMARY KEY (tenant, asset_id, node_guid),
    FOREIGN KEY (tenant, asset_id) REFERENCES assets(tenant, asset_id)
);
CREATE TABLE IF NOT EXISTS metric_catalogue (
    tenant TEXT NOT NULL, asset_id TEXT NOT NULL, node_guid TEXT NOT NULL,
    metric_id TEXT NOT NULL, context_id TEXT NOT NULL, chart_id TEXT NOT NULL,
    dimension_id TEXT NOT NULL, display_name TEXT NOT NULL, description TEXT NOT NULL,
    units TEXT NOT NULL, semantics TEXT NOT NULL, plugin TEXT NOT NULL, module TEXT NOT NULL,
    update_every INTEGER NOT NULL, first_seen DOUBLE PRECISION NOT NULL,
    last_observed DOUBLE PRECISION NOT NULL, collection_outcome TEXT NOT NULL,
    timestamp_quality TEXT NOT NULL, availability TEXT NOT NULL,
    retention_start DOUBLE PRECISION NOT NULL, retention_end DOUBLE PRECISION NOT NULL,
    source_api TEXT NOT NULL, section TEXT NOT NULL, catalogue_version TEXT NOT NULL,
    PRIMARY KEY (tenant, asset_id, metric_id),
    FOREIGN KEY (tenant, asset_id, node_guid) REFERENCES netdata_nodes(tenant, asset_id, node_guid)
);
CREATE INDEX IF NOT EXISTS metric_catalogue_search
    ON metric_catalogue(tenant, asset_id, section, availability, context_id);
INSERT INTO schema_migrations(version) VALUES (2) ON CONFLICT (version) DO NOTHING;
