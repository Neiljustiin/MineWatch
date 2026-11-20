import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ST, STATUSES, COM, QUALITY, fmtDate, fmtDateTime, ha, pct, monthIndex, monthName, initials, modelLabel } from './lib.js';
import MapPanel from './MapPanel.jsx';
import CasePanel from './CasePanel.jsx';
import PermitsView from './PermitsView.jsx';
import SettingsView from './SettingsView.jsx';
import AdminView from './AdminView.jsx';
import { DisturbanceChart, GroundTruthChart } from './Analytics.jsx';
import { StatusPill } from './ui.jsx';

const NAV_TOP = [
  { key: 'dash', label: 'Dashboard', icon: 'M9 4 L3 6 V20 L9 18 L15 20 L21 18 V4 L15 6 Z M9 4 V18 M15 6 V20' },
];
const NAV_SUB = [
  { key: 'reports', label: 'Reports', icon: 'M4 20 H20 M7 16 V11 M12 16 V7 M17 16 V9' },
  { key: 'cases', label: 'Cases', icon: 'M8 6 H20 M8 12 H20 M8 18 H20 M4 6 H4.01 M4 12 H4.01 M4 18 H4.01' },
];
const NAV_BOTTOM = [
  { key: 'permits', label: 'Permits Database', icon: 'M14 3 H6 V21 H18 V7 Z M14 3 V7 H18 M9 13 H15 M9 17 H13' },
  { key: 'settings', label: 'Settings', icon: 'M4 7 H13 M17 7 H20 M4 17 H7 M11 17 H20 M15 5 V9 M9 15 V19' },
];
const NAV_ADMIN = { key: 'admin', label: 'Admin', adminTag: true, icon: 'M12 3 L19 6 V12 C19 16.5 16 19.5 12 21 C8 19.5 5 16.5 5 12 V6 Z M9.5 12 L11.5 14 L15 10' };
const NAV = [...NAV_TOP, ...NAV_SUB, ...NAV_BOTTOM, NAV_ADMIN];

