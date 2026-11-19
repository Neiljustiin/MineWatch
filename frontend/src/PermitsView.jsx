import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { api, fmtDate, dms, ha, PST } from './lib.js';

function PermitMap({ feature }) {
  const el = useRef(null);
  useEffect(() => {
    if (!el.current || !feature) return;
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, preferCanvas: true, minZoom: 3, maxZoom: 17 });
    const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
    L.tileLayer(esri + 'World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 17, attribution: 'Tiles &copy; Esri, Maxar, Earthstar Geographics',
    }).addTo(m);
    const layer = L.geoJSON(feature, {
      style: { color: '#2F5BD3', weight: 2.2, fillColor: '#2F5BD3', fillOpacity: 0.22 },
    }).addTo(m);
    const b = layer.getBounds();
    if (b.isValid()) m.fitBounds(b.pad(0.35)); else m.setView([feature.centroid.lat, feature.centroid.lon], 11);
    return () => m.remove();
  }, [feature]);
  return <div ref={el} aria-label="Permit location map" style={{ height: 420, width: '100%' }} />;
}

function PermitDetail({ objectid, onClose }) {
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setP(null); setErr(null);
    api(`/api/permits/${objectid}`).then(setP).catch((e) => setErr(e.message));
  }, [objectid]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const ps = p ? (PST[p.state_today] || PST.unknown) : null;
  const feature = p ? { type: 'Feature', geometry: p.geometry, properties: {}, centroid: p.centroid } : null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, boxSizing: 'border-box', background: 'rgba(23,24,26,0.55)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label="Permit detail" className="mw-scroll"
        style={{ width: '100%', maxWidth: 980, maxHeight: '92vh', overflowY: 'auto', background: '#fff', borderRadius: 8, boxShadow: '0 24px 64px rgba(0,0,0,0.35)' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, padding: '18px 26px', borderBottom: '1px solid #E2E2DE' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }} className="muted">
              <span>Permits database</span><span aria-hidden="true" style={{ color: '#A3A6AA' }}>/</span>
              <span className="mono" style={{ color: '#17181A', fontWeight: 500 }}>OBJ-{objectid}</span>
            </div>
            {p && (
              <>
                <h1 style={{ margin: 0, fontSize: 22, fontWeight: 650, letterSpacing: '-0.02em' }}>{p.name}</h1>
                <span style={{ fontSize: 13, color: '#4A4D52' }}>{p.kab || '—'}, {p.prov || '—'} · <span className="mono muted">{p.skblok || 'no SK recorded'}</span></span>
              </>
            )}
          </div>
          <button type="button" className="sq-btn" aria-label="Close permit detail" onClick={onClose} style={{ flex: '0 0 auto' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 L18 18 M18 6 L6 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
        </header>

        <div style={{ padding: '20px 26px', display: 'flex', flexDirection: 'column', gap: 18 }}>
          {err && <div className="banner">Error: {err}</div>}
          {!p && !err && <div className="muted">Loading…</div>}
          {p && (
            <>
              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <PermitMap feature={feature} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px 20px', fontSize: 13.5 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>TYPE</span>
                  <span>{p.tiptmb || '—'}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>COMMODITY</span>
                  <span>{p.commodity || '—'}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>AREA</span>
                  <span className="mono">{ha(p.area_ha)} ha</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>VALID UNTIL</span>
                  <span className="mono">{fmtDate(p.valid_until)}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>STATE TODAY</span>
                  <span><span className="pill" style={{ background: ps.bg, color: ps.fg }}>{ps.label}</span></span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>SOURCE</span>
                  <span>{p.admin_added ? 'Added by Admin' : 'BIG Kebijakan Satu Peta baseline'}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3, gridColumn: '1 / -1' }}>
                  <span className="muted" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>CENTROID COORDINATES</span>
                  <span className="mono">
                    {dms(p.centroid.lat, 'N', 'S')} · {dms(p.centroid.lon, 'E', 'W')}
                    <span className="muted" style={{ marginLeft: 8 }}>({p.centroid.lat.toFixed(5)}, {p.centroid.lon.toFixed(5)})</span>
                  </span>
                </div>
              </div>

              <span className="muted" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
                Polygon from the BIG Kebijakan Satu Peta snapshot (~2022), not real-time. "State today" compares the
                recorded end date with today's date only — it is not a live legal-status check.
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PermitsView() {
  const [q, setQ] = useState('');
  const [prov, setProv] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api(`/api/permits/search?q=${encodeURIComponent(q)}&prov=${encodeURIComponent(prov)}&page=${page}&size=50`)
        .then((d) => { setData(d); setErr(null); }).catch((e) => setErr(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [q, prov, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  return (
    <main className="page">
      <div className="page-h">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <h1>Permits database</h1>
          <span className="muted" style={{ fontSize: 12 }}>BIG Kebijakan Satu Peta IUP/IUPK polygons — public snapshot ~2022, <b>not real-time</b>. "State today" compares the recorded end date with today's date only. Click a row for details and the location on the map.</span>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Company, SK number, kabupaten, commodity…"
            style={{ height: 32, padding: '0 10px', border: '1px solid #D8D8D3', borderRadius: 4, width: 300, fontSize: 12.5 }} />
          <select className="select" value={prov} onChange={(e) => { setProv(e.target.value); setPage(1); }}>
            <option value="">All provinces</option>
            {data && data.provinces.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>
      {err && <div className="banner">Error: {err}</div>}
      <section className="card reg">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', borderBottom: '1px solid #E2E2DE' }}>
          <h2>{data ? data.total.toLocaleString('en-US') : '…'} permits</h2>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
            <span className="mono muted" style={{ fontSize: 11.5 }}>{page} / {pages}</span>
            <button className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next ›</button>
          </div>
        </div>
        <div className="mw-scroll" style={{ overflowX: 'auto' }}>
          <div role="table" style={{ minWidth: 900 }}>
            <div role="row" className="pdb-grid reg-head">
              <span role="columnheader" style={{ paddingLeft: 14 }}>PERMIT HOLDER · SK</span><span role="columnheader">KABUPATEN · PROVINCE</span>
              <span role="columnheader">TYPE</span><span role="columnheader">COMMODITY</span><span role="columnheader">VALID UNTIL</span><span role="columnheader">STATE TODAY</span>
            </div>
            {data && data.items.map((p) => {
              const ps = PST[p.state_today] || PST.unknown;
              return (
                <button key={p.objectid} type="button" role="row" className="pdb-grid reg-row" onClick={() => setSelected(p.objectid)}
                  style={{ appearance: 'none', margin: 0, padding: 0, border: 0, borderBottom: '1px solid #EFEFEB', background: 'transparent', font: 'inherit', textAlign: 'left', cursor: 'pointer', width: '100%' }}>
                  <span role="cell" style={{ paddingLeft: 14, display: 'flex', flexDirection: 'column', minWidth: 0, padding: '5px 10px 5px 14px' }}>
                    <span className="ellipsis" style={{ fontWeight: 500 }}>{p.name || '(name not recorded)'}</span>
                    <span className="mono muted ellipsis" style={{ fontSize: 10.5 }}>{p.skblok || '—'}</span>
                  </span>
                  <span role="cell" className="ellipsis" style={{ color: '#3D4044' }}>{p.kab || '—'} · {p.prov || '—'}</span>
                  <span role="cell" className="ellipsis">{p.tiptmb || '—'}</span>
                  <span role="cell" className="ellipsis">{p.commodity || '—'}</span>
                  <span role="cell" className="mono" style={{ fontSize: 11.5 }}>{fmtDate(p.valid_until)}</span>
                  <span role="cell"><span className="pill" style={{ background: ps.bg, color: ps.fg }}>{ps.label}</span></span>
                </button>
              );
            })}
            {data && data.items.length === 0 && <div style={{ padding: 20, textAlign: 'center' }} className="muted">No permits match.</div>}
          </div>
        </div>
      </section>
      {selected != null && <PermitDetail objectid={selected} onClose={() => setSelected(null)} />}
    </main>
  );
}
