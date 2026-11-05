'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { dashboardMarkup } from './markup';
import './dashboard.css';
import '../electricity/icons.css';
import '../electricity/navigation.css';
import { readInitialDataset } from './live.js';

export default function NIElectricityDashboard() {
  const root = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  // React must preserve this subtree after its map and charts are initialized.
  const dashboard = useMemo(() => <div ref={root} className="ni-electricity" dangerouslySetInnerHTML={{ __html: dashboardMarkup }} />, []);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const element = root.current!;
    // Each mount owns its DOM and handlers, including during React effect replay.
    element.innerHTML = dashboardMarkup;
    async function load() {
      try {
        const [runtime, snapshot, history] = await Promise.all([
          import('./runtime.js'),
          readInitialDataset('snapshot', signal),
          readInitialDataset('history', signal),
        ]);
        if (signal.aborted) return;
        runtime.mountElectricity(element, snapshot.data, history.data, signal, { snapshot: snapshot.version, history: history.version });
        setStatus('ready');
      } catch (error) {
        if (!signal.aborted) {
          console.error('Electricity dashboard could not load its data.', error);
          setStatus('error');
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      element.querySelector('dialog')?.close();
    };
  }, []);

  return (
    <main className="wrap electricity-page" aria-busy={status === 'loading'}>
      <div className="electricity-status" role="status" hidden={status === 'ready'}>
        {status === 'loading' ? 'Loading the electricity snapshot and historical data…' : <>
          The electricity data could not be loaded. <button onClick={() => window.location.reload()}>Reload dashboard</button>
        </>}
      </div>
      <noscript>This dashboard needs JavaScript to display the map and explore time series. You can download the <a href="/data/ni-electricity/snapshot.json">snapshot</a> and <a href="/data/ni-electricity/history.json">historical data</a>.</noscript>
      {dashboard}
    </main>
  );
}
