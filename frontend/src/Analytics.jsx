import React from 'react';
import { ST, QUALITY, ha } from './lib.js';

function niceMax(v) {
  const steps = [100, 200, 250, 400, 500, 600, 800, 1000, 1500, 2000];
  return steps.find((s) => s >= v) || Math.ceil(v / 500) * 500;
}

// Left panel: replaces the design's "Detections per month" (we have 13 cases, not a monthly stream).
// Same visual grammar: stacked bars in HIGH / MEDIUM / LOW colours, but per case and in hectares.
export function DisturbanceChart({ cases, visibleIds, onOpen }) {
  const max = niceMax(Math.max(...cases.map((c) => (c.area_ha || 0))));
  const H = 160, k = H / max;
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((f) => Math.round(max * f));
  const sorted = cases.slice().sort((a, b) => (b.area_ha || 0) - (a.area_ha || 0));
  return (
    <section aria-label="Disturbed area by permit coverage" className="card an-card">
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <h2>Disturbed area by permit coverage</h2>
          <span className="muted" style={{ fontSize: 11.5 }}>Per case, hectares of detected change · split by BIG KSP permit status at the after-image date</span>
        </div>
        <div style={{ display: 'flex', gap: 12, fontSize: 11.5, color: '#3D4044' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, background: ST.HIGH.bar }} />No permit</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, background: ST.MEDIUM.bar }} />Expired</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, background: ST.LOW.bar }} />Active</span>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '34px minmax(0, 1fr)', gap: 6 }}>
        <div className="mono muted" style={{ position: 'relative', height: H, fontSize: 10, textAlign: 'right' }}>
          {ticks.map((t, i) => <span key={i} style={{ position: 'absolute', right: 0, top: i * (H / 4) - 6 }}>{t}</span>)}
        </div>
        <div style={{ position: 'relative', height: H }}>
          <div aria-hidden="true" style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div className="gridline" /><div className="gridline" /><div className="gridline" /><div className="gridline" /><div style={{ borderTop: '1px solid #A3A6AA' }} />
          </div>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'flex-end', gap: 8, padding: '0 6px' }}>
            {sorted.map((c) => (
              <button key={c.id} type="button" onClick={() => onOpen(c.id)}
                title={`${c.id} ${c.loc}: ${ha(c.area_ha)} ha — no permit ${ha(c.no_permit_ha)}, expired ${ha(c.in_expired_ha)}, active ${ha(c.in_active_ha)}`}
                style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', opacity: visibleIds.has(c.id) ? 1 : 0.35, border: 0, padding: 0, background: 'transparent', cursor: 'pointer' }}>
                <span className="tnum" style={{ fontSize: 9.5, textAlign: 'center', color: '#3D4044', marginBottom: 2 }}>{Math.round(c.area_ha || 0)}</span>
                <div style={{ height: (c.no_permit_ha || 0) * k, background: ST.HIGH.bar }} />
                <div style={{ height: (c.in_expired_ha || 0) * k, background: ST.MEDIUM.bar }} />
                <div style={{ height: (c.in_active_ha || 0) * k, background: ST.LOW.bar }} />
              </button>
            ))}
          </div>
        </div>
        <div />
        <div style={{ display: 'flex', gap: 8, padding: '0 6px' }}>
          {sorted.map((c) => <span key={c.id} className="mono muted" style={{ flex: 1, textAlign: 'center', fontSize: 9.5, whiteSpace: 'nowrap', overflow: 'hidden' }}>{c.id.replace('MW-GT-', '')}</span>)}
        </div>
      </div>
    </section>
  );
}

// Right panel: replaces the design's "Accuracy backtest" (precision/recall). There is no trained model
// and only positive ground-truth sites, so precision cannot be computed. We show what CAN be measured
// honestly: how many known illegal-mining sites the threshold + permit check flags, per data-quality tier.
export function GroundTruthChart({ cases, meta, onOpen }) {
  const flagged = (c) => c.status === 'HIGH' || c.status === 'MEDIUM';
  const nFlag = cases.filter(flagged).length;
  const tiers = ['reliable', 'light_caveat', 'medium_caveat', 'unreliable'].filter((t) => cases.some((c) => c.quality === t));
  const sorted = cases.slice().sort((a, b) => (b.pct_outside || 0) - (a.pct_outside || 0));
  return (
    <section aria-label="Ground-truth check" className="card an-card">
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <h2>Ground-truth check</h2>
          <span className="muted" style={{ fontSize: 11.5 }}>{cases.length} pilot sites in selected period · no negative sites in this pilot</span>
        </div>
        <div className="tnum" style={{ fontSize: 11.5, color: '#3D4044' }}>
          No matching permit or permit expired <b>{nFlag}/{cases.length}</b>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {sorted.map((c) => {
          const st = ST[c.status] || ST.UNCHECKED;
          const q = QUALITY[c.quality];
          return (
            <button key={c.id} type="button" onClick={() => onOpen(c.id)} title={`${c.loc} — ${c.pct_outside}% of flagged area outside any permit`}
              style={{ display: 'grid', gridTemplateColumns: '64px minmax(0,1fr) 40px 92px', alignItems: 'center', gap: 8, border: 0, background: 'transparent', padding: '1px 0', cursor: 'pointer', textAlign: 'left', fontSize: 11 }}>
              <span className="mono muted" style={{ fontSize: 10.5 }}>{c.id.replace('MW-GT-', 'GT-')}</span>
              <span style={{ position: 'relative', height: 9, background: '#F1F1EE', borderRadius: 1 }}>
                <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${c.pct_outside || 0}%`, background: st.bar, borderRadius: 1 }} />
                {meta.status_rule === 'strict' && <span style={{ position: 'absolute', top: -2, bottom: -2, left: '50%', borderLeft: '1px dashed #5F6368' }} />}
              </span>
              <span className="mono" style={{ textAlign: 'right' }}>{Math.round(c.pct_outside || 0)}%</span>
              <span className="pill" style={{ background: q.bg, color: q.fg, fontWeight: 600, justifySelf: 'start' }}>{q.label}</span>
            </button>
          );
        })}
      </div>
      <div className="muted" style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginTop: 8, fontSize: 10.5 }}>
        <span>Bar = % of flagged area outside every permit, coloured by assigned status</span>
        <span>{tiers.map((t) => `${cases.filter((c) => c.quality === t).length} ${QUALITY[t].label.toLowerCase()}`).join(' · ')}</span>
      </div>
    </section>
  );
}
