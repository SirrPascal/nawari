import React, { useState, useEffect } from 'react';
import { useInvestigation } from '../context/InvestigationContext';
import { NetworkDevice } from '../types';

export const DeviceInventoryPage: React.FC = () => {
  const { tenant, authHeader, navigate, triggerAiInvestigation } = useInvestigation();
  const [devices, setDevices] = useState<NetworkDevice[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [roleFilter, setRoleFilter] = useState('');
  const [healthFilter, setHealthFilter] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (roleFilter) params.set('role', roleFilter);
    if (healthFilter) params.set('health', healthFilter);
    if (search) params.set('q', search);

    fetch(`/api/v1/topology/devices?${params.toString()}`, { headers: authHeader })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Devices fetch failed (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setDevices(data.devices || []);
        setTotal(data.total || 0);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [tenant, roleFilter, healthFilter, search, authHeader]);

  return (
    <div className="inventory-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Infrastructure Inventory</p>
          <h1>Network Devices & Appliances</h1>
          <p className="muted">
            Monitored switches, routers, firewalls, and wireless access points synchronized via Zabbix SNMP and L2 discovery.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={() => navigate('devices', 'discovery')}
          >
            🔍 Discovery & Reconciliation (34 Candidates)
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => navigate('devices', 'topology')}
          >
            🖧 Topology Map
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="table-toolbar">
        <div className="toolbar-search">
          <input
            type="text"
            className="text-input"
            placeholder="Filter by device name or IP…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="toolbar-filters">
          <select
            className="topbar-select"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">All Roles</option>
            <option value="core_switch">Core Switches</option>
            <option value="access_switch">Access Switches</option>
            <option value="router">Routers / Gateways</option>
            <option value="firewall">Firewalls</option>
            <option value="wireless_ap">Wireless APs</option>
          </select>

          <select
            className="topbar-select"
            value={healthFilter}
            onChange={(e) => setHealthFilter(e.target.value)}
          >
            <option value="">All Health States</option>
            <option value="healthy">Healthy</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
            <option value="unreachable">Unreachable</option>
          </select>
        </div>
      </div>

      {loading && (
        <div className="page-loading">
          <div className="spinner" />
          <p>Querying network device inventory…</p>
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
                <th>Device Name</th>
                <th>Role</th>
                <th>Site</th>
                <th>Management IP</th>
                <th>Hardware / Vendor</th>
                <th>Health Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.length > 0 ? (
                devices.map((d) => (
                  <tr key={d.device_id}>
                    <td>
                      <button
                        className="link-button"
                        onClick={() => navigate('devices', 'inventory', d.device_id)}
                      >
                        <strong>{d.name}</strong>
                      </button>
                      <br />
                      <small className="muted">{d.device_id}</small>
                    </td>
                    <td>
                      <span className="role-tag">{d.device_role}</span>
                    </td>
                    <td>{d.site_id}</td>
                    <td>
                      <code>{d.management_ip || 'None'}</code>
                    </td>
                    <td>
                      {d.model ? `${d.vendor || 'Cisco'} ${d.model}` : (d.vendor ? `${d.vendor} · Candidate (Pending SWIS)` : 'Candidate (Pending SWIS)')}
                    </td>
                    <td>
                      <span className="status-badge status-healthy" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        ● Reachable (ICMP)
                      </span>
                      <br />
                      <small className="muted" style={{ fontSize: '0.72rem' }}>
                        {d.zabbix_hostid ? `Zabbix #${d.zabbix_hostid}` : 'Unmonitored'} · Syslog
                      </small>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => navigate('devices', 'inventory', d.device_id)}
                        >
                          Inspect
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => triggerAiInvestigation({ id: d.device_id, type: 'device' })}
                          title="Run AI Root Cause Diagnosis"
                        >
                          ✨ AI Audit
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="empty-table-cell">
                    No devices match the active filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="table-pagination">
            <span>Showing {devices.length} of {total} devices</span>
          </div>
        </div>
      )}
    </div>
  );
};

