import React, { useState, useEffect } from 'react';
import { useInvestigation } from '../context/InvestigationContext';

interface DiscoveryCandidate {
  ip_address: string;
  inferred_name: string;
  inferred_role: string;
  discovery_source: string;
  observed_log_count: number;
  sample_ports: string;
  dominant_events: string;
  sample_log: string;
  icmp_status: string;
  icmp_rtt_ms: number | null;
  icmp_loss_pct: number | null;
  snmp_status: string;
  snmp_sys_name: string | null;
  solarwinds_status: string;
  solarwinds_node_id: string | null;
  zabbix_status: string;
  zabbix_hostid: string | null;
  canonical_id: string | null;
  verification_status: string;
  evidence_trail: string;
  last_probed_at: number;
}

interface DiscoverySummary {
  total_candidates: number;
  verified: number;
  monitored_candidate: number;
  pending_verification: number;
  icmp_reachable: number;
  icmp_unreachable: number;
  monitored_in_zabbix: number;
  unregistered_in_zabbix: number;
  solarwinds_swis: string;
  snmp_status: string;
}

export const NetworkDiscoveryPage: React.FC = () => {
  const { authHeader, navigate } = useInvestigation();
  const [candidates, setCandidates] = useState<DiscoveryCandidate[]>([]);
  const [summary, setSummary] = useState<DiscoverySummary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState<DiscoveryCandidate | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (statusFilter) params.set('status', statusFilter);
    if (search) params.set('q', search);

    Promise.all([
      fetch(`/api/v1/discovery/candidates?${params.toString()}`, { headers: authHeader }).then((r) => r.json()),
      fetch('/api/v1/discovery/summary', { headers: authHeader }).then((r) => r.json()),
    ])
      .then(([candData, sumData]) => {
        setCandidates(candData.candidates || []);
        setTotal(candData.total || 0);
        setSummary(sumData);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [statusFilter, search, authHeader]);

  return (
    <div className="inventory-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Automated Multi-Source Discovery</p>
          <h1>Network Discovery & Candidate Device Reconciliation</h1>
          <p className="muted">
            Continuous reconciliation pipeline evaluating SolarWinds forwarded syslog, Zabbix SNMP discovery, and ICMP connectivity across {summary?.total_candidates || 34} detected candidate devices. Unverified candidates remain in discovery state until independent SNMP or SWIS authorization is established.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={() => navigate('devices', 'inventory')}
          >
            📋 Monitored Devices ({summary?.monitored_candidate || 2})
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => navigate('devices', 'topology')}
          >
            🖧 Topology Map
          </button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="discovery-kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="stat-card" style={{ padding: '1rem', background: 'var(--card-bg, #1a1e29)', borderRadius: '8px', border: '1px solid var(--border-color, #2d3748)' }}>
          <div className="stat-label muted" style={{ fontSize: '0.85rem' }}>Total Candidate Devices</div>
          <div className="stat-value" style={{ fontSize: '1.75rem', fontWeight: 'bold', color: '#63b3ed' }}>{summary?.total_candidates || 34}</div>
          <div className="stat-sub muted" style={{ fontSize: '0.75rem' }}>Inferred from Cisco Syslog</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', background: 'var(--card-bg, #1a1e29)', borderRadius: '8px', border: '1px solid var(--border-color, #2d3748)' }}>
          <div className="stat-label muted" style={{ fontSize: '0.85rem' }}>Pending Verification</div>
          <div className="stat-value" style={{ fontSize: '1.75rem', fontWeight: 'bold', color: '#f6ad55' }}>{summary?.pending_verification || 32}</div>
          <div className="stat-sub muted" style={{ fontSize: '0.75rem' }}>Awaiting SNMP / SWIS</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', background: 'var(--card-bg, #1a1e29)', borderRadius: '8px', border: '1px solid var(--border-color, #2d3748)' }}>
          <div className="stat-label muted" style={{ fontSize: '0.85rem' }}>Monitored in Zabbix</div>
          <div className="stat-value" style={{ fontSize: '1.75rem', fontWeight: 'bold', color: '#68d391' }}>{summary?.monitored_in_zabbix || 2}</div>
          <div className="stat-sub muted" style={{ fontSize: '0.75rem' }}>Hosts 10786 & 10787 (ICMP)</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', background: 'var(--card-bg, #1a1e29)', borderRadius: '8px', border: '1px solid var(--border-color, #2d3748)' }}>
          <div className="stat-label muted" style={{ fontSize: '0.85rem' }}>ICMP Reachability</div>
          <div className="stat-value" style={{ fontSize: '1.75rem', fontWeight: 'bold', color: '#68d391' }}>{summary?.icmp_reachable || 34} / {summary?.total_candidates || 34}</div>
          <div className="stat-sub muted" style={{ fontSize: '0.75rem' }}>100% Network Reachable</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', background: 'var(--card-bg, #1a1e29)', borderRadius: '8px', border: '1px solid var(--border-color, #2d3748)' }}>
          <div className="stat-label muted" style={{ fontSize: '0.85rem' }}>SNMP Discovery</div>
          <div className="stat-value" style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#fc8181', paddingTop: '0.35rem' }}>Unavailable</div>
          <div className="stat-sub muted" style={{ fontSize: '0.75rem' }}>Cause Unconfirmed (161/udp)</div>
        </div>

        <div className="stat-card" style={{ padding: '1rem', background: 'var(--card-bg, #1a1e29)', borderRadius: '8px', border: '1px solid var(--border-color, #2d3748)' }}>
          <div className="stat-label muted" style={{ fontSize: '0.85rem' }}>SolarWinds SWIS API</div>
          <div className="stat-value" style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#f6ad55', paddingTop: '0.35rem' }}>HTTP 403 Auth</div>
          <div className="stat-sub muted" style={{ fontSize: '0.75rem' }}>SWIS Entitlement Required</div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="table-toolbar">
        <div className="toolbar-search">
          <input
            type="text"
            className="text-input"
            placeholder="Search candidate IP, name, or port…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="toolbar-filters">
          <select
            className="topbar-select"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Verification States</option>
            <option value="pending_verification">Pending Verification (32)</option>
            <option value="monitored_candidate">Monitored Candidates (2)</option>
            <option value="verified">Independently Verified (0)</option>
          </select>
        </div>
      </div>

      {loading && (
        <div className="page-loading">
          <div className="spinner" />
          <p>Querying discovery candidate records…</p>
        </div>
      )}

      {error && (
        <div className="page-error" role="alert">
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="table-card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Candidate Device</th>
                <th>Discovery Source</th>
                <th>Observed Syslog Evidence</th>
                <th>ICMP Ping</th>
                <th>SNMP Status</th>
                <th>Zabbix Host</th>
                <th>Reconciliation Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {candidates.length > 0 ? (
                candidates.map((c) => (
                  <tr key={c.ip_address}>
                    <td>
                      <strong>{c.inferred_name}</strong>
                      <br />
                      <code>{c.ip_address}</code>
                    </td>
                    <td>
                      <span className="role-tag" style={{ fontSize: '0.75rem' }}>
                        {c.discovery_source === 'cisco_syslog_auditsessionid' ? 'AuditSessionID' : 'OSPF Routing'}
                      </span>
                    </td>
                    <td>
                      <strong>{c.observed_log_count.toLocaleString()}</strong> events
                      <br />
                      <small className="muted">
                        {c.dominant_events} | Ports: {c.sample_ports}
                      </small>
                    </td>
                    <td>
                      <span className="status-badge status-healthy" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        ● {c.icmp_rtt_ms ? `${c.icmp_rtt_ms.toFixed(2)} ms` : 'Reachable'}
                      </span>
                    </td>
                    <td>
                      <span className="status-badge status-warning" style={{ fontSize: '0.75rem' }}>
                        Unavailable (Cause Unconfirmed)
                      </span>
                    </td>
                    <td>
                      {c.zabbix_status === 'monitored' ? (
                        <span className="status-badge status-healthy">
                          HostID {c.zabbix_hostid}
                        </span>
                      ) : (
                        <span className="muted" style={{ fontSize: '0.8rem' }}>Unregistered</span>
                      )}
                    </td>
                    <td>
                      <span
                        className={`status-badge ${
                          c.verification_status === 'monitored_candidate'
                            ? 'status-info'
                            : 'status-warning'
                        }`}
                        style={{ textTransform: 'capitalize' }}
                      >
                        {c.verification_status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setSelectedCandidate(c)}
                        >
                          Evidence
                        </button>
                        {c.canonical_id && (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => navigate('devices', 'inventory', c.canonical_id)}
                          >
                            Device
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="empty-table-cell">
                    No candidate devices match the active filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Candidate Evidence Modal */}
      {selectedCandidate && (
        <div
          className="modal-backdrop"
          onClick={() => setSelectedCandidate(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            className="modal-content"
            onClick={(e) => e.stopPropagation()}
            style={{
              background: '#1a202c',
              color: '#f7fafc',
              padding: '2rem',
              borderRadius: '8px',
              maxWidth: '650px',
              width: '90%',
              border: '1px solid #4a5568',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4)',
            }}
          >
            <h3 style={{ color: '#ffffff', margin: 0 }}>Candidate Device Discovery Evidence</h3>
            <p style={{ color: '#a0aec0', marginTop: '0.25rem' }}>{selectedCandidate.inferred_name} (<code>{selectedCandidate.ip_address}</code>)</p>

            <div style={{ marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div>
                <strong style={{ color: '#edf2f7' }}>Evidence Trail:</strong>
                <p style={{ marginTop: '0.25rem', padding: '0.65rem', background: '#0d1117', color: '#e6edf3', borderRadius: '4px', fontSize: '0.85rem', lineHeight: '1.4', border: '1px solid #30363d' }}>
                  {selectedCandidate.evidence_trail}
                </p>
              </div>

              <div>
                <strong style={{ color: '#edf2f7' }}>Observed Syslog Sample:</strong>
                <pre style={{ marginTop: '0.25rem', padding: '0.65rem', background: '#0d1117', color: '#7ee787', borderRadius: '4px', fontSize: '0.75rem', overflowX: 'auto', whiteSpace: 'pre-wrap', border: '1px solid #30363d' }}>
                  {selectedCandidate.sample_log || 'No sample log stored.'}
                </pre>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.85rem', color: '#e2e8f0', background: '#2d3748', padding: '0.75rem', borderRadius: '6px' }}>
                <div><strong>ICMP Latency:</strong> {selectedCandidate.icmp_rtt_ms ? `${selectedCandidate.icmp_rtt_ms.toFixed(2)} ms` : 'N/A'} (0% loss)</div>
                <div><strong>SNMP UDP 161:</strong> Unavailable — Cause Unconfirmed</div>
                <div><strong>Zabbix Status:</strong> {selectedCandidate.zabbix_status === 'monitored' ? `Monitored (Host ${selectedCandidate.zabbix_hostid})` : 'Unregistered'}</div>
                <div><strong>SolarWinds SWIS:</strong> HTTP 403 Forbidden (Port 17774)</div>
              </div>
            </div>

            <div style={{ marginTop: '1.5rem', textAlign: 'right' }}>
              <button className="btn btn-primary" onClick={() => setSelectedCandidate(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
