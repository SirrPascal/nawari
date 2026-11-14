import { Suspense, lazy, useEffect, useState } from 'react';
import type { Metric, MetricCatalogue, MetricHistory as History } from './types';
import { time } from './types';

const MetricHistory = lazy(()=>import('./MetricHistory'));

export default function MetricExplorer({device,section,token,start,end}:{device:string;section:string;token:string;start?:number;end?:number}) {
  const [catalogue,setCatalogue]=useState<MetricCatalogue|null>(null);
  const [search,setSearch]=useState('');
  const [applied,setApplied]=useState('');
  const [offset,setOffset]=useState(0);
  const [selected,setSelected]=useState<Metric|null>(null);
  const [history,setHistory]=useState<History|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{setOffset(0);setSelected(null);setHistory(null);},[device,section]);
  useEffect(()=>{
    if(!device)return;
    const controller=new AbortController();
    const query=new URLSearchParams({section,limit:'50',offset:String(offset)}); if(applied)query.set('q',applied);
    fetch(`/api/v1/devices/${encodeURIComponent(device)}/metrics?${query}`,{signal:controller.signal,headers:token?{Authorization:`Bearer ${token}`}:{}})
      .then(async r=>{if(!r.ok)throw new Error(`Metric catalogue unavailable (${r.status}).`);return r.json();})
      .then((x:MetricCatalogue)=>{setCatalogue(x);setError('');}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
    return()=>controller.abort();
  },[device,section,token,offset,applied]);
  useEffect(()=>{
    if(!selected)return;
    const controller=new AbortController(); const query=new URLSearchParams({points:'120'});
    if(start)query.set('start',String(start)); if(end)query.set('end',String(end));
    fetch(`/api/v1/devices/${encodeURIComponent(device)}/metrics/${selected.metric_id}/history?${query}`,{signal:controller.signal,headers:token?{Authorization:`Bearer ${token}`}:{}})
      .then(async r=>{if(!r.ok)throw new Error(`Metric history unavailable (${r.status}).`);return r.json();})
      .then((x:History)=>{setHistory(x);setError('');}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
    return()=>controller.abort();
  },[selected,device,token,start,end]);
  const connection=catalogue?.node?.capabilities.network_connections;
  return <>
    <section className="panel metric-overview"><div><h2>Managed agent catalogue</h2><p className="muted">{catalogue?.node?`${catalogue.node.os_name} · Netdata ${catalogue.node.agent_version} · API response generation ${catalogue.node.api_generation}`:'No associated Netdata node has been discovered.'}</p></div><div className="catalogue-stats"><span><strong>{catalogue?.node?.capabilities.catalogue?.contexts??0}</strong>contexts</span><span><strong>{catalogue?.node?.capabilities.catalogue?.charts??0}</strong>charts</span><span><strong>{catalogue?.node?.capabilities.catalogue?.dimensions??0}</strong>dimensions</span></div></section>
    {section==='applications'?<section className="panel"><h2>Observed application connections</h2><p className={`capability ${connection?.access==='available'?'fresh':'unknown'}`}>{connection?.registered?'Collector function registered':'Collector function unavailable'} · {connection?.access?.replaceAll('_',' ')??'not discovered'}</p><p className="muted">The pinned agent registers process/socket topology, but this local installation returned access status 412. No connection tuples are copied into Nawari. Connection inventory would not prove per-application throughput, latency, service identity or call quality.</p></section>:null}
    <section className="panel"><div className="panel-heading"><div><h2>{section==='all'?'All collected metrics':`${section[0].toUpperCase()+section.slice(1)} metrics`}</h2><p className="muted">Dynamic catalogue · unavailable and historical metrics remain visible.</p></div><form className="metric-search" onSubmit={e=>{e.preventDefault();setOffset(0);setApplied(search);}}><label>Search metrics<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Context, chart or dimension" /></label><button>Search</button></form></div>
      {error?<p className="error" role="alert">{error}</p>:null}
      <p className="caption">{catalogue?.total??0} matching dimensions · showing {offset+1}–{Math.min(offset+50,catalogue?.total??0)}</p>
      <div className="table-scroll"><table><thead><tr><th>Metric</th><th>Dimension</th><th>Unit</th><th>Source</th><th>Last observed</th><th>Coverage</th></tr></thead><tbody>{catalogue?.metrics.map(metric=><tr key={metric.metric_id} className={selected?.metric_id===metric.metric_id?'highlight':''}><td><button className="metric-link" onClick={()=>setSelected(metric)}>{metric.context_id}</button><small>{metric.description}</small></td><td>{metric.display_name}</td><td>{metric.units}</td><td>{metric.plugin}<small>{metric.module}</small></td><td>{time(metric.last_observed)}</td><td><span className={`state ${metric.availability==='available'?'fresh':'unknown'}`}>{metric.availability}</span></td></tr>)}</tbody></table></div>
      <div className="pagination"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous</button><button disabled={!catalogue?.partial} onClick={()=>setOffset(catalogue?.next_offset??offset)}>Next</button></div>
    </section>
    {selected?<section className="panel metric-detail"><div className="panel-heading"><div><p className="eyebrow">Selected statistic</p><h2>{selected.context_id} · {selected.display_name}</h2></div><span className={`state ${selected.availability==='available'?'fresh':'unknown'}`}>{selected.collection_outcome}</span></div><dl><dt>Definition</dt><dd>{selected.description}</dd><dt>Unit</dt><dd>{selected.units}</dd><dt>Collector</dt><dd>{selected.plugin} / {selected.module}</dd><dt>Collection interval</dt><dd>{selected.update_every} seconds</dd><dt>Timestamp quality</dt><dd>{selected.timestamp_quality}</dd><dt>Valid aggregation</dt><dd>{history?.aggregation??'Loading bounded history…'}</dd><dt>Retention observed</dt><dd>{time(selected.retention_start)} – {time(selected.retention_end)}</dd><dt>Catalogue/API</dt><dd>{selected.catalogue_version} / {selected.source_api}</dd></dl>{history?<><Suspense fallback={<p>Loading metric history…</p>}><MetricHistory history={history}/></Suspense><p className="caption">{history.sample_count} returned samples · gaps remain gaps · source {history.source_api}</p></>:null}</section>:null}
  </>;
}
