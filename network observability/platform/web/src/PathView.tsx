import { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import type { Hop } from './types';

export default function PathView({ hops }: { hops: Hop[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (!container.current || !hops.length) return;
    const graph = cytoscape({container:container.current, elements:[
      ...hops.map((hop,i) => ({data:{id:String(i),label:hop.node,kind:hop.kind},position:{x:90+i*190,y:65}})),
      ...hops.slice(1).map((hop,i) => ({data:{id:`edge-${i}`,source:String(i),target:String(i+1),kind:hop.kind}})),
    ], layout:{name:'preset',fit:true,padding:35}, userPanningEnabled:false,userZoomingEnabled:false,
      style:[
        {selector:'node',style:{'label':'data(label)','background-color':'#e1efec','border-color':'#0f766e','border-width':1,'width':30,'height':30,'font-size':12,'text-valign':'bottom','text-margin-y':12,'color':'#203342'}},
        {selector:'edge',style:{'width':2,'line-color':'#0f766e','target-arrow-shape':'triangle','target-arrow-color':'#0f766e','curve-style':'bezier'}},
        {selector:'edge[kind="inferred"]',style:{'line-style':'dashed','line-color':'#8693a0','target-arrow-color':'#8693a0'}},
        {selector:'node:selected',style:{'background-color':'#0f766e'}},
      ],
    });
    graph.on('tap','node',event => setSelected(event.target.data('label')));
    const observer = new ResizeObserver(() => {graph.resize();graph.fit(undefined,35);});
    observer.observe(container.current);
    return () => {observer.disconnect();graph.destroy();};
  }, [hops]);
  if (!hops.length) return <p className="empty">No path observation is available for this selection.</p>;
  return <>
    <div ref={container} className="path" role="img" aria-label="Observed and inferred path relationships, listed below" />
    <div className="hop-list">{hops.map((hop,i) => <button key={i} onClick={() => setSelected(hop.node)} className={selected===hop.node?'selected':''}>{hop.node}<small>{hop.kind.replaceAll('_',' ')}</small></button>)}</div>
    <p className="caption">Solid edges show observed Layer 3 evidence. Dashed edges show inferred relationships. Hidden hops remain unknown.</p>
  </>;
}
