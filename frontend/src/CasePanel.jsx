import React, { useEffect, useMemo, useState } from 'react';
import { api, ST, PST, COM_LONG, QUALITY, DECISIONS, fmtDate, fmtDateTime, dms, ha, pct } from './lib.js';
import { StatusPill, QualityChip } from './ui.jsx';

const sendIcon = 'M4 12 L20 4 L14 20 L11 13 Z M11 13 L20 4';
const lockIcon = 'M6 11 H18 V20 H6 Z M8.5 11 V8 a3.5 3.5 0 0 1 7 0 V11';
const closeIcon = 'M5 12.5 L10 17 L19 7';

function yearsBetween(a, b) {
  const d = (new Date(b) - new Date(a)) / (365.25 * 864e5);
  return d.toFixed(1);
}

// lon/lat -> pixel in the case image grid
function projector(bounds, W, H) {
  const [w, s, e, n] = bounds;
  return (lon, lat) => [((lon - w) / (e - w)) * W, ((n - lat) / (n - s)) * H];
}

function ringsToPath(geom, P) {
  const polys = geom.type === 'Polygon' ? [geom.coordinates] : geom.type === 'MultiPolygon' ? geom.coordinates : [];
  let d = '';
  for (const poly of polys) for (const ring of poly) {
    ring.forEach(([x, y], i) => { const [px, py] = P(x, y); d += (i ? 'L' : 'M') + px.toFixed(1) + ' ' + py.toFixed(1); });
    d += 'Z';
  }
  return d;
}

function circlePath(lon, lat, km, P) {
  const R = 6371.0088;
  let d = '';
  for (let i = 0; i <= 96; i++) {
    const t = (i / 96) * 2 * Math.PI;
    const dLat = (km / R) * Math.cos(t) * (180 / Math.PI);
    const dLon = ((km / R) * Math.sin(t) * (180 / Math.PI)) / Math.cos((lat * Math.PI) / 180);
    const [x, y] = P(lon + dLon, lat + dLat);
    d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
  }
  return d + 'Z';
}

