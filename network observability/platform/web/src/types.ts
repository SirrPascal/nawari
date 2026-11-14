export type Hop = { node: string; kind: 'observed_l3' | 'discovered_l2' | 'inferred' };
export type Observation = {
  record_id: string; asset_id: string; service_id: string | null;
  observed_at: number; received_at: number; expires_at: number;
  freshness: string; state: string; timestamp_quality: string;
  record: {
    payload_type: string; collection_outcome: string; observation_point_id: string;
    execution_context?: string; config_version: string; operation_id?: string;
    payload: {
      test_result?: string; total_ms?: number; phases?: Record<string, {state: string; duration_ms: number | null}>;
      interface?: string; gateway?: string; vpn?: string; effective_from?: string; effective_until?: string;
      hops?: Hop[]; source_kind?: string; event_class?: string; [key: string]: unknown;
    };
  };
};
export type Investigation = {
  schema_version: string;
  mode: string; generated_at: number; partial: boolean; next_offset: number | null;
  assets: { asset_id: string; name: string; site_id: string; routing_domain_id: string }[];
  operations: { service_id: string; operation_id: string; name: string; objective_ms: number; interval_ms: number;
    description?: string; proves?: string; cannot_prove?: string; baseline_group?: string }[];
  observations: Observation[];
  incidents: { incident_id: string; asset_id: string; service_id: string; opened_at: number; suspected_domain: string; state: string; revision: number }[];
  hypotheses: { asset_id: string; classification: string; confidence: string; evidence: string[]; statement: string }[];
  sources: { enrollment_id: string; observation_point_id: string; point_kind: string; asset_id: string; coverage: string; last_observed_at: number | null }[];
  outbox: { state: string; count: number }[];
  metric_catalogue: { name: string; definition: string; unit: string; aggregation: string; source: string }[];
  integration_status: Record<string, string>;
};

export type Metric = {
  metric_id: string; context_id: string; chart_id: string; dimension_id: string;
  display_name: string; description: string; units: string; semantics: string;
  plugin: string; module: string; update_every: number; first_seen: number;
  last_observed: number; collection_outcome: string; timestamp_quality: string;
  availability: string; retention_start: number; retention_end: number;
  source_api: string; section: string; catalogue_version: string;
};
export type MetricCatalogue = {
  schema_version: string; asset_id: string; total: number; partial: boolean; next_offset: number | null;
  metrics: Metric[]; section_counts: {section: string; availability: string; count: number}[];
  node: null | {node_name: string; agent_version: string; os_name: string; last_seen: number; status: string;
    api_generation: number; capabilities: {catalogue?: {contexts: number; charts: number; dimensions: number};
      network_connections?: {registered: boolean; access: string; evidence: string}}};
};
export type MetricHistory = {
  metric: Metric; samples: {time: number; value: number | null}[]; sample_count: number;
  aggregation: string; after: number; before: number; retention_start: number; retention_end: number;
  source_api: string; partial: boolean;
};

export function time(value: number) {
  return new Date(value * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}
