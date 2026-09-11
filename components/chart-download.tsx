'use client';
import {useState,type RefObject} from 'react';
import {downloadChartPng} from '@/lib/chart-export';
export function ChartDownload({chartRef,filename,freezeNote}:{chartRef:RefObject<HTMLElement|null>;filename:string;freezeNote:string}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 return <><button type="button" className="download-chart" disabled={busy} onClick={async()=>{setBusy(true);setError('');try{if(!chartRef.current)throw new Error('Chart is not ready.');await downloadChartPng(chartRef.current,filename,freezeNote);}catch{setError('Unable to export this chart. Please try again once the chart has loaded.');}finally{setBusy(false)}}}>{busy?'Preparing PNG…':'Download chart ↓'}</button>{error&&<span role="alert" className="export-error">{error}</span>}</>;
}