export default function CasePanel({ id, analyst, onEditAnalyst, onClose, onNavigate, onChanged }) {
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);
  const [geo, setGeo] = useState({ dist: null, permits: null });
  const [ui, setUi] = useState({ split: 50, ndvi: false, aoi: true, permits: true, zoom: 1 });
  const [form, setForm] = useState({ decision: '', notes: '', ack: false });
  const [busy, setBusy] = useState(false);
  const [actErr, setActErr] = useState(null);
  const [reassign, setReassign] = useState(null);
  const [showAudit, setShowAudit] = useState(false);
  const [now, setNow] = useState(Date.now());

  const load = (logView) => api(`/api/cases/${encodeURIComponent(id)}${logView ? '?log=1' : ''}`)
    .then(setC).catch((e) => setErr(e.message));

  useEffect(() => {
    setC(null); setErr(null); setGeo({ dist: null, permits: null });
    setUi({ split: 50, ndvi: false, aoi: true, permits: true, zoom: 1 });
    setForm({ decision: '', notes: '', ack: false }); setActErr(null); setReassign(null); setShowAudit(false);
    load(true);
  }, [id]);

  useEffect(() => {
    if (!c) return;
    const get = (u) => (u ? fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null) : Promise.resolve(null));
    Promise.all([get(c.assets.disturbance), get(c.assets.permits)]).then(([dist, permits]) => setGeo({ dist, permits }));
  }, [c && c.id]);

  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(t); }, []);
  useEffect(() => {
    const f = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (c && e.key === 'ArrowUp' && c.prev_id) onNavigate(c.prev_id);
      if (c && e.key === 'ArrowDown' && c.next_id) onNavigate(c.next_id);
    };
    window.addEventListener('keydown', f);
    return () => window.removeEventListener('keydown', f);
  }, [c]);

  const img = c && c.imagery;
  const P = useMemo(() => (img ? projector(img.bounds, img.width, img.height) : null), [img]);
  const distPath = useMemo(() => (geo.dist && P ? geo.dist.features.map((f) => ringsToPath(f.geometry, P)).join('') : ''), [geo.dist, P]);
  const permitPaths = useMemo(() => (geo.permits && P ? geo.permits.features.map((f) => ({ d: ringsToPath(f.geometry, P), name: f.properties.name })) : []), [geo.permits, P]);

  if (err) return <div style={{ padding: 24 }}><div className="banner">Could not load case {id}: {err}</div><button className="btn" onClick={onClose}>Close</button></div>;
  if (!c) return <div style={{ padding: 24 }} className="muted">Loading {id}…</div>;

  const st = ST[c.status] || ST.UNCHECKED;
  const cc = c.crosscheck;
  const n = c.ndvi || null; // absent when detection = AI model (not NDVI) run
  const modelFrac = c.imagery && c.imagery.model_flagged_pixel_fraction;
  const q = QUALITY[c.quality];

  // compare stage size: fit into the 712px panel, cap height
  const maxW = 712, maxH = 460;
  const ratio = img.height / img.width;
  const stageW = ratio * maxW > maxH ? Math.round(maxH / ratio) : maxW;
  const stageH = Math.round(stageW * ratio);
  const [cx, cy] = P(c.lon, c.lat);
  const origin = `${((cx / img.width) * 100).toFixed(2)}% ${((cy / img.height) * 100).toFixed(2)}%`;
  const scaleStyle = { transform: `scale(${ui.zoom})`, transformOrigin: origin };
  const sw = (px) => px / ui.zoom * (img.width / stageW); // constant on-screen stroke width
  const circle = cc ? circlePath(c.lon, c.lat, cc.radius_km, P) : '';

  // permits table
  const rows = cc ? cc.permits : c.nearby_permits;
  const total = cc ? cc.disturbed_area_ha : 0;
  const share = (v) => (total ? ` (${Math.round((v / total) * 100)}%)` : '');

  // review gate
  const dec = c.active_decision;
  const d = form.decision;
  const alerting = d === 'confirmed' || d === 'verify';
  const closing = d === 'fp' || d === 'legal';
  const ready = !!d && form.ack && !!analyst;
  const recipients = [`DLHK Provinsi ${c.prov}`, `Polda ${c.prov} · Ditreskrimsus`, `Dinas ESDM Provinsi ${c.prov} (cc)`];
  const step = (label, done, active) => ({ label, done, active });
  const steps = [step('Decision selected', !!d, !d), step('Evidence acknowledged', form.ack, !!d && !form.ack), step(closing ? 'Close case' : 'Record alert (mock)', false, ready)];
  let gateHint = 'Select a decision and confirm you reviewed the evidence to unlock.';
  if (!analyst) gateHint = 'Set your analyst name first (top-right) — decisions are signed with it.';
  else if (d && !form.ack) gateHint = 'Confirm the evidence acknowledgement (step 2) to unlock.';
  else if (ready && alerting) gateHint = 'MOCK: the decision, notes and reference are stored. Nothing is emailed or sent — DLHK/Polda integration is not built.';
  else if (ready && closing) gateHint = 'No alert. Case is closed internally and logged in the audit trail.';

  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true); setActErr(null);
    try {
      await api(`/api/cases/${encodeURIComponent(c.id)}/decision`, { method: 'POST', body: { decision: d, notes: form.notes, ack: form.ack, actor: analyst } });
      await load(false); onChanged();
    } catch (e) { setActErr(e.message); }
    setBusy(false);
  };
  const recall = async () => {
    setBusy(true); setActErr(null);
    try {
      await api(`/api/cases/${encodeURIComponent(c.id)}/recall`, { method: 'POST', body: { actor: analyst || 'unknown' } });
      setForm({ decision: dec.decision, notes: dec.notes, ack: false });
      await load(false); onChanged();
    } catch (e) { setActErr(e.message); }
    setBusy(false);
  };
  const doAssign = async () => {
    if (!reassign || !reassign.trim()) return;
    setBusy(true); setActErr(null);
    try {
      await api(`/api/cases/${encodeURIComponent(c.id)}/assign`, { method: 'POST', body: { assignee: reassign.trim(), actor: analyst || 'unknown' } });
      setReassign(null); await load(false); onChanged();
    } catch (e) { setActErr(e.message); }
    setBusy(false);
  };
  // `now` state only drives the 15 s re-render; read the clock directly so a fresh decision never shows > 10 min
  const recallLeft = dec ? Math.min(600, Math.max(0, 600 - (Date.now() - new Date(dec.created_at).getTime()) / 1000)) : 0;
  const created = c.audit.length ? c.audit[c.audit.length - 1] : null;

  const operator = cc && cc.permits.find((p) => (p.overlap_ha || 0) > 0);

  return (
    <div style={{ width: '100%', background: '#fff' }}>
      {/* HEADER */}
      <header className="case-h">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }} className="muted">
            <span>Cases</span><span aria-hidden="true" style={{ color: '#A3A6AA' }}>/</span>
            <span className="mono" style={{ color: '#17181A', fontWeight: 500 }}>{c.id}</span>
            <span style={{ marginLeft: 8, paddingLeft: 8, borderLeft: '1px solid #E2E2DE' }}>After image {fmtDate(img.after_date)}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button type="button" className="sq-btn" aria-label="Previous case" disabled={!c.prev_id} onClick={() => onNavigate(c.prev_id)}><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15 L12 9 L18 15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></button>
            <button type="button" className="sq-btn" aria-label="Next case" disabled={!c.next_id} onClick={() => onNavigate(c.next_id)}><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9 L12 15 L18 9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></button>
            <button type="button" className="sq-btn" aria-label="Close case detail" onClick={onClose}><svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 L18 18 M18 6 L6 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></button>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-end', gap: '8px 16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
            <h1 style={{ margin: 0, fontSize: 21, fontWeight: 650, letterSpacing: '-0.02em' }}>{c.loc}</h1>
            <span style={{ fontSize: 12.5, color: '#4A4D52' }}>{c.kab}, {c.prov} · <span className="muted">
              {operator ? `Largest overlapping permit: ${operator.name}` : 'No permit polygon overlaps the detected area'}
            </span></span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
            <StatusPill status={c.status} big />
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, height: 24, padding: '0 8px 0 4px', border: '1px solid #D8D8D3', borderRadius: 3, fontSize: 12, fontWeight: 500 }}>
              <span className="mono" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 18, height: 16, padding: '0 3px', background: '#17181A', color: '#FFFFFF', borderRadius: 2, fontSize: 10, fontWeight: 600 }}>{c.com}</span>{COM_LONG[c.com]}
            </span>
            <span className="tnum" title={n ? "Share of frame pixels with ΔNDVI < −0.2 (not a model confidence)" : "Share of frame pixels flagged as changed by the FC-Siam-diff v4 model (threshold 0.5)"} style={{ display: 'inline-flex', alignItems: 'center', height: 24, padding: '0 8px', border: '1px solid #D8D8D3', borderRadius: 3, fontSize: 12 }}>
              <b style={{ fontWeight: 600, marginRight: 4 }}>{pct(n ? n.sharp_ndvi_loss_pixel_fraction : modelFrac)}</b> {n ? 'NDVI loss' : 'model flagged'}
            </span>
          </div>
        </div>
      </header>

      <div className="case-body">
        {/* META GRID */}
        <section aria-label="Detection metadata" className="meta-grid">
          <div>
            <span className="eyebrow" style={{ letterSpacing: '0.07em' }}>COORDINATES</span>
            <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>{dms(c.lat, 'N', 'S')}</span>
            <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>{dms(c.lon, 'E', 'W')}</span>
            <span className="mono muted" style={{ fontSize: 10.5 }} title={c.loc_precision}>{c.lat.toFixed(4)}, {c.lon.toFixed(4)}</span>
          </div>
          <div>
            <span className="eyebrow" style={{ letterSpacing: '0.07em' }}>DISTURBED AREA · ≤{cc ? cc.radius_km : 3} KM</span>
            <span className="tnum" style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em' }}>{ha(cc && cc.disturbed_area_ha)} <span className="muted" style={{ fontSize: 12, fontWeight: 500 }}>ha</span></span>
            <span className="muted" style={{ fontSize: 11 }}>{cc ? `${ha(cc.outside_permits_ha)} ha outside any permit` : 'not cross-checked'}</span>
          </div>
          <div>
            <span className="eyebrow" style={{ letterSpacing: '0.07em' }}>IMAGE PAIR</span>
            <span className="tnum" style={{ fontSize: 13, fontWeight: 600 }}>{fmtDate(img.before_date)} →<br />{fmtDate(img.after_date)}</span>
            <span className="muted" style={{ fontSize: 11 }}>{yearsBetween(img.before_date, img.after_date)} years apart · 2 passes only</span>
          </div>
          <div>
            <span className="eyebrow" style={{ letterSpacing: '0.07em' }}>SENSOR · METHOD</span>
            <span style={{ fontSize: 12.5, fontWeight: 500 }}>Sentinel-2 L2A, 10 m</span>
            <span className="muted" style={{ fontSize: 11 }}>NDVI threshold ΔNDVI &lt; −0.2 · not an AI model</span>
          </div>
        </section>

        {/* DATA QUALITY */}
        <div className="banner" style={{ borderLeftColor: q.fg, flexDirection: 'column', gap: 4 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span className="eyebrow">IMAGE QUALITY (MANUAL CLOUD QC)</span><QualityChip q={c.quality} /></span>
          <span>{c.quality_note}</span>
          {c.recheck_note && <span><b>Re-check:</b> {c.recheck_note}</span>}
        </div>

        {/* IMAGERY COMPARE */}
        <section aria-label="Satellite imagery comparison" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <h2 className="eyebrow" style={{ margin: 0 }}>IMAGERY · BEFORE / AFTER</h2>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button type="button" className="toggle dark" aria-pressed={ui.ndvi} onClick={() => setUi({ ...ui, ndvi: !ui.ndvi })}><span className="trk" aria-hidden="true"><span /></span>{n ? 'NDVI change overlay' : 'Model change overlay'}</button>
              <button type="button" className="toggle" aria-pressed={ui.aoi} onClick={() => setUi({ ...ui, aoi: !ui.aoi })}><span className="trk" aria-hidden="true"><span /></span>Detection outline</button>
              <button type="button" className="toggle" aria-pressed={ui.permits} onClick={() => setUi({ ...ui, permits: !ui.permits })}><span className="trk" aria-hidden="true"><span /></span>Permits</button>
              <div className="seg" role="group" aria-label="Zoom to case point">
                {[1, 2, 4].map((z) => <button key={z} type="button" aria-pressed={ui.zoom === z} onClick={() => setUi({ ...ui, zoom: z })}>{z}×</button>)}
              </div>
            </div>
          </div>

          <div className="compare" style={{ width: stageW, height: stageH }}>
            {/* BEFORE (full) */}
            <div className="layer">
              <div className="content" style={scaleStyle}>
                <img src={c.assets.before} alt={`Before image, ${fmtDate(img.before_date)}`} />
              </div>
            </div>
            {/* AFTER (clipped by divider) */}
            <div className="layer" style={{ clipPath: `inset(0 0 0 ${ui.split}%)` }}>
              <div className="content" style={scaleStyle}>
                <img src={c.assets.after} alt={`After image, ${fmtDate(img.after_date)}`} />
                {ui.ndvi && <img src={c.assets.ndvi_loss} alt="" />}
                <svg viewBox={`0 0 ${img.width} ${img.height}`} preserveAspectRatio="none" aria-hidden="true">
                  {ui.aoi && distPath && <path d={distPath} fill="none" stroke="#FFFFFF" strokeWidth={sw(1.1)} fillRule="evenodd" />}
                </svg>
              </div>
            </div>
            {/* shared overlays: permits + search radius + case point */}
            <div className="layer" style={{ pointerEvents: 'none' }}>
              <div className="content" style={scaleStyle}>
                <svg viewBox={`0 0 ${img.width} ${img.height}`} preserveAspectRatio="none" aria-hidden="true">
                  {ui.permits && permitPaths.map((p, i) => <path key={i} d={p.d} fill="rgba(154,163,168,0.08)" stroke="#E8EAE6" strokeWidth={sw(1.2)} strokeDasharray={`${sw(5)} ${sw(4)}`} />)}
                  {ui.aoi && circle && <path d={circle} fill="none" stroke="#FFFFFF" strokeOpacity="0.85" strokeWidth={sw(1.4)} strokeDasharray={`${sw(7)} ${sw(5)}`} />}
                  <circle cx={cx} cy={cy} r={sw(5)} fill="#17181A" stroke="#FFFFFF" strokeWidth={sw(2)} />
                </svg>
              </div>
            </div>
            {ui.aoi && cc && (
              <span className="tag mono" style={{ left: 10, top: 'auto', bottom: 10, fontWeight: 400, letterSpacing: 0 }}>AOI ≤{cc.radius_km} km · {ha(cc.disturbed_area_ha)} ha flagged</span>
            )}
            <span className="tag" style={{ left: 10 }}>BEFORE <span className="mono" style={{ fontWeight: 400, letterSpacing: 0 }}>{fmtDate(img.before_date)}</span></span>
            <span className="tag" style={{ right: 10 }}>AFTER <span className="mono" style={{ fontWeight: 400, letterSpacing: 0 }}>{fmtDate(img.after_date)}</span></span>
            <div aria-hidden="true" style={{ position: 'absolute', top: 0, bottom: 0, left: `${ui.split}%`, width: 2, marginLeft: -1, background: '#FFFFFF', boxShadow: '0 0 0 1px rgba(0,0,0,0.25)', pointerEvents: 'none', zIndex: 3 }} />
            <div aria-hidden="true" style={{ position: 'absolute', top: '50%', left: `${ui.split}%`, width: 34, height: 34, margin: '-17px 0 0 -17px', borderRadius: '50%', background: '#FFFFFF', boxShadow: '0 2px 8px rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none', zIndex: 3 }}>
              <svg width="18" height="18" viewBox="0 0 24 24"><path d="M9 7 L4 12 L9 17 M15 7 L20 12 L15 17" fill="none" stroke="#17181A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </div>
            <input type="range" min="0" max="100" step="1" value={ui.split} onChange={(e) => setUi({ ...ui, split: parseInt(e.target.value, 10) })} aria-label="Before/after divider position" />
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8, fontSize: 11 }} className="muted">
            <span>True colour B4/B3/B2, both dates re-aligned on GeoTIFF coordinates · drag the divider · black dot = case reference point</span>
            {ui.ndvi && (
              n ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontWeight: 600, letterSpacing: '0.06em' }}>ΔNDVI</span>
                <span className="mono">−0.6</span>
                <span aria-hidden="true" style={{ display: 'flex', height: 8, width: 120, borderRadius: 1, overflow: 'hidden', background: 'linear-gradient(90deg,#57106E,#BC3754,#F98E09)' }} />
                <span className="mono">−0.2</span>
              </span>
              ) : (
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span aria-hidden="true" style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'rgba(230,40,40,0.8)' }} />
                <span>pixels flagged "changed" by the model</span>
              </span>
              )
            )}
          </div>
        </section>

        {/* VEGETATION INDICES (NDVI run) or MODEL DETECTION (AI model run) */}
        <section aria-label="Detection signal" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <h2 className="eyebrow" style={{ margin: 0 }}>{n ? 'VEGETATION INDICES · WHOLE FRAME, BEFORE → AFTER' : 'AI MODEL DETECTION · FC-SIAM-DIFF V4'}</h2>
          {n ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
            {[
              ['NDVI mean', n.before.ndvi_mean, n.after.ndvi_mean, (v) => v.toFixed(3), 1],
              ['NDMI mean', n.before.ndmi_mean, n.after.ndmi_mean, (v) => v.toFixed(3), 1],
              ['Vegetated px', n.before.veg_pixel_frac, n.after.veg_pixel_frac, (v) => (v * 100).toFixed(1) + '%', 1],
              ['Sharp loss px', 0, n.sharp_ndvi_loss_pixel_fraction, (v) => (v * 100).toFixed(1) + '%', 0.3],
            ].map(([label, a, b, f, scale]) => (
              <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <div style={{ height: 34, display: 'flex', alignItems: 'flex-end', gap: 3, background: '#F5F5F2', borderRadius: 2, padding: '0 4px' }}>
                  <div title={`before ${f(a)}`} style={{ flex: 1, height: `${Math.max(2, Math.min(100, (Math.max(a, 0) / scale) * 100))}%`, background: '#B8BAB6', borderRadius: '2px 2px 0 0' }} />
                  <div title={`after ${f(b)}`} style={{ flex: 1, height: `${Math.max(2, Math.min(100, (Math.max(b, 0) / scale) * 100))}%`, background: '#4A4D52', borderRadius: '2px 2px 0 0' }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, gap: 4 }}>
                  <span className="muted">{label}</span>
                  <span className="mono" style={{ fontWeight: 500 }}>{label === 'Sharp loss px' ? f(b) : `${f(a)}→${f(b)}`}</span>
                </div>
              </div>
            ))}
          </div>
          ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1, height: 10, background: '#F5F5F2', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: `${Math.max(2, Math.min(100, (modelFrac || 0) * 100 * 2))}%`, height: '100%', background: '#4A4D52' }} />
              </div>
              <span className="mono" style={{ fontWeight: 600, fontSize: 12, minWidth: 48, textAlign: 'right' }}>{pct(modelFrac)}</span>
            </div>
            <span className="muted" style={{ fontSize: 11 }}>
              Share of frame pixels flagged "changed" by the model (checkpoint production_v4_base64_reg_jasansky, threshold 0.5).
              No NDVI/NDMI computed in this run — detection is the AI model's own output, not a vegetation-index proxy.
            </span>
          </div>
          )}
        </section>

        {/* PERMIT CROSS-CHECK */}
        <section aria-label="Permit cross-check" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
            <h2 className="eyebrow" style={{ margin: 0 }}>PERMIT CROSS-CHECK · BIG KSP, {cc ? cc.radius_km : c.nearby_radius_km} KM RADIUS</h2>
            <span className="muted" style={{ fontSize: 11 }}>Baseline ~2022 · validity judged at {fmtDate(img.after_date)}</span>
          </div>
          <div className="table">
            <div role="table" aria-label="Nearby permits">
              <div role="row" className="p-grid" style={{ background: '#F7F7F5', borderBottom: '1px solid #E2E2DE', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#5F6368' }}>
                <span role="columnheader" style={{ padding: '7px 12px' }}>PERMIT</span>
                <span role="columnheader" style={{ padding: '7px 8px' }}>STATUS</span>
                <span role="columnheader" style={{ padding: '7px 8px' }}>VALID UNTIL</span>
                <span role="columnheader" style={{ padding: '7px 8px', textAlign: 'right' }} title="From the case reference point to the permit boundary">DISTANCE</span>
                <span role="columnheader" style={{ padding: '7px 12px 7px 8px', textAlign: 'right' }}>OVERLAP W/ AOI</span>
              </div>
              {rows.length === 0 && <div style={{ padding: '12px', fontSize: 12 }} className="muted">No permit polygon within the search radius.</div>}
              {rows.map((p) => {
                const ps = PST[p.state] || PST.unknown;
                const ov = p.pct_of_disturbance == null ? null : p.pct_of_disturbance;
                return (
                  <div key={p.objectid} role="row" className="p-grid" style={{ alignItems: 'center', minHeight: 44, borderBottom: '1px solid #EFEFEB', fontSize: 12 }}>
                    <span role="cell" style={{ padding: '6px 12px', display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                      <span className="ellipsis" style={{ fontSize: 12, fontWeight: 600 }} title={p.name}>{p.name}</span>
                      <span className="mono muted ellipsis" style={{ fontSize: 10.5 }} title={p.sk}>{p.sk} · {p.type} · {p.commodity}</span>
                    </span>
                    <span role="cell" style={{ padding: '0 8px' }}><span className="pill" style={{ height: 18, background: ps.bg, color: ps.fg }}>{ps.label}</span></span>
                    <span role="cell" className="mono" style={{ padding: '0 8px', fontSize: 11.5, color: '#3D4044' }}>{fmtDate(p.valid_until)}</span>
                    <span role="cell" className="mono" style={{ padding: '0 8px', textAlign: 'right', fontSize: 11.5, color: '#3D4044' }}>{p.distance_km === 0 ? 'at point' : `${p.distance_km.toFixed(1)} km`}</span>
                    <span role="cell" style={{ padding: '0 12px 0 8px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                      {ov == null ? <span className="muted">—</span> : <>
                        <span aria-hidden="true" style={{ width: 52, height: 5, background: '#ECECE8', borderRadius: 1, overflow: 'hidden' }}><span style={{ display: 'block', height: '100%', width: `${Math.min(100, ov)}%`, background: '#17181A' }} /></span>
                        <span className="mono" style={{ fontSize: 12, fontWeight: 600, width: 40, textAlign: 'right' }}>{Math.round(ov)}%</span>
                      </>}
                    </span>
                  </div>
                );
              })}
            </div>
            {cc && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 1, background: '#E2E2DE' }}>
                {[['INSIDE ACTIVE PERMIT', cc.in_active_ha], ['INSIDE EXPIRED PERMIT', cc.in_expired_ha], ['NO PERMIT COVERAGE', cc.no_permit_ha]].map(([l, v]) => (
                  <div key={l} style={{ background: '#FAFAF8', padding: '9px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#5F6368' }}>{l}</span>
                    <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{ha(v)} ha{share(v)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <span className="muted" style={{ fontSize: 11 }}>
            {c.status_rule_text} Out-of-permit area may be unpermitted activity <i>or</i> incomplete permit data — analyst verification required.
            {cc && cc.repo_reference && <> Reproduces the published repo figure ({cc.repo_reference.disturbed_ha} ha, {cc.repo_reference.pct_outside}% outside).</>}
          </span>
        </section>

        {/* GROUND TRUTH */}
        <section aria-label="Ground-truth reference" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <h2 className="eyebrow" style={{ margin: 0 }}>GROUND-TRUTH REFERENCE (PUBLIC REPORTING)</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '120px minmax(0,1fr)', gap: '4px 12px', fontSize: 12 }}>
            <span className="muted">Reported status</span><span>{c.gt_status}</span>
            <span className="muted">Reported area</span><span className="tnum">{c.gt_area_ha ? `${ha(c.gt_area_ha)} ha` : 'not reported'}</span>
            <span className="muted">Location precision</span><span>{c.loc_precision}</span>
            <span className="muted">Sources</span><span>{c.sources.join(' · ')}</span>
          </div>
        </section>

        {/* DISPATCH GATE */}
        <section aria-label="Analyst review" className="gate">
          <div className="gate-h">
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="1.5" fill="none" stroke="#FFFFFF" strokeWidth="1.8" /><path d="M8 10.5 V7.5 a4 4 0 0 1 8 0 V10.5" fill="none" stroke="#FFFFFF" strokeWidth="1.8" /></svg>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.09em' }}>ANALYST REVIEW · HUMAN DECISION REQUIRED</span>
            </div>
            <span style={{ fontSize: 11, color: '#C9CBC7' }}>Alert integration not built — dispatch is a mock</span>
          </div>

          {!dec && (
            <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 14, background: '#fff' }}>
              <ol className="steps">
                {steps.map((t) => (
                  <li key={t.label} style={{ background: t.done ? '#F1F1EE' : '#FFFFFF', color: t.done || t.active ? '#17181A' : '#5F6368' }}>
                    <span className="dot" aria-hidden="true" style={{ borderColor: t.done || t.active ? '#17181A' : '#B8BAB6', background: t.done ? '#17181A' : '#FFFFFF' }}>{t.done ? '✓' : ''}</span>
                    {t.label}<span className="sr">{t.done ? '(done)' : '(pending)'}</span>
                  </li>
                ))}
              </ol>
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.3fr)', gap: 14 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <span className="field-lab">1 · DECISION</span>
                    <select value={d} onChange={(e) => setForm({ ...form, decision: e.target.value })} style={{ height: 36, padding: '0 10px', border: `1px solid ${d ? '#17181A' : '#B8BAB6'}`, borderRadius: 4, background: '#FFFFFF', fontSize: 13, fontWeight: 500 }}>
                      <option value="">Select a decision…</option>
                      {Object.entries(DECISIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <span className="field-lab">RECIPIENTS <span className="mock-tag" style={{ marginLeft: 4 }}>MOCK</span></span>
                    {recipients.map((r) => (
                      <div key={r} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: closing ? '#8A8D91' : '#17181A', textDecoration: closing ? 'line-through' : 'none' }}>
                        <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6 H20 V18 H4 Z M4 7 L12 13 L20 7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /></svg>{r}
                      </div>
                    ))}
                    <span className="muted" style={{ fontSize: 11 }}>{closing ? 'Not notified — closing decisions stay internal.' : 'Routed by province. Nothing is actually sent yet.'}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <span className="field-lab">ANALYST NOTES <span className="muted" style={{ fontWeight: 500, letterSpacing: 0 }}>· stored with the decision and in the report</span></span>
                    <textarea className="notes" rows="5" value={form.notes} maxLength={4000} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Evidence summary, access route, nearest settlement, recommended action…" />
                  </label>
                  <label style={{ display: 'flex', alignItems: 'flex-start', gap: 9, fontSize: 12, cursor: 'pointer' }}>
                    <input type="checkbox" checked={form.ack} onChange={(e) => setForm({ ...form, ack: e.target.checked })} style={{ width: 16, height: 16, margin: '1px 0 0', accentColor: '#17181A' }} />
                    <span><b style={{ fontWeight: 600 }}>2 · I have reviewed</b> the before/after imagery, NDVI change and permit overlap for {c.id}, and take responsibility for this decision.</span>
                  </label>
                </div>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingTop: 12, borderTop: '1px solid #E2E2DE' }}>
                <span className="muted" style={{ fontSize: 11.5, maxWidth: 330 }}>
                  {gateHint} {!analyst && <button type="button" className="link-id" style={{ fontFamily: 'inherit' }} onClick={onEditAnalyst}>Set name</button>}
                </span>
                <button type="button" onClick={submit} disabled={!ready || busy} aria-disabled={!ready || busy}
                  style={{ height: 40, padding: '0 18px', display: 'flex', alignItems: 'center', gap: 9, border: `1.5px solid ${ready ? '#17181A' : '#D8D8D3'}`, borderRadius: 4, background: !ready ? '#ECECE8' : closing ? '#FFFFFF' : '#17181A', color: !ready ? '#6B6E73' : closing ? '#17181A' : '#FFFFFF', fontSize: 13, fontWeight: 600, cursor: ready ? 'pointer' : 'not-allowed' }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path d={!ready ? lockIcon : closing ? closeIcon : sendIcon} fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  3 · {busy ? 'Saving…' : closing ? 'Close case — no alert' : 'Record alert (mock — not sent)'}
                </button>
              </div>
              {actErr && <span className="err">{actErr}</span>}
            </div>
          )}

          {dec && (
            <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10, background: '#FAFAF8' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span aria-hidden="true" style={{ width: 22, height: 22, borderRadius: '50%', background: '#17181A', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><svg width="12" height="12" viewBox="0 0 24 24"><path d="M5 12.5 L10 17 L19 7" fill="none" stroke="#FFFFFF" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{dec.dispatch === 'mock_alert' ? 'Alert recorded — NOT sent (mock)' : 'Case closed — no alert'}</span>
                {dec.dispatch === 'mock_alert' && <span className="mock-tag">MOCK · NO MESSAGE LEFT MINEWATCH</span>}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '120px minmax(0, 1fr)', gap: '4px 12px', fontSize: 12 }}>
                <span className="muted">Reference</span><span className="mono">{dec.ref}</span>
                <span className="muted">Decision</span><span>{DECISIONS[dec.decision]}</span>
                <span className="muted">Signed by</span><span>{dec.actor}</span>
                <span className="muted">Timestamp</span><span className="mono">{fmtDateTime(dec.created_at)}</span>
                <span className="muted">Notes</span><span style={{ whiteSpace: 'pre-wrap' }}>{dec.notes || '—'}</span>
              </div>
              <div>
                <button type="button" className="btn" disabled={recallLeft <= 0 || busy} onClick={recall} style={{ height: 30, fontSize: 12 }}>
                  {recallLeft > 0 ? `Recall (${Math.ceil(recallLeft / 60)} min left)` : 'Recall window (10 min) has passed'}
                </button>
              </div>
              {actErr && <span className="err">{actErr}</span>}
            </div>
          )}
        </section>

        {/* FOOTER ACTIONS */}
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <a className="btn" href={`/api/cases/${encodeURIComponent(c.id)}/report`} target="_blank" rel="noreferrer" style={{ height: 34, borderColor: '#C9C9C4' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3 H6 V21 H18 V7 Z M14 3 V7 H18 M12 11 V17 M9 14 L12 17 L15 14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
              Generate PDF report
            </a>
            {reassign == null ? (
              <button type="button" className="btn" style={{ height: 34, borderColor: '#C9C9C4' }} onClick={() => setReassign(c.review.assignee || analyst || '')}>
                {c.review.assignee ? `Assigned: ${c.review.assignee} · Reassign…` : 'Assign…'}
              </button>
            ) : (
              <span style={{ display: 'flex', gap: 6 }}>
                <input autoFocus value={reassign} onChange={(e) => setReassign(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doAssign()} placeholder="Analyst name" maxLength={80}
                  style={{ height: 34, padding: '0 10px', border: '1px solid #C9C9C4', borderRadius: 4, fontSize: 12.5, width: 160 }} />
                <button type="button" className="btn btn-dark" style={{ height: 34 }} onClick={doAssign} disabled={busy}>Save</button>
                <button type="button" className="btn" style={{ height: 34 }} onClick={() => setReassign(null)}>Cancel</button>
              </span>
            )}
          </div>
          <button type="button" onClick={() => setShowAudit(!showAudit)} className="mono muted" style={{ fontSize: 11, border: 0, background: 'transparent', cursor: 'pointer', padding: 0 }}>
            audit: {c.audit.length} events{created ? ` since ${fmtDateTime(created.at)}` : ''} · viewed by {c.viewers} analyst{c.viewers === 1 ? '' : 's'} {showAudit ? '▴' : '▾'}
          </button>
        </div>
        {showAudit && (
          <div className="table" style={{ fontSize: 11.5 }}>
            {c.audit.length === 0 && <div style={{ padding: 10 }} className="muted">No events yet.</div>}
            {c.audit.map((a) => (
              <div key={a.id} style={{ display: 'grid', gridTemplateColumns: '140px 90px 140px minmax(0,1fr)', gap: 8, padding: '6px 10px', borderBottom: '1px solid #EFEFEB' }}>
                <span className="mono muted">{fmtDateTime(a.at)}</span><span style={{ fontWeight: 600 }}>{a.event}</span><span className="ellipsis">{a.actor}</span><span className="ellipsis muted" title={a.detail}>{a.detail}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
