import { StrictMode, Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { Investigation, Observation } from './types';
import { time } from './types';
import './style.css';
import './metrics.css';

const Timeline = lazy(() => import('./Timeline'));
const PathView = lazy(() => import('./PathView'));
const MetricExplorer = lazy(() => import('./MetricExplorer'));
const empty: Observation[] = [];

function App() {
  const [query,setQuery] = useState(() => window.location.search);
  const [data,setData] = useState<Investigation | null>(null);
  const [error,setError] = useState('');
  const [loading,setLoading] = useState(true);
  const [token,setToken] = useState('');
  const [draft,setDraft] = useState('');
  const [needsAuth,setNeedsAuth] = useState(false);
  const [refresh,setRefresh] = useState(0);
  useEffect(() => {
    const pop = () => setQuery(window.location.search);
    window.addEventListener('popstate',pop);
    return () => window.removeEventListener('popstate',pop);
  },[]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const params = new URLSearchParams(query);
    params.delete('device'); params.delete('sample'); params.delete('service'); params.delete('operation'); params.delete('view');
    fetch(`/api/v1/investigation?${params}`, {signal:controller.signal,headers:token?{Authorization:`Bearer ${token}`}:{}})
      .then(async response => {
        if (response.status===401) {setNeedsAuth(true);throw new Error('Operator authentication required.');}
        if (!response.ok) throw new Error(`Investigation unavailable (${response.status}).`);
        return response.json();
      }).then((next: Investigation) => {
        if (next.schema_version !== undefined && next.schema_version !== '1') throw new Error('Unsupported API schema.');
        setData(next);setError('');setNeedsAuth(false);
      }).catch(reason => {if(reason.name!=='AbortError') setError(reason.message);})
      .finally(() => {if(!controller.signal.aborted)setLoading(false);});
    return () => controller.abort();
  },[query,token,refresh]);
  const navigate = useCallback((key:string,value:string) => {
    const params = new URLSearchParams(window.location.search);
    if(value) params.set(key,value); else params.delete(key);
    if(key!=='sample') params.delete('sample');
    window.history.pushState(null,'',`?${params}`);setQuery(window.location.search);
  },[]);
  const selectSample = useCallback((id:string) => navigate('sample',id),[navigate]);
  const params = new URLSearchParams(query);
  const view = params.get('view') ?? 'overview';
  const device = params.get('device') ?? data?.sources.find(x=>x.point_kind==='endpoint')?.asset_id ?? '';
  const service = params.get('service') ?? data?.operations[0]?.service_id ?? '';
  const operationId = params.get('operation') ?? data?.operations.find(x=>x.service_id===service)?.operation_id ?? '';
  const operation = data?.operations.find(x=>x.service_id===service && x.operation_id===operationId);
  const records = data?.observations.filter(x=>x.asset_id===device && x.record.payload_type==='service_test' && x.service_id===service && x.record.operation_id===operationId) ?? empty;
  const comparisonAssets = new Set(data?.sources.filter(x=>x.point_kind==='regional').map(x=>x.asset_id));
  const comparison = data?.observations.filter(x=>comparisonAssets.has(x.asset_id) && x.record.payload_type==='service_test' && x.service_id===service && x.record.operation_id===operationId) ?? empty;
  const selected = records.find(x=>x.record_id===params.get('sample')) ?? records[0];
  const context = data?.observations.find(x=>x.asset_id===device && x.record.payload_type==='network_context'
    && selected && Date.parse(String(x.record.payload.effective_from))/1000<=selected.observed_at && Date.parse(String(x.record.payload.effective_until))/1000>selected.observed_at);
  const path = data?.observations.find(x=>x.asset_id===device && x.record.payload_type==='path' && (!selected || x.observed_at<=selected.observed_at+15));
  const incidents = data?.incidents.filter(x=>x.asset_id===device && x.service_id===service) ?? [];
  const hypotheses = data?.hypotheses?.filter(x=>x.asset_id===device) ?? [];
  const events = data?.observations.filter(x=>x.asset_id===device && x.record.payload_type==='selected_event') ?? empty;
  const failures = records.filter(x=>x.record.collection_outcome==='complete' && x.record.payload.test_result!=='success').length;
  const source = data?.sources.find(x=>x.asset_id===device);
  const catalogue = data?.metric_catalogue[0];

  return <div className="app">
    <header className="topbar"><a className="brand" href="/">nawari<span>Network experience</span></a><div className="top-status">{data?.mode==='fixture'?'Controlled fixture workspace':'Operator workspace'}<button onClick={()=>setRefresh(x=>x+1)} disabled={loading}>{loading?'Refreshing…':'Refresh evidence'}</button></div></header>
    {data?.mode==='fixture'?<div className="fixture-banner">Controlled local fixtures · All devices, service targets, regional comparisons and infrastructure relationships shown here are validation data.</div>:null}
    {error?<div className="error" role="alert">{error} {data?'Previously loaded evidence remains visible.':''}</div>:null}
    {needsAuth?<form className="auth" onSubmit={event=>{event.preventDefault();setToken(draft);setDraft('');}}><h1>Operator access</h1><label>Scoped operator token<input type="password" value={draft} onChange={event=>setDraft(event.target.value)} autoComplete="off" /></label><button type="submit">Open investigation</button></form>:null}
    <div className="workspace">
      <aside><h2>Observation points</h2><p className="muted">Assigned devices stay visible when reporting stops.</p><nav aria-label="Devices">{data?.sources.map(item=><button key={item.enrollment_id} aria-pressed={device===item.asset_id} onClick={()=>navigate('device',item.asset_id)} className={device===item.asset_id?'active':''}><span>{item.asset_id}</span><small>{item.point_kind} · {item.coverage}</small></button>)}</nav><div className="source-health"><h2>Pipeline state</h2>{Object.entries(data?.integration_status??{}).map(([key,value])=><p key={key}><strong>{key}</strong><span>{value.replaceAll('_',' ')}</span></p>)}{data?.outbox.map(x=><p key={x.state}><strong>{x.state}</strong><span>{x.count} records</span></p>)}</div></aside>
      <main aria-busy={loading}>
        <div className="page-heading"><div><p className="eyebrow">Device investigation</p><h1>{device || 'Loading evidence…'}</h1><p className="muted">{data?.assets.find(x=>x.asset_id===device)?.site_id ?? 'Site unavailable'} · {source?.point_kind ?? 'Unknown observation point'}</p></div><span className={`state ${source?.coverage??'unknown'}`}>{source?.coverage??'unknown'} collection</span></div>
        <div className="device-sections" role="tablist" aria-label="Device investigation sections">{[['overview','Overview'],['system','System'],['applications','Applications'],['network','Network'],['services','Business services'],['all','All metrics'],['evidence','Evidence']].map(([key,label])=><button role="tab" aria-selected={view===key} className={view===key?'active':''} key={key} onClick={()=>navigate('view',key)}>{label}</button>)}</div>
        {['overview','system','applications','network','all'].includes(view)&&device?<Suspense fallback={<section className="panel"><p>Loading managed metric catalogue…</p></section>}><MetricExplorer device={device} section={view==='overview'?'system':view} token={token} start={params.get('start')?Number(params.get('start')):undefined} end={params.get('end')?Number(params.get('end')):undefined}/></Suspense>:null}
        <section className="filters" aria-label="Investigation filters"><label>Service operation<select value={`${service}|${operationId}`} onChange={event=>{const [nextService,nextOperation]=event.target.value.split('|');const p=new URLSearchParams(window.location.search);p.set('service',nextService);p.set('operation',nextOperation);p.delete('sample');window.history.pushState(null,'',`?${p}`);setQuery(window.location.search);}}>{data?.operations.map(x=><option key={`${x.service_id}|${x.operation_id}`} value={`${x.service_id}|${x.operation_id}`}>{x.name} · {x.operation_id}</option>)}</select></label><label>Start · local time<input type="datetime-local" value={params.get('start')?new Date(Number(params.get('start'))*1000-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16):''} onChange={event=>navigate('start',event.target.value?String(Date.parse(event.target.value)/1000):'')} /></label><label>End · local time<input type="datetime-local" value={params.get('end')?new Date(Number(params.get('end'))*1000-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16):''} onChange={event=>navigate('end',event.target.value?String(Date.parse(event.target.value)/1000):'')} /></label><button onClick={()=>{const p=new URLSearchParams(window.location.search);p.delete('start');p.delete('end');window.history.pushState(null,'',`?${p}`);setQuery(window.location.search);}}>Last hour</button></section>
        {data?.partial?<p className="error">Partial result · Showing a bounded page. Narrow the time range to investigate all samples.</p>:null}
        <section className="summary" aria-label="Selected scope summary"><div><span>Latest operation</span><strong>{selected?.record.payload.total_ms!=null?`${selected.record.payload.total_ms.toFixed(1)} ms`:'Unavailable'}</strong><small>{selected?.record.payload.test_result?.replaceAll('_',' ')??'No observation'}</small></div><div><span>Returned samples</span><strong>{records.length}</strong><small>{failures} explicit failures</small></div><div><span>Performance objective</span><strong>{operation?`${operation.objective_ms} ms`:'Undefined'}</strong><small>Individual request duration</small></div><div><span>Regional comparison</span><strong>{comparison.length?`${comparison[0].record.payload.total_ms?.toFixed(1)} ms`:'Unavailable'}</strong><small>{comparison.length} comparison samples</small></div></section>
        <section className="panel"><div className="panel-heading"><h2>Service response timeline</h2><span className="legend">● Laptop <span>┄ Regional reference</span></span></div><p className="muted">{operation?.description??catalogue?.definition??'Measurement definition unavailable.'}</p>{records.length?<Suspense fallback={<p>Loading timeline…</p>}><Timeline records={records} comparison={comparison} objective={operation?.objective_ms??500} onSelect={selectSample}/></Suspense>:<p className="empty">No service observations in this window. Collection coverage remains unknown.</p>}<p className="caption">{catalogue?.aggregation} · {records.length} samples · API snapshot {data?time(data.generated_at):'pending'}</p>{operation?<div className="coverage-note"><strong>What this proves</strong><p>{operation.proves??'Only the configured operation result.'}</p><strong>What remains unproven</strong><p>{operation.cannot_prove??'Complete application and employee-session health.'}</p></div>:null}</section>
        <div className="detail-grid"><section className="panel"><h2>Selected observation</h2>{selected?<><dl><dt>Observation time</dt><dd>{new Date(selected.observed_at*1000).toLocaleString()}</dd><dt>Collection outcome</dt><dd>{selected.record.collection_outcome}</dd><dt>Freshness at selected time</dt><dd>{selected.freshness}</dd><dt>Source / execution context</dt><dd>nawari.plugin / {selected.record.execution_context}</dd><dt>Configuration</dt><dd>{selected.record.config_version}</dd><dt>Delivery</dt><dd>{selected.state}</dd></dl><h3>Request phases</h3><table><thead><tr><th>Phase</th><th>State</th><th>Duration</th></tr></thead><tbody>{Object.entries(selected.record.payload.phases??{}).map(([name,phase])=><tr key={name}><td>{name}</td><td>{phase.state.replaceAll('_',' ')}</td><td>{phase.duration_ms===null?'Unavailable':`${phase.duration_ms.toFixed(1)} ms`}</td></tr>)}</tbody></table></>:<p className="empty">Select an available observation.</p>}</section><section className="panel"><h2>Network context at observation time</h2>{context?<dl>{Object.entries(context.record.payload).filter(([key])=>!key.startsWith('effective')).map(([key,value])=><div className="context-row" key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{String(value)}</dd></div>)}</dl>:<p className="empty">No time-valid network context is available.</p>}<h3>Scope and evidence limits</h3><p className="muted">Loopback fixtures exercise collection and investigation. Employee routing, wireless associations and user-session behaviour require real-service acceptance.</p></section></div>
        <section className="panel"><h2>Path and relationships</h2><Suspense fallback={<p>Loading relationships…</p>}><PathView hops={path?.record.payload.hops??[]}/></Suspense></section>
        <div className="detail-grid"><section className="panel"><h2>Related events</h2>{events.length?events.map(x=><article className="event" key={x.record_id}><strong>{x.record.payload.event_class?.replaceAll('_',' ')}</strong><p>{time(x.observed_at)} · {x.record.payload.source_kind} · {x.state}</p></article>):<p className="empty">No selected events in this window.</p>}</section><section className="panel"><h2>Evidence-supported hypotheses</h2>{hypotheses.length?hypotheses.map(x=><article className="event" key={`${x.classification}-${x.evidence.join('-')}`}><strong>{x.classification.replaceAll('_',' ')}</strong><p>{x.confidence.replaceAll('_',' ')} · {x.evidence.length} linked observations</p><p className="muted">{x.statement}</p></article>):<p className="empty">Insufficient compatible evidence for a ranked hypothesis.</p>}<h3>Shadow incidents</h3>{incidents.length?incidents.map(x=><article className="event" key={x.incident_id}><strong>Suspected {x.suspected_domain.replaceAll('_',' ')} degradation</strong><p>{time(x.opened_at)} · {x.state} · revision {x.revision}</p><p className="muted">Operator confirmation pending. Review the matching samples and regional comparison.</p></article>):<p className="empty">No shadow incident in this window. Review collection coverage before assessing service health.</p>}</section></div>
        <section className="panel"><h2>Evidence samples</h2><p className="muted">Select a row to inspect timing phases and time-valid context. Showing {Math.min(20, records.length)} of {records.length} returned samples.</p><div className="table-scroll"><table><thead><tr><th>Observed</th><th>Duration</th><th>Result</th><th>Collection</th><th>Freshness</th><th>Inspect</th></tr></thead><tbody>{records.slice(0,20).map(row=><tr key={row.record_id} className={row.record_id===selected?.record_id?'highlight':''}><td>{time(row.observed_at)}</td><td>{row.record.payload.total_ms==null?'Unavailable':`${row.record.payload.total_ms.toFixed(1)} ms`}</td><td>{row.record.payload.test_result?.replaceAll('_',' ')}</td><td>{row.record.collection_outcome}</td><td>{row.freshness}</td><td><button onClick={()=>selectSample(row.record_id)} aria-label={`Inspect sample at ${time(row.observed_at)}`}>Inspect</button></td></tr>)}</tbody></table></div></section>
      </main>
    </div>
  </div>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
