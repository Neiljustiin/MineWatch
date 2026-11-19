import React from 'react';
import { fmtDateTime } from './lib.js';

export default function SettingsView({ meta, analyst, onLogout }) {
  const row = (k, v) => (<><span className="muted">{k}</span><span>{v}</span></>);
  return (
    <main className="page" style={{ maxWidth: 900 }}>
      <div className="page-h"><h1>Settings</h1></div>
      <section className="card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 style={{ margin: 0, fontSize: 13.5 }}>Analyst identity</h2>
        <span className="muted" style={{ fontSize: 12 }}>Signed in as <strong style={{ color: '#17181A' }}>{analyst || '…'}</strong>. This name is used to sign every decision and audit event you record — it comes from your login, not a free-text field.</span>
        <div>
          <button className="btn" onClick={onLogout}>Log out</button>
        </div>
      </section>
      <section className="card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 style={{ margin: 0, fontSize: 13.5 }}>Status classification</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '160px minmax(0,1fr)', gap: '6px 12px', fontSize: 12.5 }}>
          {row('Active rule', <span className="mono">{meta.status_rule}</span>)}
          {row('Definition', meta.status_rule_text)}
          {row('Change it', <span>Restart the API with <span className="mono">MINEWATCH_STATUS_RULE=strict</span> and <span className="mono">MINEWATCH_HIGH_PCT=50</span> (or another agreed value).</span>)}
        </div>
      </section>
      <section className="card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <h2 style={{ margin: 0, fontSize: 13.5 }}>Data provenance</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '160px minmax(0,1fr)', gap: '6px 12px', fontSize: 12.5 }}>
          {row('Detection', meta.detection_method)}
          {row('Permit baseline', `${meta.permit_baseline} — ${meta.permit_count.toLocaleString('en-US')} polygons`)}
          {row('Source repo', <span className="mono">{meta.source_repo}</span>)}
          {row('Bundle built', fmtDateTime(meta.generated_at))}
          {row('Alerting', meta.alerting)}
        </div>
      </section>
    </main>
  );
}
