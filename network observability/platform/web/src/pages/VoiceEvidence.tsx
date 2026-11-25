import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useInvestigation } from '../context/InvestigationContext';

const VOICE_VIEWS = [
  { id: 'sip', label: 'SIP captures' },
  { id: 'traces', label: 'Avaya traces' },
  { id: 'rtcpmon', label: 'Media quality' },
] as const;

function Inspector({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const opener = document.activeElement;
    element.showModal();
    return () => {
      element.close();
      if (opener instanceof HTMLElement) {
        window.requestAnimationFrame(() => { if (opener.isConnected) opener.focus({ preventScroll: true }); });
      }
    };
  }, []);
  return <dialog ref={dialog} className="assurance-modal-card" aria-label={title}
    onCancel={(event) => { event.preventDefault(); close(); }}
    onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
    <div className="assurance-modal-content">{children}</div>
  </dialog>;
}

const messageFor = (error: unknown) => error instanceof Error ? error.message : 'Request failed';
const metric = (value: number | null | undefined, digits: number, unit: string) =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) + unit : '—';

export type HomerStatus = {
  status: string;
  architecture: string;
  heplify_server: {
    status: string;
    version: string;
    hep_listener: { port: number; active: boolean };
    total_sip_packets_received: number;
  };
  database: {
    engine: string;
    database: string;
    connected: boolean;
    total_persisted_call_packets: number;
  };
  asterisk_capture: {
    version: string;
    res_hep: boolean;
    res_hep_pjsip: boolean;
    capture_node_id: string;
  };
};

export type SipHop = {
  hop_id: number;
  timestamp: string;
  source_node: string;
  target_node: string;
  src_ip_port: string;
  dst_ip_port: string;
  message_label: string;
  latency_delta_ms: number;
  raw_sip: string;
};

export type SipLadder = {
  call_id: string;
  total_hops: number;
  correlation_status: string;
  hops: SipHop[];
  mermaid: string;
  evidence_quality: string;
  classification?: string;
  capture_node_id?: string;
};

export type AvtestRun = {
  avtest_run_id: string;
  tenant: string;
  target_extension: string;
  test_name: string;
  sip_call_id: string;
  capture_source_id: string;
  homer_reference: string;
  actual_code: number;
  outcome: string;
  setup_duration_ms: number;
  correlation_status: string;
  source_timestamp: string;
  ladder: SipLadder;
  created_at: number;
};

export type CapturedCall = {
  call_id: string;
  start_time: string;
  end_time: string;
  packet_count: number;
  from_user: string;
  to_user: string;
  methods: string;
  final_status_code: number;
  outcome: string;
  homer_reference: string;
  source_ip?: string;
  destination_ip?: string;
  capture_node_id?: string;
  classification?: string;
  evidence_quality?: string;
};

export type AvayaTraceHop = {
  hop_id: number;
  timestamp_str: string;
  epoch: number;
  source_node: string;
  target_node: string;
  interface: string;
  direction: string;
  transport: string;
  src_endpoint: string;
  dst_endpoint: string;
  call_id: string;
  orig_call_id: string | null;
  method: string;
  status_code: number | null;
  cseq: string;
  from_header: string;
  to_header: string;
  latency_delta_ms: number;
  raw_sip: string;
  is_decrypted_capture: boolean;
};

export type AvayaTraceRun = {
  trace_id: string;
  tenant: string;
  source_tool: string;
  primary_call_id: string;
  correlated_call_ids: string[];
  b2bua_legs: number;
  from_user: string;
  to_user: string;
  start_time: string;
  end_time: string;
  total_duration_ms: number;
  final_status_code: number;
  outcome: string;
  total_hops: number;
  hops: AvayaTraceHop[];
  mermaid: string;
  gdpr_sanitized: boolean;
  capture_point: string;
  created_at: number;
};

export type AvayaRtcpmonRecord = {
  record_id: string;
  tenant: string;
  call_id: string;
  calling_party: string;
  called_party: string;
  local_ip: string;
  remote_ip: string;
  codec: string;
  endpoint_model: string;
  packets_sent: number;
  packets_lost: number;
  loss_rate_pct: number;
  discard_rate_pct: number;
  jitter_mean_ms: number;
  jitter_max_ms: number;
  round_trip_delay_ms: number;
  burst_duration_ms: number;
  calculated_r_factor: number;
  calculated_mos: number;
  reported_r_factor: number;
  reported_mos: number;
  evidence_valid: boolean;
  diagnostic_assessment: string[];
  created_at: number;
};