function parseHash() {
  const h = window.location.hash.replace(/^#\/?/, '');
  const [path, q] = h.split('?');
  const params = new URLSearchParams(q || '');
  return { view: ['permits', 'settings', 'admin'].includes(path) ? path : 'dash', caseId: params.get('case') };
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [cases, setCases] = useState(null);
  const [err, setErr] = useState(null);
  const [route, setRoute] = useState(parseHash);
  const [analyst, setAnalyst] = useState(() => localStorage.getItem('mw.analyst') || '');
  const [role, setRole] = useState('');
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState('');
  const [prov, setProv] = useState('ALL');
  const [on, setOn] = useState({ HIGH: true, MEDIUM: true, LOW: true, UNCHECKED: true });
  const [tab, setTab] = useState('ALL');
  const [win, setWin] = useState(null); // [lo, hi) month offsets
  const [customRange, setCustomRange] = useState(null); // inclusive YYYY-MM-DD dates
  const [sel, setSel] = useState(null);
  const [callout, setCallout] = useState(null);
  const [sort, setSort] = useState({ key: 'date', dir: -1 });
  const [section, setSection] = useState('top'); // 'top' | 'register' | 'analytics' — tracks which dash section is in view, for Cases/Reports nav highlight
  const searchRef = useRef(null);

  const reload = useCallback(() => api('/api/cases').then(setCases).catch((e) => setErr(e.message)), []);
  useEffect(() => { api('/api/meta').then(setMeta).catch((e) => setErr(e.message)); reload(); }, [reload]);
  useEffect(() => { api('/api/auth/me').then((d) => { setAnalyst(d.username); setRole(d.role || 'Analyst'); }); }, []);
  useEffect(() => {
    const f = () => setRoute(parseHash());
    window.addEventListener('hashchange', f);
    return () => window.removeEventListener('hashchange', f);
  }, []);
  // Track which section (Dashboard top / Cases register / Reports analytics) is currently in view while scrolling
  useEffect(() => {
    if (route.view !== 'dash') return;
    const targets = ['register', 'analytics'].map((id) => document.getElementById(id)).filter(Boolean);
    if (!targets.length) return;
    const obs = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setSection(visible.target.id);
      else if (window.scrollY < 200) setSection('top');
    }, { rootMargin: '-96px 0px -60% 0px', threshold: [0, 0.1, 0.3] });
    targets.forEach((t) => obs.observe(t));
    return () => obs.disconnect();
  }, [route.view, cases]);
  useEffect(() => {
    const f = (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); searchRef.current && searchRef.current.focus(); } };
    window.addEventListener('keydown', f);
    return () => window.removeEventListener('keydown', f);
  }, []);
  useEffect(() => { localStorage.setItem('mw.analyst', analyst); }, [analyst]);

  const go = (view, caseId) => {
    const q = caseId ? `?case=${encodeURIComponent(caseId)}` : '';
    window.location.hash = `#/${view === 'dash' ? '' : view}${q}`;
  };
  const openCase = (id) => { setSel(id); setCallout(id); go(route.view === 'dash' ? 'dash' : route.view, id); };
  const closeCase = () => go(route.view);

  // ---- timeline months: earliest -> latest after-image date
  const months = useMemo(() => {
    if (!cases || !cases.length) return [];
    const idx = cases.map((c) => monthIndex(c.after_date));
    const a = Math.min(...idx), b = Math.max(...idx);
    const out = [];
    for (let i = a; i <= b; i++) out.push({ idx: i, y: Math.floor(i / 12), m: i % 12 });
    return out;
  }, [cases]);
  useEffect(() => { if (months.length && !win) setWin([0, months.length]); }, [months, win]);

  if (err) return <div className="page"><div className="banner">API error: {err}. Is the backend running?</div></div>;
  if (!cases || !meta || !win) return <div className="page muted">Loading MineWatch…</div>;

  const m0 = months[0].idx;
  const nMonths = months.length;
  const clampMonth = (i) => Math.max(0, Math.min(nMonths, i));
  const [lo, hi] = customRange
    ? [clampMonth(monthIndex(customRange.from) - m0), clampMonth(monthIndex(customRange.to) - m0 + 1)]
    : win;
  const setMonthWindow = (next) => { setCustomRange(null); setWin(next); };
  const q = query.trim().toLowerCase();
  const inWin = (c) => {
    if (customRange) {
      const day = c.after_date.slice(0, 10);
      return day >= customRange.from && day <= customRange.to;
    }
    const i = monthIndex(c.after_date) - m0;
    return i >= lo && i < hi;
  };
  const periodCases = cases.filter(inWin);
  // "lat, lon" query -> cases within 25 km (haversine)
  const cm = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/);
  const near = (c) => {
    const [la, lo2] = [parseFloat(cm[1]), parseFloat(cm[2])], r = Math.PI / 180;
    const a = Math.sin(((c.lat - la) * r) / 2) ** 2 + Math.cos(la * r) * Math.cos(c.lat * r) * Math.sin(((c.lon - lo2) * r) / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(a)) <= 25;
  };
  const matches = (c) => !q || (cm ? near(c) : null) || [c.id, c.loc, c.kab, c.prov, COM[c.com], c.com, `${c.lat}, ${c.lon}`, ...(c.operators || []), ...(c.permit_nos || [])]
    .join(' ').toLowerCase().includes(q);
  const base = periodCases.filter((c) => (prov === 'ALL' || c.prov === prov) && matches(c));
  const visible = base.filter((c) => on[c.status]);
  const countBy = (arr, k) => arr.filter((c) => c.status === k).length;

  const feed = (tab === 'ALL' ? visible : visible.filter((c) => c.status === tab))
    .slice().sort((a, b) => b.after_date.localeCompare(a.after_date) || a.id.localeCompare(b.id));
  const table = visible.slice().sort((a, b) => {
    const d = sort.dir;
    if (sort.key === 'area') return ((a.area_ha || 0) - (b.area_ha || 0)) * d;
    if (sort.key === 'loss') return (a.sharp_loss - b.sharp_loss) * d;
    if (sort.key === 'out') return ((a.pct_outside || 0) - (b.pct_outside || 0)) * d;
    return a.after_date.localeCompare(b.after_date) * d;
  });
  const sortBy = (k) => () => setSort((s) => ({ key: k, dir: s.key === k ? -s.dir : -1 }));
  const arrow = (k) => (sort.key === k ? (sort.dir < 0 ? '↓' : '↑') : '');
  const ariaSort = (k) => (sort.key === k ? (sort.dir < 0 ? 'descending' : 'ascending') : 'none');

  const flagged = visible.filter((c) => c.status === 'HIGH' || c.status === 'MEDIUM');
  const flaggedArea = visible.reduce((s, c) => s + (c.no_permit_ha || 0) + (c.in_expired_ha || 0), 0);
  const awaiting = visible.filter((c) => !c.review.decision);
  // The review queue spans all cases and does not mutate dashboard filters.
  const awaitingFlagged = cases.filter((c) => (c.status === 'HIGH' || c.status === 'MEDIUM') && !c.review.decision)
    .sort((a, b) => b.after_date.localeCompare(a.after_date) || a.id.localeCompare(b.id));
  const sumBy = (arr, f) => arr.reduce((s, c) => s + (c[f] || 0), 0);
  const kpis = [
    { label: 'CASES IN WINDOW', value: visible.length, unit: 'sites', sub: `of ${cases.length} ground-truth pilot cases` },
    { label: ST.HIGH.label.toUpperCase(), value: countBy(visible, 'HIGH'), unit: 'sites', sub: `${ha(sumBy(visible, 'no_permit_ha'))} ha outside any permit`, mark: 'HIGH' },
    { label: ST.MEDIUM.label.toUpperCase(), value: countBy(visible, 'MEDIUM'), unit: 'sites', sub: `${ha(sumBy(visible, 'in_expired_ha'))} ha inside expired permits`, mark: 'MEDIUM' },
    { label: 'FLAGGED AREA', value: ha(flaggedArea), unit: 'ha', sub: `no valid permit · across ${flagged.length} flagged cases` },
    { label: 'AWAITING REVIEW', value: awaiting.length, unit: 'cases', sub: `${visible.length - awaiting.length} decided by an analyst` },
  ];

  const yearMon = (i) => `${monthName(months[i].m)} ${months[i].y}`;
  const windowLabel = customRange
    ? `${fmtDate(customRange.from)} – ${fmtDate(customRange.to)}`
    : `${yearMon(lo)} – ${yearMon(hi - 1)}`;
  const initialDates = customRange || {
    from: monthBoundary(months[lo]), to: monthBoundary(months[hi - 1], true),
  };
  const len = hi - lo;
  const presets = [['6M', Math.max(0, months.length - 6), months.length], ['12M', Math.max(0, months.length - 12), months.length], ['All', 0, months.length]];
  const provinces = [...new Set(cases.map((c) => c.prov))].sort();
  const selectedId = route.caseId;

  const navCurrent = route.view === 'dash' ? (section === 'register' ? 'cases' : section === 'analytics' ? 'reports' : 'dash') : route.view;
  const onNav = (k) => {
    if (k === 'permits' || k === 'settings' || k === 'admin') return go(k);
    go('dash');
    const id = k === 'cases' ? 'register' : k === 'reports' ? 'analytics' : 'top';
    setSection(id === 'top' ? 'top' : id);
    setTimeout(() => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (k === 'dash') window.scrollTo({ top: 0, behavior: 'smooth' });
    }, 30);
  };

  const logout = () => {
    if (!window.confirm('Log out of MineWatch?')) return;
    api('/api/auth/logout', { method: 'POST' }).catch(() => {}).then(() => { window.location.href = '/login'; });
  };

  const sideW = collapsed ? 60 : 232;
  return (
    <div className="app" id="top">
      {/* SIDEBAR */}
      <nav aria-label="Primary" className="side" style={{ width: sideW }}>
        <div className="side-brand">
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" style={{ flex: 'none' }}><rect x="1" y="1" width="20" height="20" rx="3" fill="#17181A" /><path d="M5.5 15.5 L9.2 8.5 L11.8 12.8 L13.6 10 L16.5 15.5" fill="none" stroke="#FFFFFF" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" /><circle cx="15.4" cy="6.6" r="1.3" fill="#FFFFFF" /></svg>
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
              <span className="t1">MineWatch</span>
              <span className="t2">Illegal Mining Detection</span>
            </div>
          )}
        </div>
        <div className="side-nav">
          {!collapsed && <div className="sec">WORKSPACE</div>}
          {NAV_TOP.map((n) => {
            const act = navCurrent === n.key;
            return (
              <button key={n.key} type="button" className="nav-a" aria-current={act ? 'page' : undefined} title={n.label} onClick={() => onNav(n.key)}
                style={{ padding: collapsed ? 0 : '0 14px 0 18px', justifyContent: collapsed ? 'center' : 'flex-start' }}>
                <span className="bar" aria-hidden="true" />
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" style={{ flex: 'none' }}><path d={n.icon} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
                {!collapsed && <span style={{ flex: 1, whiteSpace: 'nowrap' }}>{n.label}</span>}
              </button>
            );
          })}
          {!collapsed && NAV_SUB.map((n) => {
            const act = navCurrent === n.key;
            return (
              <button key={n.key} type="button" className="nav-a nav-sub" aria-current={act ? 'page' : undefined} title={n.label} onClick={() => onNav(n.key)}
                style={{ padding: '0 14px 0 34px', justifyContent: 'flex-start' }}>
                <span className="bar" aria-hidden="true" />
                <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" style={{ flex: 'none' }}><path d={n.icon} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
                <span style={{ flex: 1, whiteSpace: 'nowrap' }}>{n.label}</span>
                {n.key === 'cases' && <span className="badge">{cases.length}</span>}
              </button>
            );
          })}
          {NAV_BOTTOM.map((n) => {
            const act = navCurrent === n.key;
            return (
              <button key={n.key} type="button" className="nav-a" aria-current={act ? 'page' : undefined} title={n.label} onClick={() => onNav(n.key)}
                style={{ padding: collapsed ? 0 : '0 14px 0 18px', justifyContent: collapsed ? 'center' : 'flex-start' }}>
                <span className="bar" aria-hidden="true" />
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" style={{ flex: 'none' }}><path d={n.icon} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
                {!collapsed && <span style={{ flex: 1, whiteSpace: 'nowrap' }}>{n.label}</span>}
                {!collapsed && n.key === 'permits' && <span className="badge">{meta.permit_count.toLocaleString('en-US')}</span>}
              </button>
            );
          })}
          {role === 'Admin' && (() => {
            const act = navCurrent === NAV_ADMIN.key;
            return (
              <button key={NAV_ADMIN.key} type="button" className="nav-a" aria-current={act ? 'page' : undefined} title={NAV_ADMIN.label} onClick={() => onNav(NAV_ADMIN.key)}
                style={{ padding: collapsed ? 0 : '0 14px 0 18px', justifyContent: collapsed ? 'center' : 'flex-start' }}>
                <span className="bar" aria-hidden="true" />
                <svg width="17" height="17" viewBox="0 0 24 24" aria-hidden="true" style={{ flex: 'none' }}><path d={NAV_ADMIN.icon} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
                {!collapsed && <span style={{ flex: 1, whiteSpace: 'nowrap' }}>{NAV_ADMIN.label}</span>}
                {!collapsed && (
                  <></>
                )}
              </button>
            );
          })()}
        </div>
        <div className="side-foot">
          <button type="button" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}
            style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', gap: 8, height: 30, padding: '0 8px', border: '1px solid #DADAD5', borderRadius: 4, background: '#FFFFFF', cursor: 'pointer', fontSize: 12, color: '#3D4044' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" style={{ transform: `rotate(${collapsed ? 180 : 0}deg)` }}><path d="M15 6 L9 12 L15 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            {!collapsed && <span>Collapse</span>}
          </button>
        </div>
      </nav>

      {/* MAIN */}
      <div className="main-col">
        <header className="topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <span className="muted">Monitoring</span><span aria-hidden="true" style={{ color: '#A3A6AA' }}>/</span>
            <span style={{ fontWeight: 600 }}>{route.view === 'permits' ? 'Permits database' : route.view === 'settings' ? 'Settings' : route.view === 'admin' ? 'Admin' : 'National overview'}</span>
          </div>
          <div style={{ flex: '1 1 320px', display: 'flex', justifyContent: 'center', minWidth: 0 }}>
            <label className="search">
              <span className="sr">Search cases</span>
              <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style={{ position: 'absolute', left: 10, color: '#6B6E73' }}><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.8" /><path d="M16 16 L20 20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
              <input ref={searchRef} type="search" value={query} onChange={(e) => { setQuery(e.target.value); if (route.view !== 'dash') go('dash'); }}
                placeholder="Search location, company, permit no. or coordinates" />
            </label>
          </div>
          <div className="topbar-actions">
            <DateWindowPicker label={windowLabel} initialDates={initialDates} onApply={(range) => { setCustomRange(range); if (route.view !== 'dash') go('dash'); }}
              onReset={() => { setMonthWindow([0, nMonths]); if (route.view !== 'dash') go('dash'); }} />
            <ReviewNotifications cases={awaitingFlagged} onOpenCase={(id) => { setSel(id); setCallout(id); go('dash', id); }} />
            <button type="button" onClick={logout} title="Log out" style={{ display: 'flex', alignItems: 'center', gap: 9, paddingLeft: 10, borderLeft: '1px solid #E2E2DE', border: 0, background: 'transparent', cursor: 'pointer', textAlign: 'left' }}>
              <span className="avatar" aria-hidden="true">{analyst ? initials(analyst) : '?'}</span>
              <span style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>{analyst || '…'}</span>
                <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.07em', color: '#4A4D52' }}>{(role || 'ANALYST').toUpperCase()} · LOG OUT</span>
              </span>
            </button>
          </div>
        </header>

        {route.view === 'permits' && <PermitsView />}
        {route.view === 'settings' && <SettingsView meta={meta} analyst={analyst} onLogout={logout} />}
        {route.view === 'admin' && <AdminView role={role} analyst={analyst} />}

        {route.view === 'dash' && (
          <main className="page">
            <div className="page-h">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                <h1>National overview</h1>
                <span style={{ fontSize: 12 }} className="muted">
                  Change detection on Sentinel-2 L2A (10 m) cross-checked against BIG KSP permit polygons (~2022) · window <span style={{ color: '#17181A', fontWeight: 500 }}>{windowLabel}</span>
                </span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', color: '#5F6368' }}>PROVINCE
                  <select className="select" value={prov} onChange={(e) => setProv(e.target.value)} style={{ letterSpacing: 0, color: '#17181A' }}>
                    <option value="ALL">All provinces ({provinces.length})</option>
                    {provinces.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </label>
                <a className="btn" href="/api/export.geojson" download="minewatch_cases.geojson">
                  <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 V15 M7.5 10.5 L12 15 L16.5 10.5 M5 19.5 H19" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  Export GeoJSON
                </a>
              </div>
            </div>

            {/* KPI */}
            <section aria-label="Key figures for the selected window" className="kpis">
              {kpis.map((k) => (
                <div key={k.label} className="kpi">
                  <div className="lab">
                    {k.mark && <span aria-hidden="true" style={{ width: 8, height: 8, background: ST[k.mark].dot, borderRadius: ST[k.mark].rad, transform: `rotate(${ST[k.mark].rot})`, flex: 'none' }} />}
                    <span>{k.label}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span className="val">{k.value}</span><span className="unit">{k.unit}</span></div>
                  <span className="sub">{k.sub}</span>
                </div>
              ))}
            </section>

            {/* MAP + FEED */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'stretch' }}>
              <section aria-label="Detections map" className="card map-card">
                <MapPanel cases={visible} base={base} on={on} setOn={setOn} callout={callout} setCallout={setCallout}
                  sel={sel} setSel={setSel} openCase={openCase} meta={meta} />
                <Timeline months={months} cases={base} lo={lo} hi={hi} setWin={setMonthWindow} isCustom={!!customRange} windowLabel={windowLabel} len={len} total={base.length} presets={presets} />
              </section>

              <section id="feed" aria-label="Detection feed" className="feed-wrap">
                <div className="feed">
                  <div style={{ padding: '10px 14px 0', display: 'flex', flexDirection: 'column', gap: 8, borderBottom: '1px solid #E2E2DE' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <h2 style={{ margin: 0, fontSize: 13.5, fontWeight: 650 }}>Detection feed</h2>
                      <span style={{ fontSize: 11.5 }} className="muted">Newest image first · {feed.length} cases</span>
                    </div>
                    <div role="tablist" aria-label="Filter feed by permit category" className="tabs">
                      {['ALL', ...STATUSES].map((k) => (
                        <button key={k} type="button" role="tab" className="tab" aria-selected={tab === k} title={k === 'ALL' ? 'All cases' : ST[k].label} onClick={() => setTab(k)}>
                          {k === 'ALL' ? 'All' : ST[k].short}<span className="mono muted" style={{ fontSize: 10.5 }}>{k === 'ALL' ? visible.length : countBy(visible, k)}</span>
                          <span className="u" aria-hidden="true" />
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="mw-scroll" style={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto' }}>
                    {feed.map((c) => (
                      <button key={c.id} type="button" className={'feed-row' + (sel === c.id ? ' sel' : '')} onClick={() => openCase(c.id)} aria-label={`Open case ${c.id}, ${c.loc}`}>
                        <span className="selbar" aria-hidden="true" />
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                          <span className="thumbs"><img src={c.thumbs[0]} alt="" loading="lazy" /><img src={c.thumbs[1]} alt="" loading="lazy" /></span>
                          <span style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, letterSpacing: '0.06em', color: '#5F6368', padding: '0 2px' }}><span>T0</span><span>T1</span></span>
                        </span>
                        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
                          <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                            <span className="ellipsis" style={{ fontSize: 13, fontWeight: 600 }}>{c.loc}</span>
                            <span className="mono muted" style={{ fontSize: 10.5, whiteSpace: 'nowrap' }}>{fmtDate(c.after_date)}</span>
                          </span>
                          <span className="ellipsis muted" style={{ fontSize: 11.5 }}>{c.id} · {c.kab} · {c.prov}</span>
                          <span className="tnum" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '6px 10px', marginTop: 2, fontSize: 11.5 }}>
                            <StatusPill status={c.status} />
                            <span title={meta.checkpoint ? 'Share of frame pixels flagged as changed by the model' : 'Share of frame pixels with ΔNDVI < −0.2'}><b style={{ fontWeight: 600 }}>{pct(c.sharp_loss)}</b> <span className="muted">{meta.checkpoint ? 'model flagged' : 'NDVI loss'}</span></span>
                            <span><b style={{ fontWeight: 600 }}>{ha(c.area_ha)}</b> <span className="muted">ha</span></span>
                            <span className="chip-com" title={COM[c.com]}>{c.com}</span>
                            {c.review.decision && <span className="pill" style={{ background: '#EDEDE9', color: '#2B2D31' }}>✓ {c.review.decision_label}</span>}
                          </span>
                        </span>
                      </button>
                    ))}
                    {feed.length === 0 && <div style={{ padding: '28px 16px', textAlign: 'center', fontSize: 12.5 }} className="muted">No cases match the current window and filters.</div>}
                  </div>
                </div>
              </section>
            </div>

            {/* ANALYTICS */}
            <div id="analytics" style={{ display: 'flex', flexWrap: 'wrap', gap: 14, scrollMarginTop: 70 }}>
              <DisturbanceChart cases={periodCases} visibleIds={new Set(visible.map((c) => c.id))} onOpen={openCase} />
              <GroundTruthChart cases={periodCases} meta={meta} onOpen={openCase} />
            </div>

            {/* REGISTER */}
            <section id="register" aria-label="Case register" className="card reg" style={{ scrollMarginTop: 70 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '10px 14px', borderBottom: '1px solid #E2E2DE' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  <h2>Case register</h2>
                  <span style={{ fontSize: 11.5 }} className="muted">{table.length} cases · 13 ground-truth pilot sites, all ≤ 3 km cross-check</span>
                </div>
                <span style={{ fontSize: 11.5 }} className="muted">Sort: click a numeric column header</span>
              </div>
              <div className="mw-scroll" style={{ overflowX: 'auto' }}>
                <div role="table" aria-label="Cases" style={{ minWidth: 1140 }}>
                  <div role="row" className="reg-grid reg-head">
                    <span role="columnheader" style={{ paddingLeft: 14 }}>CASE ID</span>
                    <span role="columnheader">LOCATION</span>
                    <span role="columnheader">PROVINCE</span>
                    <span role="columnheader">COMMODITY</span>
                    <span role="columnheader" aria-sort={ariaSort('area')} style={{ padding: 0 }}><button type="button" onClick={sortBy('area')} style={{ textAlign: 'right' }}>AREA (HA) {arrow('area')}</button></span>
                    <span role="columnheader">PERMIT CATEGORY</span>
                    <span role="columnheader" aria-sort={ariaSort('out')} style={{ padding: 0 }}><button type="button" onClick={sortBy('out')} style={{ textAlign: 'right' }}>OUTSIDE {arrow('out')}</button></span>
                    <span role="columnheader" aria-sort={ariaSort('date')} style={{ padding: 0 }}><button type="button" onClick={sortBy('date')} style={{ textAlign: 'left' }}>AFTER IMAGE {arrow('date')}</button></span>
                    <span role="columnheader">REVIEW</span>
                  </div>
                  {table.map((c) => (
                    <div key={c.id} role="row" className={'reg-grid reg-row' + (sel === c.id ? ' sel' : '')}>
                      <span role="cell" style={{ paddingLeft: 14 }}><button type="button" className="link-id" onClick={() => openCase(c.id)}>{c.id}</button></span>
                      <span role="cell" className="ellipsis"><span style={{ fontWeight: 500 }}>{c.loc}</span> <span className="muted">· {c.kab}</span></span>
                      <span role="cell" className="ellipsis" style={{ color: '#3D4044' }}>{c.prov}</span>
                      <span role="cell" style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span className="chip-com">{c.com}</span><span style={{ color: '#3D4044' }}>{COM[c.com]}</span></span>
                      <span role="cell" className="mono" style={{ textAlign: 'right', fontSize: 12 }}>{ha(c.area_ha)}</span>
                      <span role="cell"><StatusPill status={c.status} /></span>
                      <span role="cell" style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 7 }}>
                        <span className="minibar" aria-hidden="true"><span style={{ width: `${c.pct_outside || 0}%` }} /></span>
                        <span className="mono" style={{ fontSize: 12 }}>{c.pct_outside == null ? '—' : Math.round(c.pct_outside) + '%'}</span>
                      </span>
                      <span role="cell" className="mono" style={{ fontSize: 11.5, color: '#3D4044' }}>{fmtDate(c.after_date)}</span>
                      <span role="cell" className="ellipsis" style={{ color: c.review.decision ? '#17181A' : c.review.assignee ? '#17181A' : '#8A5A00' }}>
                        {c.review.decision ? `✓ ${c.review.decision_label}` : c.review.assignee || 'Unassigned'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <footer style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '6px 16px', fontSize: 11 }} className="muted">
              <span>Imagery: Copernicus Sentinel-2 L2A · Permits: BIG Kebijakan Satu Peta IUP/IUPK ({meta.permit_count.toLocaleString('en-US')} polygons, ~2022) · Detection: {meta.checkpoint ? modelLabel(meta.detection_method).tag : 'NDVI threshold'}</span>
              <span>13 real ground-truth pilot cases · All decisions require analyst sign-off · Alert dispatch is a MOCK</span>
            </footer>
          </main>
        )}
      </div>

      {selectedId && (
        <div className="overlay">
          <button type="button" className="scrim" onClick={closeCase} aria-label="Close case panel" />
          <aside aria-label="Case detail" className="mw-scroll">
            <CasePanel id={selectedId} analyst={analyst} meta={meta} onClose={closeCase}
              onNavigate={(id) => { setSel(id); setCallout(id); go(route.view, id); }} onChanged={reload} />
          </aside>
        </div>
      )}
    </div>
  );
}

function monthBoundary({ y, m }, end = false) {
  return new Date(Date.UTC(y, m + Number(end), end ? 0 : 1)).toISOString().slice(0, 10);
}

function TopbarPopover({ id, titleId, width, className, onOpen, trigger, children }) {
  const anchor = useRef(null);
  const button = useRef(null);
  const [position, setPosition] = useState(null);
  const isOpen = position !== null;
  const reposition = useCallback(() => {
    const rect = button.current.getBoundingClientRect();
    const viewport = document.documentElement.clientWidth;
    const panelWidth = Math.min(width, viewport - 24);
    const left = Math.max(12, Math.min(rect.right - panelWidth, viewport - panelWidth - 12));
    setPosition({ top: rect.bottom + 8, left, width: panelWidth });
  }, [width]);
  const close = (restoreFocus = false) => {
    setPosition(null);
    if (restoreFocus) button.current.focus();
  };
  useEffect(() => {
    if (!isOpen) return;
    const outside = (e) => { if (!anchor.current.contains(e.target)) setPosition(null); };
    const escape = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      e.preventDefault();
      setPosition(null);
      button.current.focus();
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('focusin', outside);
    document.addEventListener('keydown', escape);
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('focusin', outside);
      document.removeEventListener('keydown', escape);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition);
    };
  }, [isOpen, reposition]);
  return (
    <div ref={anchor} className="topbar-popover-anchor">
      {trigger({ ref: button, 'aria-expanded': isOpen, 'aria-controls': id, onClick: () => {
        if (isOpen) close();
        else { onOpen?.(); reposition(); }
      } })}
      <section id={id} aria-labelledby={titleId} hidden={!isOpen} className={`topbar-popover card ${className}`}
        style={isOpen ? ({ ...position, maxHeight: `calc(100dvh - ${position.top + 12}px)` }) : undefined}>
        {children(() => close(true))}
      </section>
    </div>
  );
}

