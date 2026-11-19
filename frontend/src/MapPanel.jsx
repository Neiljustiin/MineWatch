import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import { ST, STATUSES, COM, ha, pct, api, fmtDate, fmtDateTime } from './lib.js';

const INDONESIA = [[-11.2, 94.5], [6.3, 141.2]];

function markerHtml(c, active) {
  const st = ST[c.status] || ST.UNCHECKED;
  const size = (c.area_ha || 0) > 300 ? 14 : 12;
  const ring = active ? '0 0 0 4px rgba(255,255,255,0.32), ' : '';
  return `<div class="mw-marker"><span style="width:${size}px;height:${size}px;background:${st.map};border-radius:${st.rad};transform:rotate(${st.rot});box-shadow:${ring}0 1px 3px rgba(0,0,0,.5)"></span></div>`;
}

export default function MapPanel({ cases, base, on, setOn, callout, setCallout, sel, setSel, openCase, meta }) {
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const permitLayer = useRef(null);
  const baseLayers = useRef(null);
  const fitted = useRef(false);
  const [basemap, setBasemap] = useState('dark');
  const [showPermits, setShowPermits] = useState(false);
  const [permitState, setPermitState] = useState('idle'); // idle | loading | ready | error
  const [zoom, setZoom] = useState(5);
  const [, force] = useState(0);

  // init
  useEffect(() => {
    const m = L.map(el.current, { zoomControl: false, attributionControl: true, preferCanvas: true, minZoom: 4, maxZoom: 16, worldCopyJump: false });
    const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
    const att = 'Tiles &copy; Esri — Esri, HERE, Garmin, &copy; OpenStreetMap contributors';
    baseLayers.current = {
      dark: L.layerGroup([
        L.tileLayer(esri + 'Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16, attribution: att }),
        L.tileLayer(esri + 'Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16, opacity: 0.7, pane: 'shadowPane' }),
      ]),
      sat: L.tileLayer(esri + 'World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 18, attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics' }),
    };
    baseLayers.current.dark.addTo(m);
    L.control.scale({ position: 'bottomright', imperial: false, maxWidth: 90 }).addTo(m);
    m.fitBounds(INDONESIA);
    layer.current = L.layerGroup().addTo(m);
    m.on('zoomend moveend', () => { setZoom(m.getZoom()); force((x) => x + 1); });
    m.on('click', () => setCallout(null));
    map.current = m;
    setZoom(m.getZoom());
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(el.current);
    return () => { ro.disconnect(); m.remove(); };
  }, []);

  // markers
  useEffect(() => {
    const g = layer.current;
    if (!g) return;
    g.clearLayers();
    cases.forEach((c) => {
      const mk = L.marker([c.lat, c.lon], {
        icon: L.divIcon({ className: '', html: markerHtml(c, callout === c.id), iconSize: [24, 24], iconAnchor: [12, 12] }),
        keyboard: true, title: `${(ST[c.status] || ST.UNCHECKED).label} — ${c.loc}, ${c.prov}`, riseOnHover: true,
      });
      mk.on('click', (e) => { L.DomEvent.stopPropagation(e); setSel(c.id); setCallout(callout === c.id ? null : c.id); });
      mk.on('dblclick', (e) => { L.DomEvent.stopPropagation(e); openCase(c.id); });
      g.addLayer(mk);
    });
    // first render: frame the pilot sites instead of the whole archipelago
    if (!fitted.current && cases.length) {
      fitted.current = true;
      map.current.fitBounds(L.latLngBounds(cases.map((c) => [c.lat, c.lon])).pad(0.12), { maxZoom: 7 });
    }
  }, [cases, callout]);

  useEffect(() => {
    const m = map.current, b = baseLayers.current;
    if (!m || !b) return;
    Object.entries(b).forEach(([k, l]) => { if (k === basemap) { if (!m.hasLayer(l)) l.addTo(m); } else if (m.hasLayer(l)) m.removeLayer(l); });
  }, [basemap]);

  // permits layer (national, 4,608 polygons, canvas-rendered)
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (!showPermits) { if (permitLayer.current) m.removeLayer(permitLayer.current); return; }
    if (permitLayer.current) { permitLayer.current.addTo(m); return; }
    setPermitState('loading');
    api('/api/permits/all').then((gj) => {
      const today = new Date().toISOString().slice(0, 10);
      permitLayer.current = L.geoJSON(gj, {
        renderer: L.canvas({ padding: 0.3 }),
        style: (f) => ({ color: '#AEB6BA', weight: 0.8, dashArray: '3 2.4', fillColor: '#9AA3A8', fillOpacity: f.properties.valid_until && f.properties.valid_until < today ? 0.04 : 0.1 }),
        onEachFeature: (f, lyr) => {
          const p = f.properties;
          lyr.bindTooltip(`<b>${p.name || '(no name)'}</b><br>${p.skblok || ''}<br>${p.commodity || ''} · valid until ${p.valid_until || '—'}`, { sticky: true, className: 'mw-tip' });
        },
      });
      permitLayer.current.addTo(m);
      permitLayer.current.bringToBack();
      setPermitState('ready');
    }).catch(() => setPermitState('error'));
  }, [showPermits]);

  // fly to callout when picked from elsewhere (feed / register)
  useEffect(() => {
    const m = map.current;
    if (!m || !sel) return;
    const c = cases.find((x) => x.id === sel);
    if (c && !m.getBounds().pad(-0.1).contains([c.lat, c.lon])) m.panTo([c.lat, c.lon]);
  }, [sel]);

  const c0 = callout ? cases.find((c) => c.id === callout) : null;
  let pos = null;
  if (c0 && map.current) {
    const pt = map.current.latLngToContainerPoint([c0.lat, c0.lon]);
    const w = el.current ? el.current.clientWidth : 800;
    pos = { left: pt.x, top: pt.y, right: pt.x > w * 0.62 };
  }
  const countBy = (k) => base.filter((c) => c.status === k).length;
  const legendKeys = [...STATUSES, ...(countBy('UNCHECKED') ? ['UNCHECKED'] : [])];

  return (
    <>
      <div className="map-bar">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', color: '#C2C4C0' }}>DETECTIONS MAP</span>
          <span className="tnum" style={{ fontSize: 11.5, color: '#A9ACA8' }}>{cases.length} sites shown</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button type="button" className="map-btn" aria-pressed={showPermits} onClick={() => setShowPermits(!showPermits)}>
            <svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray="3 2.4" /></svg>
            Permit concessions{permitState === 'loading' ? ' …' : permitState === 'error' ? ' (failed)' : ''}
          </button>
          <button type="button" className="map-btn" aria-pressed={basemap === 'sat'} onClick={() => setBasemap(basemap === 'sat' ? 'dark' : 'sat')}>Satellite</button>
          <button type="button" className="map-btn" onClick={() => map.current && map.current.fitBounds(INDONESIA)}>Indonesia</button>
          <div style={{ display: 'flex', border: '1px solid #3A3F44', borderRadius: 3, overflow: 'hidden' }}>
            <button type="button" aria-label="Zoom in" onClick={() => map.current.zoomIn()} style={{ width: 26, height: 24, border: 0, borderRight: '1px solid #3A3F44', background: '#262A2E', color: '#E2E3E0', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}>+</button>
            <button type="button" aria-label="Zoom out" onClick={() => map.current.zoomOut()} style={{ width: 26, height: 24, border: 0, background: '#262A2E', color: '#E2E3E0', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}>−</button>
          </div>
        </div>
      </div>
      {meta && (
        <div className="map-fresh">
          <span className="fresh-item"><span>Latest S2 L2A scene</span><span>{fmtDate(meta.latest_after_date)}</span></span>
          <span className="div" aria-hidden="true" />
          <span className="fresh-item"><span>Permit baseline</span><span>BIG KSP ~2022</span></span>
          <span className="div" aria-hidden="true" />
          <span className="fresh-item"><span>Data built</span><span>{fmtDateTime(meta.generated_at)}</span></span>
        </div>
      )}
      <div className="map-wrap">
        <div ref={el} style={{ position: 'absolute', inset: 0 }} />
        <div className="map-note">EPSG:4326 · z{zoom} · Esri {basemap === 'sat' ? 'World Imagery' : 'Dark Gray'}</div>

        {c0 && pos && (
          <div className="callout" style={{ left: pos.left, top: pos.top, transform: `translate(${pos.right ? 'calc(-100% - 16px)' : '16px'}, -50%)` }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span className="mono muted" style={{ fontSize: 10.5 }}>{c0.id}</span>
              <span className="pill" style={{ height: 18, background: ST[c0.status].bg, color: ST[c0.status].fg }}>
                <span className="mk" style={{ background: ST[c0.status].dot, borderRadius: ST[c0.status].rad, transform: `rotate(${ST[c0.status].rot})` }} />{ST[c0.status].label}
              </span>
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.25 }}>{c0.loc}</div>
            <div className="muted" style={{ fontSize: 11.5 }}>{c0.kab}, {c0.prov}</div>
            <div className="tnum" style={{ display: 'flex', gap: 12, fontSize: 11.5, flexWrap: 'wrap' }}>
              <span><b style={{ fontWeight: 600 }}>{pct(c0.sharp_loss)}</b> {meta?.checkpoint ? 'model flagged' : 'NDVI loss'}</span>
              <span><b style={{ fontWeight: 600 }}>{ha(c0.area_ha)}</b> ha</span>
              <span>{COM[c0.com]}</span>
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 2 }}>
              <button type="button" onClick={() => openCase(c0.id)} style={{ flex: 1, height: 28, border: 0, borderRadius: 4, background: '#17181A', color: '#FFFFFF', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Open case</button>
              <button type="button" onClick={() => setCallout(null)} aria-label="Dismiss" style={{ width: 28, height: 28, border: '1px solid #D8D8D3', borderRadius: 4, background: '#FFFFFF', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}>×</button>
            </div>
          </div>
        )}

        <div role="group" aria-label="Map legend and filters" className="legend">
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 6px 4px', fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', color: '#A9ACA8' }}>
            <span>LEGEND</span><span style={{ fontWeight: 500, letterSpacing: '0.02em' }}>click to filter</span>
          </div>
          {legendKeys.map((k) => (
            <button key={k} type="button" aria-pressed={on[k]} style={{ opacity: on[k] ? 1 : 0.45 }} onClick={() => setOn({ ...on, [k]: !on[k] })}>
              <span aria-hidden="true" style={{ width: 14, display: 'flex', justifyContent: 'center' }}>
                <span style={{ width: 10, height: 10, background: ST[k].map, borderRadius: ST[k].rad, transform: `rotate(${ST[k].rot})`, border: '1.5px solid #FFFFFF', boxSizing: 'border-box' }} />
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, flex: 1 }}>{ST[k].label}</span>
              <span className="mono" style={{ fontSize: 10.5, color: '#A9ACA8' }}>{countBy(k)}</span>
            </button>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, height: 22, padding: '0 6px', fontSize: 11, color: '#A9ACA8', opacity: showPermits ? 1 : 0.45 }}>
            <span aria-hidden="true" style={{ width: 14, height: 9, border: '1px dashed #AEB6BA', boxSizing: 'border-box' }} />Permit concession (BIG KSP ~2022)
          </div>
        </div>
      </div>
    </>
  );
}