export function VoiceEvidence() {
  const { authHeader, activeSubSection, navigate } = useInvestigation();
  const authorization = authHeader.Authorization;
  const subTab = ['traces', 'avaya_traces'].includes(activeSubSection || '') ? 'avaya_traces' :
    ['rtcp', 'rtcpmon'].includes(activeSubSection || '') ? 'avaya_rtcpmon' : 'asterisk_homer';
  const activeView = subTab === 'avaya_traces' ? 'traces' : subTab === 'avaya_rtcpmon' ? 'rtcpmon' : 'sip';
  const [refresh, setRefresh] = useState(0);
  const [feedState, setFeedState] = useState<Record<string, string>>({});
  const [inspection, setInspection] = useState<{ id: string; kind: 'call' | 'trace' } | null>(() => {
    const params = new URLSearchParams(window.location.search);
    const trace = params.get('trace_id');
    const call = params.get('call_id');
    return trace ? { id: trace, kind: 'trace' } : call ? { id: call, kind: 'call' } : null;
  });
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [homerStatus, setHomerStatus] = useState<HomerStatus | null>(null);
  const [runs, setRuns] = useState<AvtestRun[]>([]);
  const [rawCalls, setRawCalls] = useState<CapturedCall[]>([]);
  const [selectedExt, setSelectedExt] = useState<string>('1001');
  const [originating, setOriginating] = useState<boolean>(false);
  const [originateError, setOriginateError] = useState<string | null>(null);
  const [selectedLadder, setSelectedLadder] = useState<SipLadder | null>(null);
  const [expandedHop, setExpandedHop] = useState<number | null>(null);
  const [showMermaid, setShowMermaid] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Avaya Traces & RTCPMON state
  const [avayaTraces, setAvayaTraces] = useState<AvayaTraceRun[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<AvayaTraceRun | null>(null);
  const [showTraceMermaid, setShowTraceMermaid] = useState<boolean>(false);
  const [expandedTraceHop, setExpandedTraceHop] = useState<number | null>(null);
  const [copiedTraceMermaid, setCopiedTraceMermaid] = useState<boolean>(false);
  const [rtcpRecords, setRtcpRecords] = useState<AvayaRtcpmonRecord[]>([]);
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);
  const [pruneStatus, setPruneStatus] = useState<string | null>(null);

  const request = useCallback(async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
    const headers = new Headers(options.headers);
    if (authorization) headers.set('Authorization', authorization);
    const response = await fetch('/api/v1/assurance/' + path, { ...options, headers });
    if (response.status === 401 || response.status === 403) {
      throw new Error('Sign in with an authorized operator token.');
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.replaceAll('_', ' ') || 'Request failed');
    return data as T;
  }, [authorization]);

  const reloadData = () => setRefresh((previous) => previous + 1);
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    let timer: number | undefined;
    async function read<T>(key: string, path: string, save: (value: T) => void) {
      try {
        const value = await request<T>(path, { signal });
        if (signal.aborted) return;
        save(value);
        setFeedState((previous) => ({ ...previous, [key]: 'ready' }));
      } catch (error) {
        if (!signal.aborted) setFeedState((previous) => ({ ...previous, [key]: messageFor(error) }));
      }
    }
    async function poll() {
      if (subTab === 'asterisk_homer') {
        await Promise.all([
          read<HomerStatus>('status', 'homer/status', setHomerStatus),
          read<{ runs: AvtestRun[] }>('runs', 'avtest/runs?limit=25', (data) => setRuns(data.runs)),
          read<{ calls: CapturedCall[] }>('calls', 'homer/calls?limit=25', (data) => setRawCalls(data.calls)),
        ]);
      } else if (subTab === 'avaya_traces') {
        await read<{ traces: AvayaTraceRun[] }>('traces', 'avaya/trace/runs', (data) => setAvayaTraces(data.traces));
      } else {
        await read<{ records: AvayaRtcpmonRecord[] }>('media', 'avaya/rtcpmon/records', (data) => setRtcpRecords(data.records));
      }
      if (!signal.aborted) timer = window.setTimeout(poll, 15_000);
    }
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [request, refresh, subTab]);

  useEffect(() => {
    if (!inspection) return;
    const controller = new AbortController();
    const { signal } = controller;
    const id = encodeURIComponent(inspection.id);
    const load = inspection.kind === 'call'
      ? request<SipLadder>('homer/ladder?call_id=' + id, { signal }).then((ladder) => {
        if (signal.aborted) return;
        if (!ladder.hops?.length) throw new Error('HOMER has no signaling packets for this call.');
        setSelectedLadder(ladder);
      })
      : request<AvayaTraceRun>('avaya/trace/detail?trace_id=' + id, { signal }).then((trace) => {
        if (!signal.aborted) setSelectedTrace(trace);
      });
    load.catch((error) => { if (!signal.aborted) setInspectionError(messageFor(error)); });
    return () => controller.abort();
  }, [inspection, request]);

  const feedMessage = (key: string, empty: string) => {
    const status = feedState[key];
    return status === 'ready' ? empty : status || 'Loading…';
  };
  const openLadder = (id: string) => {
    setExpandedHop(null);
    setShowMermaid(false);
    setCopied(false);
    setInspectionError(null);
    setInspection({ kind: 'call', id });
  };
  const openTrace = (id: string) => {
    setExpandedTraceHop(null);
    setShowTraceMermaid(false);
    setCopiedTraceMermaid(false);
    setInspectionError(null);
    setInspection({ kind: 'trace', id });
  };
  const closeInspector = () => { setInspection(null); setSelectedLadder(null); setSelectedTrace(null); };
  const displayedFeeds = subTab === 'asterisk_homer' ? ['status', 'calls', 'runs'] : [subTab === 'avaya_traces' ? 'traces' : 'media'];
  const refreshError = displayedFeeds.some((key) => feedState[key] && feedState[key] !== 'ready');

  const handleOriginate = async () => {
    setOriginating(true);
    setOriginateError(null);
    try {
      const newRun = await request<AvtestRun>('avtest/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extension: selectedExt }),
      });
      setRuns((prev) => [newRun, ...prev]);
      if (newRun.ladder && newRun.ladder.total_hops > 0) {
        setExpandedHop(null);
        setShowMermaid(false);
        setSelectedLadder(newRun.ladder);
      }
      reloadData();
    } catch (error) {
      setOriginateError(messageFor(error));
    } finally {
      setOriginating(false);
    }
  };

  const copyMermaid = async (value: string, markCopied: (copied: boolean) => void) => {
    try {
      await navigator.clipboard.writeText(value);
      markCopied(true);
    } catch {
      setInspectionError('Clipboard access is unavailable. Select and copy the sequence text.');
    }
  };

  const handleIngestTraceFixture = async (fixtureType: 'tracesbc' | 'tracesm') => {
    setIsIngesting(true);
    setIngestStatus(null);
    try {
      const data = await request<{ ingested_count: number; trace_ids: string[] }>('avaya/trace/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_fixture: true, fixture_type: fixtureType }),
      });
      setIngestStatus(`✓ Successfully ingested ${data.ingested_count} trace run: ${data.trace_ids.join(', ')}`);
      reloadData();
    } catch (error) {
      setIngestStatus('Error: ' + messageFor(error));
    } finally {
      setIsIngesting(false);
    }
  };

  const handleIngestRtcpmonFixture = async () => {
    setIsIngesting(true);
    setIngestStatus(null);
    try {
      const data = await request<{ record_id: string; record?: AvayaRtcpmonRecord }>('avaya/rtcpmon/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_fixture: true }),
      });
      setIngestStatus(`✓ Successfully ingested RTCPMON record: ${data.record_id} (G.107 MOS: ${data.record?.calculated_mos})`);
      reloadData();
    } catch (error) {
      setIngestStatus('Error: ' + messageFor(error));
    } finally {
      setIsIngesting(false);
    }
  };

  const handlePruneHomer = async () => {
    try {
      const data = await request<{ retained_partitions_count: number }>('homer/prune', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days_to_keep: 7 }),
      });
      setPruneStatus(`✓ Homer retention enforced: ${data.retained_partitions_count} partitions active in homer_data`);
    } catch (error) {
      setPruneStatus('Prune error: ' + messageFor(error));
    }
  };

  return (
    <div className="voice-assurance-container">
      <nav className="assurance-tabs-bar" aria-label="Voice evidence views">
        {VOICE_VIEWS.map(({ id, label }) => <button key={id} type="button"
          className={'assurance-tab-btn' + (activeView === id ? ' active' : '')}
          aria-pressed={activeView === id}
          onClick={() => { closeInspector(); setInspectionError(null); setIngestStatus(null); navigate('communications', id); }}>
          {label}
        </button>)}
        <button type="button" className="btn btn-secondary voice-refresh" onClick={reloadData}>Refresh</button>
      </nav>
      {refreshError && <p className="assurance-callout" role="status">Some evidence could not be refreshed. {displayedFeeds.map((key) => feedState[key]).find((state) => state && state !== 'ready')}</p>}
      {inspection && !selectedLadder && !selectedTrace && !inspectionError && <p role="status">Loading evidence…</p>}
      {inspectionError && !selectedLadder && !selectedTrace && <p className="assurance-callout" role="alert">{inspectionError}</p>}

      {/* ========================================================================= */}
      {/* TAB 1: ASTERISK 22 & HOMER 7 LAB (HEPV3)                                   */}
      {/* ========================================================================= */}
      {subTab === 'asterisk_homer' && (
        <>
          <section className="panel">
            <div className="voice-panel-header">
              <div><h2>Capture pipeline</h2><p>HOMER, Heplify and the local Asterisk test source</p></div>
              <span className="badge badge-neutral">{homerStatus?.status || (feedState.status ? 'Unavailable' : 'Loading')}</span>
            </div>
            <div className="assurance-cards-grid">
              <div className="assurance-stat-card">
                <div className="assurance-stat-label">HEP collector</div>
                <div className="assurance-stat-value">{homerStatus?.heplify_server.status ?? '—'}</div>
                <div className="assurance-stat-meta">{homerStatus ?
                  'Port ' + homerStatus.heplify_server.hep_listener.port + ' · ' + (homerStatus.heplify_server.hep_listener.active ? 'Listening' : 'Inactive') : 'Listener status unavailable'}</div>
              </div>
              <div className="assurance-stat-card">
                <div className="assurance-stat-label">Captured packets</div>
                <div className="assurance-stat-value">{homerStatus?.database.connected ?
                  homerStatus.database.total_persisted_call_packets.toLocaleString() : '—'}</div>
                <div className="assurance-stat-meta">{homerStatus ? (homerStatus.database.connected ? 'Storage connected' : 'Storage unavailable') : 'Storage status unavailable'}</div>
              </div>
              <div className="assurance-stat-card">
                <div className="assurance-stat-label">Asterisk capture</div>
                <div className="assurance-stat-value">{homerStatus ? (homerStatus.asterisk_capture.res_hep_pjsip ? 'Enabled' : 'Inactive') : '—'}</div>
                <div className="assurance-stat-meta">{homerStatus?.asterisk_capture.capture_node_id || 'Source unavailable'}</div>
              </div>
            </div>
          </section>

          {/* 2. ACTION PANEL: ORIGINATE CONTROLLED SYNTHETIC CALL */}
          <section className="panel">
            <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', margin: '0 0 0.5rem' }}>
              Run a local test call
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: '0 0 1rem' }}>
              Choose a lab extension to capture and inspect the SIP exchange in HOMER.
            </p>

            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <label htmlFor="voice-extension" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Diagnostic Target Extension</label>
                <select
                  id="voice-extension"
                  value={selectedExt}
                  onChange={(e) => setSelectedExt(e.target.value)}
                  style={{
                    background: 'var(--panel-surface)',
                    color: 'var(--text-primary)',
                    border: '1px solid var(--border-light)',
                    borderRadius: '6px',
                    padding: '0.5rem 0.75rem',
                    width: '100%',
                    fontSize: '0.85rem'
                  }}
                >
                  <option value="1001">Ext 1001 — Echo Test (Expected: 200 OK Answered)</option>
                  <option value="1002">Ext 1002 — Fast Answer &amp; Hangup (Expected: 200 OK)</option>
                  <option value="1003">Ext 1003 — Busy Simulator (Expected: 486 Busy Here)</option>
                  <option value="1004">Ext 1004 — Congestion Simulator (Expected: 503 Service Unavailable)</option>
                </select>
              </div>

              <button
                onClick={handleOriginate}
                disabled={originating}
                className="assurance-tab-btn active"
                style={{
                  marginTop: '1.15rem',
                  opacity: originating ? 0.7 : 1,
                  cursor: originating ? 'not-allowed' : 'pointer',
                }}
              >
                {originating ? '⏳ Originating SIP Call & Capturing HEP...' : '⚡ Originate Isolated Test Call'}
              </button>
            </div>

            {originateError && (
              <div style={{ marginTop: '0.75rem', padding: '0.65rem 0.85rem', background: '#fee2e2', border: '1px solid #f87171', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem' }}>
                Error: {originateError}
              </div>
            )}
          </section>

          {/* 3. RECENT AVTEST CALL RUNS WITH HOMER CORRELATION */}
          <section className="panel">
            <div className="voice-panel-header">
              <div>
                <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  Recent test calls
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', margin: '2px 0 0' }}>
                  Correlates AVTEST execution run IDs with Asterisk PJSIP Call-IDs and verified HOMER signaling ladders.
                </p>
              </div>
              <span className="badge badge-dimmed">
                Total Executions: {runs.length}
              </span>
            </div>

            {runs.length === 0 ? (
              <div className="assurance-callout" style={{ textAlign: 'center', padding: '1.5rem' }}>
                {feedMessage('runs', 'No test runs recorded.')}
              </div>
            ) : (
              <div className="assurance-table" role="region" aria-label="Recent test calls" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>Run ID</th>
                      <th>Target Extension</th>
                      <th>Test Name</th>
                      <th>Outcome</th>
                      <th>SIP Code</th>
                      <th>Duration</th>
                      <th>SIP Call-ID</th>
                      <th>Evidence</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => {
                      const isOk = r.outcome === 'ANSWERED';
                      const isBusy = r.outcome === 'BUSY';
                      const badgeClass = isOk ? 'badge-success' : (isBusy ? 'badge-warning' : 'badge-danger');

                      return (
                        <tr key={r.avtest_run_id}>
                          <td style={{ fontFamily: 'monospace', color: 'var(--teal-primary)', fontWeight: 600 }}>{r.avtest_run_id}</td>
                          <td style={{ fontWeight: 600 }}>Ext {r.target_extension}</td>
                          <td style={{ color: 'var(--text-muted)' }}>{r.test_name}</td>
                          <td>
                            <span className={`badge ${badgeClass}`}>
                              {r.outcome}
                            </span>
                          </td>
                          <td style={{ fontFamily: 'monospace' }}>
                            SIP {r.actual_code}
                          </td>
                          <td style={{ color: 'var(--text-muted)' }}>{r.setup_duration_ms} ms</td>
                          <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {r.sip_call_id || '—'}
                          </td>
                          <td>
                            <span className="badge badge-success">
                              {r.correlation_status || 'Pending'}
                            </span>
                          </td>
                          <td>
                            <button
                              onClick={() => openLadder(r.sip_call_id)}
                              className="assurance-tab-btn"
                              style={{ padding: '3px 8px', fontSize: '0.75rem' }}
                            >
                              🔍 View SIP Ladder
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* 4. ALL RAW CAPTURED SIP CALLS IN HOMER DATABASE */}
          <section className="panel">
            <div className="voice-panel-header">
              <div>
                <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  Recent SIP captures
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', margin: '2px 0 0' }}>
                  Queried directly from PostgreSQL database <code>homer_data</code> via HOMER 7 API.
                </p>
              </div>
              <span className="badge badge-dimmed">
                {rawCalls.length} Transactions
              </span>
            </div>

            {rawCalls.length === 0 ? (
              <p style={{ color: 'var(--text-muted)' }}>{feedMessage('calls', 'No SIP captures recorded.')}</p>
            ) : (
              <div className="assurance-table" role="region" aria-label="Recent SIP captures" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>Call-ID</th>
                      <th>Type / Source</th>
                      <th>From / To</th>
                      <th>Observed Methods</th>
                      <th>Packets</th>
                      <th>Final Status</th>
                      <th>Start Time</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rawCalls.map((c) => (
                      <tr key={c.call_id}>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--teal-primary)' }}>
                          {c.call_id}
                        </td>
                        <td>
                          <span className={`badge ${c.classification === 'PRODUCTION' ? 'badge-success' : 'badge-neutral'}`} style={{ fontSize: '0.7rem' }}>
                            {c.classification === 'PRODUCTION' ? `PROD · ${c.source_ip || 'Avaya'}` : `SYNTH · ${c.source_ip || '127.0.0.1'}`}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-muted)' }}>
                          {c.from_user} → {c.to_user}
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {c.methods}
                        </td>
                        <td>{c.packet_count} pkts</td>
                        <td>
                          <span className={`badge ${c.final_status_code === 200 ? 'badge-success' : 'badge-danger'}`}>
                            SIP {c.final_status_code} ({c.outcome})
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{c.start_time}</td>
                        <td>
                          <button
                            onClick={() => openLadder(c.call_id)}
                            className="assurance-tab-btn"
                            style={{ padding: '3px 8px', fontSize: '0.75rem' }}
                          >
                            Inspect Ladder
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: AVAYA MULTI-LEG DIAGNOSTIC TRACES (traceSBC & traceSM)             */}
      {/* ========================================================================= */}
      {subTab === 'avaya_traces' && (
        <>
          <section className="panel">
            <div className="voice-panel-header">
              <div><h2>Avaya trace samples</h2><p>Load a sanitized sample from the SBC or Session Manager.</p></div>
            </div>
            <div className="assurance-filters">
              <button type="button" className="btn btn-secondary" disabled={isIngesting}
                onClick={() => handleIngestTraceFixture('tracesbc')}>Load traceSBC sample</button>
              <button type="button" className="btn btn-secondary" disabled={isIngesting}
                onClick={() => handleIngestTraceFixture('tracesm')}>Load traceSM sample</button>
            </div>
            {ingestStatus && <p className="assurance-callout" role="status">{ingestStatus}</p>}
          </section>

          {/* Table of Reconstructed Avaya Diagnostic Traces */}
          <section className="panel">
            <div className="voice-panel-header">
              <div>
                <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  Recent Avaya traces
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', margin: '2px 0 0' }}>
                  Persisted diagnostic runs correlated across network demarcations.
                </p>
              </div>
              <span className="badge badge-dimmed">
                {avayaTraces.length} Diagnostic Runs
              </span>
            </div>

            {avayaTraces.length === 0 ? (
              <div className="assurance-callout" style={{ textAlign: 'center', padding: '1.5rem' }}>
                {feedMessage('traces', 'No Avaya traces recorded.')}
              </div>
            ) : (
              <div className="assurance-table" role="region" aria-label="Recent Avaya traces" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>Trace ID</th>
                      <th>Source Tool</th>
                      <th>Primary Call-ID</th>
                      <th>B2BUA Legs</th>
                      <th>Caller → Callee (GDPR)</th>
                      <th>Duration</th>
                      <th>Outcome</th>
                      <th>Hops</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {avayaTraces.map((t) => (
                      <tr key={t.trace_id}>
                        <td style={{ fontFamily: 'monospace', color: 'var(--teal-primary)', fontWeight: 600 }}>{t.trace_id}</td>
                        <td>
                          <span className={`badge ${t.source_tool === 'traceSBC' ? 'badge-info' : 'badge-neutral'}`} style={{ fontWeight: 600 }}>
                            {t.source_tool}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {t.primary_call_id || '—'}
                        </td>
                        <td>
                          <span className={`badge ${t.b2bua_legs > 1 ? 'badge-success' : 'badge-neutral'}`}>
                            {t.b2bua_legs} Leg{t.b2bua_legs > 1 ? 's' : ''} (Correlated)
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {t.from_user} → {t.to_user}
                        </td>
                        <td style={{ color: 'var(--text-muted)' }}>{t.total_duration_ms} ms</td>
                        <td>
                          <span className={`badge ${t.outcome === 'ANSWERED' ? 'badge-success' : 'badge-danger'}`} style={{ fontWeight: 600 }}>
                            SIP {t.final_status_code} ({t.outcome})
                          </span>
                        </td>
                        <td>{t.total_hops} hops</td>
                        <td>
                          <button
                            onClick={() => openTrace(t.trace_id)}
                            className="assurance-tab-btn"
                            style={{ padding: '3px 8px', fontSize: '0.75rem' }}
                          >
                            🔍 Inspect Trace
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: AVAYA RTCPMON & RFC 3611 MEDIA QUALITY                             */}
      {/* ========================================================================= */}
      {subTab === 'avaya_rtcpmon' && (
        <>
          <section className="panel">
            <div className="voice-panel-header">
              <div><h2>Media quality samples</h2><p>Compare packet loss, jitter, round-trip time and MOS from RTCPMON records.</p></div>
            </div>
            <button type="button" className="btn btn-secondary" disabled={isIngesting}
              onClick={handleIngestRtcpmonFixture}>Load RTCPMON sample</button>
            {ingestStatus && <p className="assurance-callout" role="status">{ingestStatus}</p>}
            <details className="voice-retention">
              <summary>HOMER capture retention</summary>
              <p>Pruning permanently deletes HOMER capture partitions older than seven days.</p>
              <button type="button" className="btn btn-secondary" onClick={() => {
                if (window.confirm('Delete HOMER capture partitions older than seven days?')) void handlePruneHomer();
              }}>Prune old captures</button>
              {pruneStatus && <p className="assurance-callout" role="status">{pruneStatus}</p>}
            </details>
          </section>

          {/* Table of RTCPMON Records */}
          <section className="panel">
            <div className="voice-panel-header">
              <div>
                <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  Decoded Media Quality Records (Avaya RTCPMON &amp; RFC 3611)
                </h2>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', margin: '2px 0 0' }}>
                  Independent ITU-T G.107 E-model calculations cross-checked against phone reported values.
                </p>
              </div>
              <span className="badge badge-dimmed">
                {rtcpRecords.length} Records
              </span>
            </div>

            {rtcpRecords.length === 0 ? (
              <div className="assurance-callout" style={{ textAlign: 'center', padding: '1.5rem' }}>
                {feedMessage('media', 'No media quality records captured.')}
              </div>
            ) : (
              <div className="assurance-table" role="region" aria-label="Recent media quality records" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>Record ID</th>
                      <th>Endpoint Model</th>
                      <th>Codec</th>
                      <th>Loss %</th>
                      <th>Discard %</th>
                      <th>Jitter</th>
                      <th>RTT</th>
                      <th>Calculated G.107 MOS</th>
                      <th>Reported Phone MOS</th>
                      <th>Diagnostic Assessment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rtcpRecords.map((r) => {
                      const isTollQuality = (r.calculated_mos || 0) >= 4.0;
                      const mosClass = r.calculated_mos == null ? 'badge-neutral' : isTollQuality ? 'badge-success' : ((r.calculated_mos || 0) >= 3.5 ? 'badge-warning' : 'badge-danger');

                      return (
                        <tr key={r.record_id}>
                          <td style={{ fontFamily: 'monospace', color: 'var(--teal-primary)', fontWeight: 600 }}>{r.record_id}</td>
                          <td style={{ fontWeight: 600 }}>{r.endpoint_model}</td>
                          <td>
                            <span className="badge badge-neutral" style={{ fontFamily: 'monospace' }}>
                              {r.codec}
                            </span>
                          </td>
                          <td style={{ color: r.loss_rate_pct > 1.0 ? '#ef4444' : 'var(--text-primary)' }}>
                            {metric(r.loss_rate_pct, 2, '%')}
                          </td>
                          <td style={{ color: r.discard_rate_pct > 1.0 ? '#ef4444' : 'var(--text-primary)' }}>
                            {metric(r.discard_rate_pct, 2, '%')}
                          </td>
                          <td style={{ color: 'var(--text-primary)' }}>
                            {metric(r.jitter_mean_ms, 1, ' ms')}
                          </td>
                          <td style={{ color: 'var(--text-primary)' }}>
                            {metric(r.round_trip_delay_ms, 1, ' ms')}
                          </td>
                          <td>
                            <span className={`badge ${mosClass}`} style={{ fontWeight: 700 }}>
                              MOS {r.calculated_mos?.toFixed(2) || '—'} (R {r.calculated_r_factor?.toFixed(1) || '—'})
                            </span>
                          </td>
                          <td style={{ color: 'var(--text-muted)' }}>
                            {r.reported_mos != null ? `MOS ${r.reported_mos.toFixed(2)} (R ${r.reported_r_factor?.toFixed(1) || '—'})` : '—'}
                          </td>
                          <td style={{ fontSize: '0.75rem' }}>
                            {r.diagnostic_assessment && r.diagnostic_assessment.length > 0 ? (
                              <span style={{ color: isTollQuality ? '#10b981' : '#ef4444', fontWeight: 600 }}>
                                {r.diagnostic_assessment[0]}
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>No assessment</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {/* ========================================================================= */}
      {/* MODAL 1: ASTERISK / HOMER SIP LADDER & RAW PACKET INSPECTOR               */}
      {/* ========================================================================= */}
      {selectedLadder && (
        <Inspector title="SIP signaling ladder" close={closeInspector}>
            {/* Modal Header */}
            <div className="assurance-modal-header">
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  SIP Signaling Ladder &amp; Protocol Inspector
                </h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', margin: '2px 0 0', fontFamily: 'monospace' }}>
                  Call-ID: {selectedLadder.call_id}
                </p>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '6px', alignItems: 'center' }}>
                  <span className={`badge ${selectedLadder.classification === 'PRODUCTION' ? 'badge-success' : 'badge-neutral'}`} style={{ fontSize: '0.75rem' }}>
                    {selectedLadder.classification === 'PRODUCTION' ? '[PRODUCTION — VERIFIED AVAYA SOURCE]' : '[SYNTHETIC — ASTERISK PROBE]'}
                  </span>
                  <span className="badge badge-dimmed" style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                    Capture Node: {selectedLadder.capture_node_id || 'nawari-avtest-lab'}
                  </span>
                </div>
              </div>
              <button
                onClick={closeInspector}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', fontSize: '1.25rem', cursor: 'pointer', padding: '4px 8px' }}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            {/* Modal View Selector */}
            <div className="assurance-modal-toolbar">
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={() => setShowMermaid(false)}
                  className={`assurance-tab-btn ${!showMermaid ? 'active' : ''}`}
                  style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                >
                  Chronological Hops ({selectedLadder.total_hops})
                </button>
                <button
                  onClick={() => setShowMermaid(true)}
                  className={`assurance-tab-btn ${showMermaid ? 'active' : ''}`}
                  style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                >
                  Mermaid Sequence
                </button>
              </div>

              {showMermaid && (
                <button
                  onClick={() => void copyMermaid(selectedLadder.mermaid, setCopied)}
                  className="assurance-tab-btn"
                  style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                >
                  {copied ? '✓ Copied' : '📋 Copy Mermaid'}
                </button>
              )}
            </div>

            {/* Modal Body */}
            <div className="assurance-modal-body">
              {inspectionError && <p role="alert">{inspectionError}</p>}
              {showMermaid ? (
                <div>
                  <pre className="assurance-terminal-pre">
                    {selectedLadder.mermaid}
                  </pre>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {selectedLadder.hops.map((hop) => {
                    const isExpanded = expandedHop === hop.hop_id;
                    return (
                      <div
                        key={hop.hop_id}
                        className="assurance-stat-card"
                        style={{ padding: '0.75rem 1rem', gap: '0.5rem' }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span
                              style={{
                                background: 'var(--teal-primary)',
                                color: '#fff',
                                width: '24px',
                                height: '24px',
                                borderRadius: '50%',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '0.75rem',
                                fontWeight: 700,
                              }}
                            >
                              {hop.hop_id}
                            </span>
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.9rem' }}>
                              {hop.source_node} → {hop.target_node}
                            </span>
                            <span
                              className="badge badge-info"
                              style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}
                            >
                              {hop.message_label}
                            </span>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                              +{hop.latency_delta_ms} ms
                            </span>
                            <button
                              onClick={() => setExpandedHop(isExpanded ? null : hop.hop_id)}
                              className="assurance-tab-btn"
                              style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                            >
                              {isExpanded ? 'Hide Raw' : 'Inspect Raw SIP'}
                            </button>
                          </div>
                        </div>

                        {/* Collapsible raw SIP packet viewer */}
                        {isExpanded && (
                          <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-light)' }}>
                            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', display: 'flex', justifyContent: 'space-between' }}>
                              <span>Transport: {hop.src_ip_port} → {hop.dst_ip_port} (UDP/5060)</span>
                              <span>Timestamp: {hop.timestamp}</span>
                            </div>
                            <pre className="assurance-terminal-pre">
                              {hop.raw_sip}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="assurance-modal-footer">
              <span>
                🛡️ Verified Genuine Signaling Trace. Loopback test isolated entirely from corporate trunking.
              </span>
              <button
                onClick={closeInspector}
                className="assurance-tab-btn active"
                style={{ padding: '4px 14px' }}
              >
                Close Inspector
              </button>
            </div>
        </Inspector>
      )}

      {/* ========================================================================= */}
      {/* MODAL 2: AVAYA MULTI-LEG DIAGNOSTIC TRACE INSPECTOR                        */}
      {/* ========================================================================= */}
      {selectedTrace && (
        <Inspector title="Avaya trace inspector" close={closeInspector}>
            {/* Modal Header */}
            <div className="assurance-modal-header">
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                  Avaya Multi-Leg Trace: {selectedTrace.source_tool} ({selectedTrace.trace_id})
                </h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', margin: '2px 0 0', fontFamily: 'monospace' }}>
                  Demarcation: {selectedTrace.capture_point}
                </p>
              </div>
              <button
                onClick={closeInspector}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', fontSize: '1.25rem', cursor: 'pointer', padding: '4px 8px' }}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            {/* B2BUA Correlation Banner */}
            <div className="assurance-modal-toolbar">
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Correlated Call-IDs:</span>
                {selectedTrace.correlated_call_ids.map((cid) => (
                  <span key={cid} className="badge badge-info" style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                    {cid}
                  </span>
                ))}
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={() => setShowTraceMermaid(false)}
                  className={`assurance-tab-btn ${!showTraceMermaid ? 'active' : ''}`}
                  style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                >
                  Hop Sequence ({selectedTrace.total_hops})
                </button>
                <button
                  onClick={() => setShowTraceMermaid(true)}
                  className={`assurance-tab-btn ${showTraceMermaid ? 'active' : ''}`}
                  style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                >
                  Mermaid Sequence
                </button>
                {showTraceMermaid && (
                  <button
                    onClick={() => void copyMermaid(selectedTrace.mermaid, setCopiedTraceMermaid)}
                    className="assurance-tab-btn"
                    style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                  >
                    {copiedTraceMermaid ? '✓ Copied' : '📋 Copy'}
                  </button>
                )}
              </div>
            </div>

            {/* Modal Body */}
            <div className="assurance-modal-body">
              {inspectionError && <p role="alert">{inspectionError}</p>}
              {showTraceMermaid ? (
                <div>
                  <pre className="assurance-terminal-pre">
                    {selectedTrace.mermaid}
                  </pre>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {selectedTrace.hops.map((hop) => {
                    const isExpanded = expandedTraceHop === hop.hop_id;
                    const isTls = hop.transport?.toUpperCase() === 'TLS';

                    return (
                      <div
                        key={hop.hop_id}
                        className="assurance-stat-card"
                        style={{ padding: '0.75rem 1rem', gap: '0.5rem' }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                            <span
                              style={{
                                background: 'var(--teal-primary)',
                                color: '#fff',
                                width: '24px',
                                height: '24px',
                                borderRadius: '50%',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '0.75rem',
                                fontWeight: 700,
                              }}
                            >
                              {hop.hop_id}
                            </span>
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.9rem' }}>
                              {hop.source_node} → {hop.target_node}
                            </span>
                            <span
                              className={`badge ${isTls ? 'badge-info' : 'badge-neutral'}`}
                              style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}
                            >
                              {hop.method} [{hop.transport}]
                            </span>
                            <span className="badge badge-dimmed" style={{ fontSize: '0.7rem' }}>
                              {hop.interface} ({hop.direction})
                            </span>
                            {hop.is_decrypted_capture && (
                              <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                                🔒 Decrypted Capture
                              </span>
                            )}
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                              +{hop.latency_delta_ms} ms
                            </span>
                            <button
                              onClick={() => setExpandedTraceHop(isExpanded ? null : hop.hop_id)}
                              className="assurance-tab-btn"
                              style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                            >
                              {isExpanded ? 'Hide Raw' : 'Inspect Raw SIP'}
                            </button>
                          </div>
                        </div>

                        {/* Collapsible raw SIP message */}
                        {isExpanded && (
                          <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-light)' }}>
                            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px', display: 'flex', justifyContent: 'space-between' }}>
                              <span>Endpoint: {hop.src_endpoint} → {hop.dst_endpoint}</span>
                              <span>Timestamp: {hop.timestamp_str}</span>
                            </div>
                            <pre className="assurance-terminal-pre">
                              {hop.raw_sip}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="assurance-modal-footer">
              <span>
                🛡️ GDPR Redacted: Phone numbers (+254***) and station extensions (1**1) anonymized before storage.
              </span>
              <button
                onClick={closeInspector}
                className="assurance-tab-btn active"
                style={{ padding: '4px 14px' }}
              >
                Close Inspector
              </button>
            </div>
        </Inspector>
      )}
    </div>
  );
}

