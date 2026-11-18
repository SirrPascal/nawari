import { EvidenceInspectorModal, EvidenceDetail } from '../components/EvidenceInspectorModal';
import React, { useEffect, useState } from 'react';
import { useInvestigation } from '../context/InvestigationContext';

interface SnapshotItem {
  snapshot_id: string;
  title: string;
  description: string;
  created_by: string;
  created_at: number;
  time_range_start: number;
  time_range_end: number;
}

export const DashboardsPage: React.FC = () => {
  const { authHeader, navigate } = useInvestigation();
  const [snapshots, setSnapshots] = useState<SnapshotItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<EvidenceDetail | null>(null);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const inspect = async (snapshot: SnapshotItem) => {
    setInspectionError(null);
    try {
      const response = await fetch(`/api/v1/snapshots/${encodeURIComponent(snapshot.snapshot_id)}`, { headers: authHeader });
      if (!response.ok) throw new Error(`Snapshot unavailable (${response.status})`);
      const record = await response.json();
      setSelected({ title: snapshot.title, metricName: 'Investigation snapshot', value: snapshot.snapshot_id,
        quality: 'retained snapshot', sourceSystem: 'Nawari operational metadata', measuredAt: snapshot.created_at,
        rawEvidence: record, evidenceCategory: 'observed' });
    } catch (error) { setInspectionError(error instanceof Error ? error.message : 'Snapshot unavailable'); }
  };

  const fetchSnapshots = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/snapshots', { headers: authHeader });
      if (res.ok) {
        const json = await res.json();
        setSnapshots(json.snapshots || []);
      }
    } catch (e) {
      console.error('Failed to fetch investigation snapshots', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSnapshots();
  }, [authHeader]);

  return (
    <div className="page-container">
      <header className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Dashboards & Investigation Snapshots</h1>
          <p className="page-subtitle">
            Executive operational summaries, cross-layer telemetry dashboards, and frozen forensic incident snapshots
          </p>
        </div>
        <button className="btn btn-secondary" onClick={fetchSnapshots} disabled={loading}>
          {loading ? 'Refreshing…' : '🔄 Refresh Dashboards'}
        </button>
      </header>

      {/* Built-in Dashboards Grid */}
      <section className="panel" style={{ marginBottom: '1.5rem' }}>
        <div className="panel-header">
          <h3>Network Infrastructure & Telemetry Dashboards (Grafana 11)</h3>
          <span className="badge badge-success">Live Zabbix & Loki Data Sources</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem', padding: '1rem 0' }}>
          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>🖧</div>
            <strong>Network Device Overview</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Fleet health, reachability (34/34 online), average latency, and active Zabbix trigger alerts.
            </p>
            <a className="btn btn-secondary" href="/grafana/d/nawari-net-overview/network-device-overview" target="_blank" rel="noreferrer">
              Open Device Overview ↗
            </a>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>📈</div>
            <strong>Device Availability & Loss</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Continuous ICMP response time (s), packet loss percentage (%), and 24-hour uptime state timeline.
            </p>
            <a className="btn btn-secondary" href="/grafana/d/nawari-net-avail/network-device-availability" target="_blank" rel="noreferrer">
              Open Availability Trends ↗
            </a>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>⚡</div>
            <strong>Network Interface Performance</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Genuine SNMP ingress/egress bps and discard counters. Unpolled candidates clearly marked N/A.
            </p>
            <a className="btn btn-secondary" href="/grafana/d/nawari-net-perf/network-interface-performance" target="_blank" rel="noreferrer">
              Open Performance Dashboard ↗
            </a>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>📜</div>
            <strong>SolarWinds Cisco Logs & Events</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Searchable Loki stream of forwarded Cisco syslog events, facility breakdown, and severity analytics.
            </p>
            <a className="btn btn-secondary" href="/grafana/d/nawari-sw-cisco-logs/solarwinds-cisco-logs-events" target="_blank" rel="noreferrer">
              Open Cisco Logs (Loki) ↗
            </a>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>🔍</div>
            <strong>Network Incident Investigation</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Cross-layer correlation aligning active Zabbix reachability alerts with matched Cisco syslog flappings.
            </p>
            <a className="btn btn-secondary" href="/grafana/d/nawari-net-incident/network-incident-investigation" target="_blank" rel="noreferrer">
              Open Incident Investigation ↗
            </a>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>🛡️</div>
            <strong>Monitoring Coverage & Retention</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Protocol coverage audit (ICMP, Syslog, SNMP, SWIS) and verified 120-hour FIFO log retention compliance.
            </p>
            <a className="btn btn-secondary" href="/grafana/d/nawari-net-coverage/monitoring-coverage-and-data-quality" target="_blank" rel="noreferrer">
              Open Coverage & Retention ↗
            </a>
          </div>
        </div>
      </section>

      {/* Built-in Dashboards Grid */}
      <section className="panel" style={{ marginBottom: '1.5rem' }}>
        <div className="panel-header">
          <h3>Built-in Observability Views</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem', padding: '1rem 0' }}>
          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>📊</div>
            <strong>Enterprise Health</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Review canonical inventory, source freshness, test coverage and active incidents.
            </p>
            <button className="btn btn-secondary" onClick={() => navigate("overview", "enterprise")}>Open Enterprise Health</button>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>💻</div>
            <strong>Endpoint & Connection Evidence</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Inspect endpoint connections, passive network context and available radio measurements.
            </p>
            <button className="btn btn-secondary" onClick={() => navigate("endpoints", "inventory")}>Open Endpoints</button>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>⚡</div>
            <strong>Observed Network Paths</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Inspect observed network hops and source-owned path measurements. Intermediate nonresponses do not establish transit packet loss.
            </p>
            <button className="btn btn-secondary" onClick={() => navigate("endpoints", "path")}>Open Network Paths</button>
          </div>

          <div style={{ padding: '1rem', border: '1px solid #e2e8f0', borderRadius: 6, background: '#f8fafc' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.25rem' }}>📞</div>
            <strong>Communications Evidence</strong>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0.5rem 0' }}>
              Inspect captured SIP signaling and available media-quality evidence. Missing source coverage remains visible.
            </p>
            <button className="btn btn-secondary" onClick={() => navigate("communications", "sip")}>Open Communications</button>
          </div>
        </div>
      </section>

      {/* Investigation Snapshots Table */}
      <section className="panel">
        <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>Preserved Investigation Snapshots</h3>
          <span className="muted">{snapshots.length} frozen states</span>
        </div>
        {snapshots.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
            <p>No investigation snapshots saved yet. Freeze any live path or incident investigation to create one.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Snapshot Title</th>
                <th>Author</th>
                <th>Observed Window</th>
                <th>Created At</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.snapshot_id}>
                  <td>
                    <strong>{s.title}</strong>
                    <div style={{ fontSize: '0.8rem', color: '#64748b' }}>{s.description}</div>
                  </td>
                  <td>{s.created_by}</td>
                  <td>
                    {new Date(s.time_range_start * 1000).toLocaleTimeString()} –{' '}
                    {new Date(s.time_range_end * 1000).toLocaleTimeString()}
                  </td>
                  <td>{new Date(s.created_at * 1000).toLocaleString()}</td>
                  <td>
                    <button onClick={() => void inspect(s)} className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}>
                      Inspect Frozen Evidence
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {inspectionError && <p role="alert">{inspectionError}</p>}
      <EvidenceInspectorModal isOpen={selected !== null} onClose={() => setSelected(null)} evidence={selected} />
    </div>
  );
};

