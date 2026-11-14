import { useEffect, useRef } from 'react';
import { init, use } from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import type { MetricHistory as History } from './types';

use([LineChart, GridComponent, TooltipComponent, SVGRenderer]);

export default function MetricHistory({history}:{history:History}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const chart = init(container.current, undefined, {renderer:'svg'});
    chart.setOption({animation:false,grid:{left:58,right:20,top:24,bottom:35},
      tooltip:{trigger:'axis',valueFormatter:(value:unknown)=>value===null?'Unavailable':`${Number(value).toFixed(2)} ${history.metric.units}`},
      xAxis:{type:'time',axisLabel:{color:'#536475'},splitLine:{show:false}},
      yAxis:{type:'value',name:history.metric.units,axisLabel:{color:'#536475'},splitLine:{lineStyle:{color:'#e8edf1'}}},
      series:[{type:'line',showSymbol:history.samples.length<80,connectNulls:false,data:history.samples.map(x=>[x.time*1000,x.value]),lineStyle:{color:'#0f766e',width:2},itemStyle:{color:'#0f766e'}}]});
    const observer=new ResizeObserver(()=>chart.resize()); observer.observe(container.current);
    return()=>{observer.disconnect();chart.dispose();};
  },[history]);
  return <div className="metric-history" ref={container} role="img" aria-label={`${history.metric.description}, ${history.sample_count} historical samples`} />;
}
