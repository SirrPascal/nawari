import { useEffect, useRef } from 'react';
import { init, use } from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import type { Observation } from './types';

use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, SVGRenderer]);

export default function Timeline({ records, comparison, objective, onSelect }: {
  records: Observation[]; comparison: Observation[]; objective: number; onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const chart = init(container.current, undefined, {renderer: 'svg'});
    const series = (values: Observation[]) => [...values].sort((a,b) => a.observed_at-b.observed_at).flatMap((row,i,all) => {
      const point = {value: [row.observed_at*1000, row.record.collection_outcome === 'complete' ? row.record.payload.total_ms ?? null : null], id: row.record_id};
      const gap = i > 0 && row.observed_at-all[i-1].observed_at > 30;
      return gap ? [{value:[(row.observed_at-1)*1000,null],id:'gap'},point] : [point];
    });
    chart.setOption({
      animation: false,
      grid: {left: 56, right: 24, top: 30, bottom: 35},
      tooltip: {trigger:'axis', valueFormatter:(value: unknown) => value === null ? 'Unavailable' : `${Number(value).toFixed(1)} ms`},
      xAxis: {type:'time', axisLine:{lineStyle:{color:'#cbd5dc'}}, axisLabel:{color:'#536475'}, splitLine:{show:false}},
      yAxis: {type:'value', name:'ms', min:0, axisLabel:{color:'#536475'}, splitLine:{lineStyle:{color:'#e8edf1'}}},
      series: [
        {name:'Selected laptop', type:'line', data:series(records), showSymbol:true, symbolSize:5, connectNulls:false, lineStyle:{color:'#0f766e',width:2}, itemStyle:{color:'#0f766e'}, markLine:{symbol:'none', label:{formatter:`Objective ${objective} ms`,position:'insideEndTop'},lineStyle:{color:'#b45309',type:'dashed'},data:[{yAxis:objective}]}},
        {name:'Regional fixture',type:'line',data:series(comparison),showSymbol:false,connectNulls:false,lineStyle:{color:'#6b7a90',type:'dashed',width:2}},
      ],
    });
    chart.on('click', (event) => {
      const data = event.data as {id?: string} | undefined;
      if (data?.id && data.id !== 'gap') onSelect(data.id);
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => {observer.disconnect(); chart.dispose();};
  }, [records, comparison, objective, onSelect]);
  return <div className="timeline" ref={container} role="img" aria-label="Individual HTTP duration samples over time. Select a sample using the evidence table below." />;
}