function ReviewNotifications({ cases, onOpenCase }) {
  return (
    <TopbarPopover id="review-notifications-panel" titleId="review-notifications-title" width={440} className="review-notifications" trigger={(props) => (
      <button {...props} type="button" className="iconbtn" title="Notifications" aria-label={`Notifications: ${cases.length} cases awaiting review`}>
        <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16 V11 a6 6 0 0 1 12 0 V16 L19.5 18 H4.5 Z M10 20.5 a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg>
        {cases.length > 0 && <span className="count" aria-hidden="true">{cases.length}</span>}
      </button>
    )}>
      {(close) => <>
        <div className="review-notifications-head">
          <div>
            <h2 id="review-notifications-title">Notifications</h2>
            <p id="review-notifications-summary" className="muted">{cases.length} {cases.length === 1 ? 'case' : 'cases'} flagged for review · All dates</p>
          </div>
          <button type="button" className="btn" onClick={close}>Close</button>
        </div>
        {cases.length === 0 ? <p className="review-notifications-empty muted">No flagged cases are awaiting review.</p> : (
          <ul className="review-notifications-list mw-scroll">
            {cases.map((c) => (
              <li key={c.id}>
                <button type="button" className="review-notification-row" onClick={() => { close(); onOpenCase(c.id); }}>
                  <strong>{c.loc}</strong>
                  <span className="muted">{c.id} · {c.prov} · {fmtDate(c.after_date)}</span>
                  <span><StatusPill status={c.status} /></span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </>}
    </TopbarPopover>
  );
}

function DateWindowPicker({ label, initialDates, onApply, onReset }) {
  const [draft, setDraft] = useState(initialDates);
  const reversed = !!(draft.from && draft.to && draft.from > draft.to);
  const apply = (e, close) => {
    e.preventDefault();
    if (!draft.from || !draft.to || reversed) return;
    onApply(draft);
    close();
  };
  return (
    <TopbarPopover id="date-window-panel" titleId="date-window-title" width={420} className="date-dialog" onOpen={() => setDraft(initialDates)} trigger={(props) => (
      <button {...props} type="button" className="btn" style={{ minHeight: 34 }} aria-label={`Choose date range: ${label}`}>
        <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5.5" width="16" height="14.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.7" /><path d="M4 10 H20 M8.5 3.5 V7 M15.5 3.5 V7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg>
        <span className="tnum">{label}</span>
      </button>
    )}>
      {(close) => (
        <form onSubmit={(e) => apply(e, close)}>
          <h2 id="date-window-title">Custom date range</h2>
          <p className="muted">Filter by after-image date. Both dates are included.</p>
          <div className="date-dialog-fields">
            <label>From<input type="date" required max="9999-12-31" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} /></label>
            <label>To<input type="date" required max="9999-12-31" value={draft.to} aria-invalid={reversed || undefined} onChange={(e) => setDraft({ ...draft, to: e.target.value })} /></label>
          </div>
          {reversed && <p className="date-dialog-error" role="alert">The end date must be on or after the start date.</p>}
          <div className="date-dialog-actions">
            <button className="btn" type="button" onClick={() => { onReset(); close(); }}>All dates</button>
            <button className="btn" type="button" onClick={close}>Cancel</button>
            <button className="btn primary" type="submit" disabled={!draft.from || !draft.to || reversed}>Apply</button>
          </div>
        </form>
      )}
    </TopbarPopover>
  );
}

function Timeline({ months, cases, lo, hi, setWin, isCustom, windowLabel, len, total, presets }) {
  const n = months.length;
  const per = months.map((mm) => {
    const inM = cases.filter((c) => monthIndex(c.after_date) === mm.idx);
    return { HIGH: inM.filter((c) => c.status === 'HIGH').length, MEDIUM: inM.filter((c) => c.status === 'MEDIUM').length, LOW: inM.filter((c) => c.status === 'LOW').length };
  });
  const maxT = Math.max(1, ...per.map((p) => p.HIGH + p.MEDIUM + p.LOW));
  const k = 40 / maxT;
  const winLeft = `calc(6px + ${(lo / n).toFixed(4)} * (100% - 12px))`;
  const winWidth = `calc(${(len / n).toFixed(4)} * (100% - 12px))`;
  const showLabel = (i) => n <= 14 || months[i].m === 0 || i === 0 || i === n - 1 || months[i].m === 6;
  return (
    <div className="tl">
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="eyebrow">AFTER-IMAGE TIMELINE</span>
          <span className="tnum" style={{ fontSize: 12, fontWeight: 500 }}>{windowLabel}</span>
          <span className="tnum muted" style={{ fontSize: 11.5 }}>{!isCustom && `${len} mo · `}{total} cases</span>
        </div>
        <div role="group" aria-label="Window presets" className="seg">
          {presets.map((p) => (
            <button key={p[0]} type="button" aria-pressed={!isCustom && lo === p[1] && hi === p[2]} onClick={() => setWin([p[1], p[2]])}>{p[0]}</button>
          ))}
        </div>
      </div>
      <div style={{ position: 'relative', height: 46, padding: '0 6px', display: 'flex', alignItems: 'flex-end', gap: 2 }}>
        <div aria-hidden="true" style={{ position: 'absolute', top: 0, bottom: 0, left: winLeft, width: winWidth, background: '#EEEEEA', borderLeft: '1px solid #A3A6AA', borderRight: '1px solid #A3A6AA' }} />
        {per.map((p, i) => {
          const inW = i >= lo && i < hi;
          const t = `${monthName(months[i].m)} ${months[i].y}: ${p.HIGH + p.MEDIUM + p.LOW} cases (${p.HIGH} ${ST.HIGH.label}, ${p.MEDIUM} ${ST.MEDIUM.label}, ${p.LOW} ${ST.LOW.label})`;
          return (
            <div key={i} title={t} style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
              <div style={{ height: p.HIGH * k, background: inW ? '#C8322A' : '#CFCFCA' }} />
              <div style={{ height: p.MEDIUM * k, background: inW ? '#D99A1E' : '#DCDCD7' }} />
              <div style={{ height: p.LOW * k, background: inW ? '#7FB08F' : '#E6E6E2' }} />
            </div>
          );
        })}
      </div>
      <div style={{ position: 'relative', height: 26 }}>
        <div aria-hidden="true" style={{ position: 'absolute', left: 6, right: 6, top: 12, height: 2, background: '#DADAD5' }} />
        <div aria-hidden="true" style={{ position: 'absolute', top: 12, height: 2, left: winLeft, width: winWidth, background: '#17181A' }} />
        <input className="mw-range" type="range" min="0" max={n} step="1" value={lo} aria-label="Window start"
          onChange={(e) => setWin([Math.min(parseInt(e.target.value, 10), Math.max(1, hi) - 1), Math.max(1, hi)])} />
        <input className="mw-range" type="range" min="0" max={n} step="1" value={hi} aria-label="Window end"
          onChange={(e) => setWin([Math.min(lo, n - 1), Math.max(parseInt(e.target.value, 10), Math.min(lo, n - 1) + 1)])} />
      </div>
      <div style={{ display: 'flex', padding: '0 6px', gap: 2 }}>
        {months.map((mm, i) => (
          <span key={i} style={{ flex: 1, textAlign: 'center', fontSize: 10, whiteSpace: 'nowrap', overflow: 'visible', color: i >= lo && i < hi ? '#17181A' : '#6B6E73' }} className="tnum">
            {showLabel(i) ? (mm.m === 0 || i === 0 ? `${monthName(mm.m)} ’${String(mm.y).slice(2)}` : monthName(mm.m)) : ''}
          </span>
        ))}
      </div>
    </div>
  );
}
