import React, { useEffect, useMemo, useState } from 'react';
import { api, fmtDate, fmtDateTime } from './lib.js';

const TABS = [
  { key: 'users', label: 'Users' },
  { key: 'permits', label: 'Permits' },
  { key: 'log', label: 'Activity log' },
  { key: 'data', label: 'Data status' },
];
const RANGES = [['7', 'Last 7 days'], ['30', 'Last 30 days'], ['90', 'Last 90 days'], ['all', 'All time']];

function genPw() {
  const c = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let s = ''; for (let i = 0; i < 12; i++) s += c[Math.floor(Math.random() * c.length)];
  return s;
}

export default function AdminView({ role, analyst }) {
  const [tab, setTab] = useState('users');
  const [toast, setToast] = useState('');
  const say = (msg) => { setToast(msg); setTimeout(() => setToast((t) => (t === msg ? '' : t)), 4200); };

  if (role !== 'Admin') {
    return (
      <main className="page">
        <section className="card" style={{ marginTop: 40, alignSelf: 'center', width: '100%', maxWidth: 460, padding: 24, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <span className="mono" style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', color: '#5F6368' }}>403 · ADMIN ONLY</span>
          <h1 style={{ margin: 0, fontSize: 18, fontWeight: 650 }}>This section is limited to Admin accounts.</h1>
          <p style={{ margin: 0, color: '#4A4D52', lineHeight: 1.5 }}>Ask an Admin if you need a user or permit changed.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <div className="page-h">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <h1>Admin</h1>
          <span className="muted" style={{ fontSize: 12 }}>Back-office controls for trusted operators. Every change here is written to the activity log.</span>
        </div>
        </div>

      <div role="tablist" aria-label="Admin sections" style={{ display: 'flex', gap: 2, borderBottom: '1px solid #D6D6D1' }}>
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            style={{ position: 'relative', height: 36, padding: '0 14px', border: 0, background: 'transparent', cursor: 'pointer', fontSize: 13, fontWeight: tab === t.key ? 600 : 500, color: tab === t.key ? '#17181A' : '#4A4D52' }}>
            {t.label}
            <span aria-hidden="true" style={{ position: 'absolute', left: 8, right: 8, bottom: -1, height: 2, background: '#17181A', opacity: tab === t.key ? 1 : 0 }} />
          </button>
        ))}
      </div>

      {tab === 'users' && <UsersTab me={analyst} say={say} />}
      {tab === 'permits' && <PermitsTab say={say} />}
      {tab === 'log' && <LogTab />}
      {tab === 'data' && <DataTab />}

      {toast && <div role="status" style={{ position: 'fixed', right: 20, bottom: 20, zIndex: 90, maxWidth: 420, padding: '10px 14px', background: '#17181A', color: '#F3F3F1', borderRadius: 5, fontSize: 12.5, boxShadow: '0 8px 24px rgba(23,24,26,0.3)' }}>{toast}</div>}
    </main>
  );
}

function Modal({ title, width = 440, onClose, children, footer, labelledBy, alertdialog }) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, boxSizing: 'border-box', background: 'rgba(23,24,26,0.5)' }}>
      <div role={alertdialog ? 'alertdialog' : 'dialog'} aria-modal="true" aria-labelledby={labelledBy} className="mw-scroll"
        style={{ width: '100%', maxWidth: width, maxHeight: '100%', overflowY: 'auto', background: '#fff', borderRadius: 6, boxShadow: '0 16px 48px rgba(0,0,0,0.3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid #E2E2DE' }}>
          <h2 id={labelledBy} style={{ margin: 0, fontSize: 15, fontWeight: 650 }}>{title}</h2>
          <button type="button" className="btn" style={{ height: 26, padding: '0 9px' }} onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>{children}</div>
        {footer && <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '12px 18px', borderTop: '1px solid #E2E2DE', background: '#FAFAF8', borderRadius: '0 0 6px 6px' }}>{footer}</div>}
      </div>
    </div>
  );
}

function Lbl({ children }) { return <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#3D4044' }}>{children}</span>; }
const inStyle = { width: '100%', height: 34, boxSizing: 'border-box', padding: '0 10px', border: '1px solid #C9C9C4', borderRadius: 4, background: '#fff', fontSize: 13 };

// ----------------------------------------------------------------- Users --
function UsersTab({ me, say }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState('');
  const [modal, setModal] = useState(null); // 'add' | { type:'reset'|'delete', u }
  const [form, setForm] = useState({ username: '', password: '', role: 'Analyst', show: false, err: '' });
  const [resetPw, setResetPw] = useState({ password: '', show: false, err: '' });

  const reload = () => api('/api/admin/users').then(setData).catch((e) => setErr(e.message));
  useEffect(() => { reload(); }, []);

  if (err) return <div className="banner">Error: {err}</div>;
  if (!data) return <div className="muted">Loading…</div>;

  const ql = q.trim().toLowerCase();
  const rows = data.users.filter((u) => !ql || u.username.toLowerCase().includes(ql));
  const admins = data.admin_count;

  const addUser = () => {
    const u = form.username.trim().toLowerCase();
    if (!u || !/^[a-z0-9._-]{3,32}$/.test(u)) return setForm({ ...form, err: 'Username: 3–32 chars, letters, digits, dot, dash or underscore.' });
    if (form.password.length < 8) return setForm({ ...form, err: 'Temporary password must be at least 8 characters.' });
    api('/api/admin/users', { method: 'POST', body: { username: u, password: form.password, role: form.role } })
      .then(() => { setModal(null); reload(); say(`User ${u} added and logged.`); })
      .catch((e) => setForm({ ...form, err: e.message }));
  };
  const saveReset = (u) => {
    if (resetPw.password.length < 8) return setResetPw({ ...resetPw, err: 'Temporary password must be at least 8 characters.' });
    api(`/api/admin/users/${encodeURIComponent(u)}/reset-password`, { method: 'POST', body: { password: resetPw.password } })
      .then(() => { setModal(null); say(`Password reset for ${u}. Logged.`); })
      .catch((e) => setResetPw({ ...resetPw, err: e.message }));
  };
  const delUser = (u) => {
    api(`/api/admin/users/${encodeURIComponent(u)}`, { method: 'DELETE' })
      .then(() => { setModal(null); reload(); say(`User ${u} deleted. Their history is kept.`); })
      .catch((e) => say(e.message));
  };

  return (
    <section aria-label="Users" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '8px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: '1 1 260px', maxWidth: 420 }}>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by username" style={inStyle} />
          <span className="mono muted" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>{data.users.length} users · {admins} admin</span>
        </div>
        <button type="button" className="btn btn-dark" onClick={() => { setForm({ username: '', password: '', role: 'Analyst', show: false, err: '' }); setModal('add'); }}>+ Add user</button>
      </div>

      <div className="card">
        <div className="mw-scroll" style={{ overflowX: 'auto' }}>
          <div role="table" aria-label="Users" style={{ minWidth: 900 }}>
            <div role="row" style={{ display: 'grid', gridTemplateColumns: 'minmax(160px,1.3fr) 96px 120px 160px 140px 214px', background: '#F7F7F5', borderBottom: '1px solid #E2E2DE', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#5F6368' }}>
              <span role="columnheader" style={{ padding: '9px 14px' }}>USERNAME</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>ROLE</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>CREATED</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>LAST LOGIN</span>
              <span role="columnheader" style={{ padding: '9px 10px', textAlign: 'right' }}>DECISIONS SIGNED</span>
              <span role="columnheader" style={{ padding: '9px 14px' }}>ACTIONS</span>
            </div>
            {rows.map((u) => {
              const lastAdmin = u.role === 'Admin' && admins <= 1;
              return (
                <div key={u.username} role="row" style={{ display: 'grid', gridTemplateColumns: 'minmax(160px,1.3fr) 96px 120px 160px 140px 214px', alignItems: 'center', minHeight: 40, borderBottom: '1px solid #EFEFEB', fontSize: 12.5 }}>
                  <span role="cell" style={{ padding: '0 14px', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>{u.username}</span>
                    {u.username === me && <span className="muted" style={{ fontSize: 10.5 }}>(you)</span>}
                  </span>
                  <span role="cell" style={{ padding: '0 10px' }}>
                    <span className="pill" style={{ background: u.role === 'Admin' ? '#17181A' : '#EDEDE9', color: u.role === 'Admin' ? '#fff' : '#3D4044' }}>{u.role.toUpperCase()}</span>
                  </span>
                  <span role="cell" className="mono" style={{ padding: '0 10px', fontSize: 11.5, color: '#3D4044' }}>{fmtDate(u.created_at)}</span>
                  <span role="cell" className="mono" style={{ padding: '0 10px', fontSize: 11.5, color: '#3D4044' }}>{u.last_login ? fmtDateTime(u.last_login) : '—'}</span>
                  <span role="cell" className="mono" style={{ padding: '0 10px', textAlign: 'right', fontSize: 12 }}>{u.decisions_signed}</span>
                  <span role="cell" style={{ padding: '0 14px', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button type="button" className="btn" style={{ height: 26, padding: '0 9px', fontSize: 11.5 }} onClick={() => { setResetPw({ password: '', show: false, err: '' }); setModal({ type: 'reset', u: u.username }); }}>Reset password</button>
                    <button type="button" className="btn" style={{ height: 26, padding: '0 9px', fontSize: 11.5 }} disabled={lastAdmin} title={lastAdmin ? "Can't delete the last remaining Admin account." : undefined}
                      onClick={() => !lastAdmin && setModal({ type: 'delete', u: u.username, dec: u.decisions_signed, aud: u.audit_entries })}>Delete</button>
                  </span>
                </div>
              );
            })}
            {rows.length === 0 && <div style={{ padding: '22px 14px', textAlign: 'center', color: '#5F6368' }}>No users match this filter.</div>}
          </div>
        </div>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5 }}>Known gap: there is no self-service password change yet. New and reset passwords are temporary and set by an Admin; users are asked to change them after first login.</p>

      {modal === 'add' && (
        <Modal title="Add user" labelledBy="mt-add" onClose={() => setModal(null)}
          footer={<><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button type="button" className="btn btn-dark" onClick={addUser}>Add user</button></>}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>USERNAME</Lbl><input className="mono" style={inStyle} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value, err: '' })} autoComplete="off" /></label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>TEMPORARY PASSWORD</Lbl>
            <span style={{ display: 'flex', gap: 6 }}>
              <input className="mono" style={inStyle} type={form.show ? 'text' : 'password'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value, err: '' })} autoComplete="new-password" />
              <button type="button" className="btn" onClick={() => setForm({ ...form, show: !form.show })}>{form.show ? 'Hide' : 'Show'}</button>
              <button type="button" className="btn" onClick={() => setForm({ ...form, password: genPw(), show: true, err: '' })}>Generate</button>
            </span>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>ROLE</Lbl>
            <select className="select" style={{ ...inStyle, width: '100%' }} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="Analyst">Analyst</option><option value="Admin">Admin</option>
            </select>
          </label>
          <span style={{ fontSize: 12, color: '#5F6368' }}>The user should change this password after first login.</span>
          {form.err && <p role="alert" style={{ margin: 0, padding: '8px 10px', border: '1px solid #17181A', borderRadius: 4, fontSize: 12, fontWeight: 500 }}>{form.err}</p>}
        </Modal>
      )}

      {modal && modal.type === 'reset' && (
        <Modal title="Reset password" labelledBy="mt-rp" width={400} onClose={() => setModal(null)}
          footer={<><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button type="button" className="btn btn-dark" onClick={() => saveReset(modal.u)}>Set password</button></>}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}><span className="muted">Account</span><span className="mono" style={{ fontWeight: 500 }}>{modal.u}</span></div>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>NEW TEMPORARY PASSWORD</Lbl>
            <span style={{ display: 'flex', gap: 6 }}>
              <input className="mono" style={inStyle} type={resetPw.show ? 'text' : 'password'} value={resetPw.password} onChange={(e) => setResetPw({ ...resetPw, password: e.target.value, err: '' })} autoComplete="new-password" />
              <button type="button" className="btn" onClick={() => setResetPw({ ...resetPw, show: !resetPw.show })}>{resetPw.show ? 'Hide' : 'Show'}</button>
              <button type="button" className="btn" onClick={() => setResetPw({ ...resetPw, password: genPw(), show: true, err: '' })}>Generate</button>
            </span>
          </label>
          {resetPw.err && <p role="alert" style={{ margin: 0, padding: '8px 10px', border: '1px solid #17181A', borderRadius: 4, fontSize: 12, fontWeight: 500 }}>{resetPw.err}</p>}
        </Modal>
      )}

      {modal && modal.type === 'delete' && (
        <Modal title={`Delete user ${modal.u}?`} labelledBy="mt-du" alertdialog onClose={() => setModal(null)}
          footer={<><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button type="button" className="btn btn-dark" onClick={() => delUser(modal.u)}>Delete user</button></>}>
          <div style={{ padding: '10px 12px', background: '#FBF0D6', borderRadius: 4, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{modal.dec} decisions signed · {modal.aud} audit entries</span>
            <span style={{ fontSize: 12.5, lineHeight: 1.45 }}>These stay in history, attributed to <b>{modal.u}</b>, after deletion.</span>
          </div>
          <span style={{ fontSize: 12.5, color: '#3D4044', lineHeight: 1.45 }}>The account can no longer log in. This is recorded in the activity log and cannot be undone.</span>
        </Modal>
      )}
    </section>
  );
}

// --------------------------------------------------------------- Permits --
function blankPermitForm() {
  return { mode: 'add', objectid: null, no: '', holder: '', commodity: '', type: 'IUP', status: 'active', expiry: '', prov: '', kab: '', loc: 'upload', fileName: '', geojson: null, polygon: [], err: '' };
}

function DrawPad({ poly, setPoly }) {
  const [center, setCenter] = useState({ lat: -2.0, lon: 113.0, span: 2 });
  const toLL = (xPct, yPct) => [center.lat + (0.5 - yPct) * center.span, center.lon + (xPct - 0.5) * center.span];
  const toPct = (lat, lon) => [50 + ((lon - center.lon) / center.span) * 100, 50 - ((lat - center.lat) / center.span) * 100];
  const onClick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const xPct = (e.clientX - r.left) / r.width, yPct = (e.clientY - r.top) / r.height;
    const [lat, lon] = toLL(xPct, yPct);
    setPoly(poly.concat([[lat, lon]]));
  };
  const pts = poly.map(([lat, lon]) => toPct(lat, lon).map((v) => v.toFixed(2)).join(',')).join(' ');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11.5 }}>Center lat<input type="number" step="0.001" value={center.lat} onChange={(e) => setCenter({ ...center, lat: parseFloat(e.target.value) || 0 })} style={{ width: 90, height: 26, border: '1px solid #C9C9C4', borderRadius: 4, padding: '0 6px' }} /></label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11.5 }}>Center lon<input type="number" step="0.001" value={center.lon} onChange={(e) => setCenter({ ...center, lon: parseFloat(e.target.value) || 0 })} style={{ width: 90, height: 26, border: '1px solid #C9C9C4', borderRadius: 4, padding: '0 6px' }} /></label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11.5 }}>Span (deg)<input type="number" step="0.05" min="0.02" value={center.span} onChange={(e) => setCenter({ ...center, span: Math.max(0.02, parseFloat(e.target.value) || 1) })} style={{ width: 70, height: 26, border: '1px solid #C9C9C4', borderRadius: 4, padding: '0 6px' }} /></label>
        <span className="muted" style={{ fontSize: 11 }}>Tip: find coordinates in a case first, set them here, then click to place vertices.</span>
      </div>
      <div style={{ position: 'relative', height: 260, borderRadius: 5, overflow: 'hidden', background: '#181B1E', border: '1px solid #2D3135' }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          <rect width="100" height="100" fill="#1D2023" />
          <line x1="50" y1="0" x2="50" y2="100" stroke="#2D3135" strokeWidth="0.3" /><line x1="0" y1="50" x2="100" y2="50" stroke="#2D3135" strokeWidth="0.3" />
          {poly.length >= 3 && <polygon points={pts} fill="rgba(229,72,61,0.28)" stroke="#F3F3F1" strokeWidth="1.2" />}
          {poly.length === 2 && <polyline points={pts} fill="none" stroke="#F3F3F1" strokeWidth="1.2" strokeDasharray="4 3" />}
          {poly.map(([lat, lon], i) => { const [x, y] = toPct(lat, lon); return <circle key={i} cx={x} cy={y} r="1.1" fill="#F3F3F1" stroke="#17181A" strokeWidth="0.4" />; })}
        </svg>
        <button type="button" onClick={onClick} aria-label="Click to place a polygon vertex" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0, background: 'transparent', cursor: 'crosshair' }} />
        {poly.length === 0 && <span style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', pointerEvents: 'none', padding: '6px 10px', background: 'rgba(23,24,26,0.85)', color: '#E4E5E2', borderRadius: 3, fontSize: 12 }}>Click to place vertices (min. 3)</span>}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, color: '#3D4044' }}>
        <span>{poly.length} vertices</span>
        <span style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn" style={{ height: 24, padding: '0 8px', fontSize: 11 }} onClick={() => setPoly(poly.slice(0, -1))}>Undo point</button>
          <button type="button" className="btn" style={{ height: 24, padding: '0 8px', fontSize: 11 }} onClick={() => setPoly([])}>Clear</button>
        </span>
      </div>
    </div>
  );
}

function PermitsTab({ say }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState('');
  const [commodity, setCommodity] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState(blankPermitForm());
  const [delTarget, setDelTarget] = useState(null);
  const [reimportBusy, setReimportBusy] = useState(false);

  const reload = () => api(`/api/admin/permits?q=${encodeURIComponent(q)}&commodity=${commodity}&type=${type}&status=${status}&page=${page}&size=50`)
    .then(setData).catch((e) => setErr(e.message));
  useEffect(() => { const t = setTimeout(reload, 200); return () => clearTimeout(t); }, [q, commodity, type, status, page]);

  if (err) return <div className="banner">Error: {err}</div>;
  if (!data) return <div className="muted">Loading…</div>;
  const pages = Math.max(1, Math.ceil(data.total / data.size));

  const onFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      try { setForm((s) => ({ ...s, fileName: `${f.name} · ${Math.max(1, Math.round(f.size / 1024))} KB`, geojson: JSON.parse(reader.result), polygon: [], err: '' })); }
      catch { setForm((s) => ({ ...s, err: 'Could not parse that file as GeoJSON.' })); }
    };
    reader.readAsText(f);
  };

  const openAdd = () => { setForm(blankPermitForm()); setModal('permit'); };
  const openEdit = (p) => {
    setForm({ ...blankPermitForm(), mode: 'edit', objectid: p.objectid, no: p.no.startsWith('OBJ-') ? '' : p.no, holder: p.holder, commodity: p.commodity, type: p.type, status: p.status, expiry: p.valid_until || '', prov: p.prov === '-' ? '' : p.prov, kab: p.kab === '-' ? '' : p.kab });
    setModal('permit');
  };
  const savePermit = () => {
    if (!form.holder.trim()) return setForm({ ...form, err: 'Enter the holder name.' });
    const hasGeom = form.geojson || form.polygon.length >= 3;
    if (form.mode === 'add' && !hasGeom) return setForm({ ...form, err: 'Add a location: upload a GeoJSON polygon, or draw at least 3 vertices on the map.' });
    const body = { no: form.no, holder: form.holder.trim(), commodity: form.commodity, type: form.type, status: form.status, expiry: form.expiry || null, prov: form.prov, kab: form.kab, geojson: form.geojson, polygon: form.polygon.length >= 3 ? form.polygon : null };
    const req = form.mode === 'add' ? api('/api/admin/permits', { method: 'POST', body }) : api(`/api/admin/permits/${form.objectid}`, { method: 'PUT', body });
    req.then((r) => { setModal(null); reload(); say(form.mode === 'add' ? `Permit saved. ${r.cases_recrosschecked} cases re-cross-checked.` : `Permit updated. ${r.cases_recrosschecked} cases re-cross-checked.`); })
      .catch((e) => setForm({ ...form, err: e.message }));
  };
  const confirmDelete = () => {
    api(`/api/admin/permits/${delTarget.objectid}`, { method: 'DELETE' })
      .then((r) => { setModal(null); setDelTarget(null); reload(); say(`Permit ${delTarget.no} deleted. ${r.cases_recrosschecked} cases re-cross-checked.`); })
      .catch((e) => say(e.message));
  };
  const confirmReimport = () => {
    setReimportBusy(true);
    api('/api/admin/permits/reimport', { method: 'POST' })
      .then((r) => { setModal(null); reload(); say(`Base registry re-imported. ${r.cases_recrosschecked} cases re-cross-checked.`); })
      .catch((e) => say(e.message)).finally(() => setReimportBusy(false));
  };

  return (
    <section aria-label="Permits" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '10px 16px', padding: '10px 14px', background: '#FAFAF8', border: '1px solid #D6D6D1', borderRadius: 6 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 10px', fontSize: 12.5 }}>
          <Lbl>BASE REGISTRY</Lbl><span>BIG Kebijakan Satu Peta, snapshot ~2022</span><span className="muted">·</span>
          <span className="mono">{data.total.toLocaleString('en-US')} polygons</span><span className="muted">·</span>
          <span style={{ color: '#4A4D52' }}>admin-added <span className="mono">{data.admin_added_count}</span></span>
        </div>
        <button type="button" className="btn" style={{ borderStyle: 'dashed', borderColor: '#8A8D91', height: 26, padding: '0 9px', fontSize: 11.5 }} onClick={() => setModal('reimport')}>⟳ Re-import base registry</button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '8px 12px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Permit no., holder or province" style={{ ...inStyle, width: 220 }} />
          <input list="adm-commodity-opts" value={commodity} onChange={(e) => { setCommodity(e.target.value); setPage(1); }} placeholder="Any commodity" style={{ ...inStyle, width: 170 }} />
          <datalist id="adm-commodity-opts">{(data.commodities || []).map((c) => <option key={c} value={c} />)}</datalist>
          <select className="select" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}><option value="">All types</option>{(data.types || []).map((t) => <option key={t} value={t}>{t}</option>)}</select>
          <select className="select" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">All statuses</option><option value="active">Active</option><option value="expired">Expired</option></select>
        </div>
        <button type="button" className="btn btn-dark" onClick={openAdd}>+ Add permit</button>
      </div>

      <div className="card">
        <div className="mw-scroll" style={{ overflowX: 'auto' }}>
          <div role="table" aria-label="Permits" style={{ minWidth: 1100 }}>
            <div role="row" style={{ display: 'grid', gridTemplateColumns: '170px minmax(180px,1.6fr) 112px 70px 96px 104px minmax(130px,1fr) 132px', background: '#F7F7F5', borderBottom: '1px solid #E2E2DE', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#5F6368' }}>
              <span role="columnheader" style={{ padding: '9px 14px' }}>PERMIT NO</span><span role="columnheader" style={{ padding: '9px 10px' }}>HOLDER / COMPANY</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>COMMODITY</span><span role="columnheader" style={{ padding: '9px 10px' }}>TYPE</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>STATUS</span><span role="columnheader" style={{ padding: '9px 10px', textAlign: 'right' }}>AREA (HA)</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>PROVINCE</span><span role="columnheader" style={{ padding: '9px 14px' }}>ACTIONS</span>
            </div>
            {data.items.map((p) => {
              const active = p.status === 'active';
              return (
                <div key={p.objectid} role="row" style={{ display: 'grid', gridTemplateColumns: '170px minmax(180px,1.6fr) 112px 70px 96px 104px minmax(130px,1fr) 132px', alignItems: 'center', minHeight: 40, borderBottom: '1px solid #EFEFEB', fontSize: 12.5 }}>
                  <span role="cell" style={{ padding: '7px 14px', display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                    <span className="mono" style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'normal', wordBreak: 'break-word', overflowWrap: 'anywhere', lineHeight: 1.35 }}>{p.no}</span>
                    {p.added && <span style={{ fontSize: 9.5, fontWeight: 600, letterSpacing: '0.06em', color: '#5F6368' }}>ADDED BY ADMIN</span>}
                  </span>
                  <span role="cell" className="ellipsis" style={{ padding: '0 10px' }} title={p.holder}>{p.holder}</span>
                  <span role="cell" className="ellipsis" style={{ padding: '0 10px' }} title={p.commodity}>{p.commodity}</span>
                  <span role="cell" className="mono" style={{ padding: '0 10px', fontSize: 11.5 }}>{p.type}</span>
                  <span role="cell" style={{ padding: '0 10px' }}><span className="pill" style={{ background: active ? '#E4F1E8' : '#FBF0D6', color: '#17181A' }}>{p.status.toUpperCase()}</span></span>
                  <span role="cell" className="mono" style={{ padding: '0 10px', textAlign: 'right', fontSize: 12 }}>{p.area_ha.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
                  <span role="cell" className="ellipsis" style={{ padding: '0 10px', color: '#3D4044' }}>{p.prov}</span>
                  <span role="cell" style={{ padding: '0 14px', display: 'flex', gap: 6 }}>
                    <button type="button" className="btn" style={{ height: 26, padding: '0 9px', fontSize: 11.5 }} onClick={() => openEdit(p)}>Edit</button>
                    <button type="button" className="btn" style={{ height: 26, padding: '0 9px', fontSize: 11.5 }} onClick={() => { setDelTarget(p); setModal('delete'); }}>Delete</button>
                  </span>
                </div>
              );
            })}
            {data.items.length === 0 && <div style={{ padding: '22px 14px', textAlign: 'center', color: '#5F6368' }}>No permits match these filters.</div>}
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '6px 12px', padding: '8px 14px', borderTop: '1px solid #E2E2DE', fontSize: 11.5, color: '#5F6368' }}>
          <span className="mono">{data.items.length} shown · {data.total.toLocaleString('en-US')} permits in registry</span>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button className="btn" style={{ height: 24, padding: '0 8px' }} disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
            <span className="mono">{page} / {pages}</span>
            <button className="btn" style={{ height: 24, padding: '0 8px' }} disabled={page >= pages} onClick={() => setPage(page + 1)}>Next ›</button>
          </div>
        </div>
      </div>

      {modal === 'permit' && (
        <Modal title={form.mode === 'edit' ? `Edit permit OBJ-${form.objectid}` : 'Add permit'} width={700} labelledBy="mt-pf" onClose={() => setModal(null)}
          footer={<><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button type="button" className="btn btn-dark" onClick={savePermit}>{form.mode === 'edit' ? 'Save changes' : 'Save permit'}</button></>}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px 14px' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>PERMIT / SK NUMBER</Lbl><input className="mono" style={inStyle} value={form.no} onChange={(e) => setForm({ ...form, no: e.target.value })} placeholder="optional" /></label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>HOLDER NAME</Lbl><input style={inStyle} value={form.holder} onChange={(e) => setForm({ ...form, holder: e.target.value, err: '' })} /></label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>COMMODITY</Lbl><input style={inStyle} list="adm-pf-commodity" value={form.commodity} onChange={(e) => setForm({ ...form, commodity: e.target.value })} placeholder="e.g. NIKEL, BATUBARA, PASIR" /><datalist id="adm-pf-commodity">{(data.commodities || []).map((c) => <option key={c} value={c} />)}</datalist></label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>TYPE</Lbl><select className="select" style={{ ...inStyle, width: '100%' }} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>{(data.types && data.types.length ? data.types : ['IUP', 'IUPK', 'IPR', 'KK', 'PKP2B']).map((t) => <option key={t} value={t}>{t}</option>)}</select></label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>EXPIRY DATE</Lbl><input className="mono" type="date" style={inStyle} value={form.expiry} onChange={(e) => setForm({ ...form, expiry: e.target.value })} /></label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}><Lbl>PROVINCE</Lbl><input style={inStyle} value={form.prov} onChange={(e) => setForm({ ...form, prov: e.target.value })} list="adm-prov-opts" /><datalist id="adm-prov-opts">{(data.provinces || []).map((p) => <option key={p} value={p} />)}</datalist></label>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
              <Lbl>LOCATION · POLYGON GEOMETRY</Lbl>
              <div role="tablist" aria-label="Location input method" style={{ display: 'flex', border: '1px solid #C9C9C4', borderRadius: 4, overflow: 'hidden' }}>
                <button type="button" role="tab" aria-selected={form.loc === 'upload'} onClick={() => setForm({ ...form, loc: 'upload' })} style={{ height: 28, padding: '0 12px', border: 0, borderRight: '1px solid #C9C9C4', background: form.loc === 'upload' ? '#17181A' : '#fff', color: form.loc === 'upload' ? '#fff' : '#17181A', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>Upload GeoJSON</button>
                <button type="button" role="tab" aria-selected={form.loc === 'draw'} onClick={() => setForm({ ...form, loc: 'draw' })} style={{ height: 28, padding: '0 12px', border: 0, background: form.loc === 'draw' ? '#17181A' : '#fff', color: form.loc === 'draw' ? '#fff' : '#17181A', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>Draw on map</button>
              </div>
            </div>
            {form.loc === 'upload' ? (
              <label style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6, height: 120, border: '1.5px dashed #8A8D91', borderRadius: 5, background: '#FAFAF8', cursor: 'pointer', textAlign: 'center', padding: 12 }}>
                <input type="file" accept=".geojson,.json" onChange={onFile} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0, cursor: 'pointer' }} />
                <span style={{ fontSize: 12.5, fontWeight: 500 }}>{form.geojson ? form.fileName : 'Drop a .geojson/.json file here, or browse'}</span>
                <span style={{ fontSize: 11.5, color: '#5F6368' }}>Polygon or MultiPolygon, EPSG:4326. Validated on save.</span>
              </label>
            ) : <DrawPad poly={form.polygon} setPoly={(poly) => setForm({ ...form, polygon: poly, err: '' })} />}
            {form.mode === 'edit' && <span style={{ fontSize: 11.5, color: '#5F6368' }}>Existing geometry is kept unless you upload or draw a replacement.</span>}
          </div>
          <p style={{ margin: 0, padding: '9px 12px', background: '#FAFAF8', border: '1px solid #E2E2DE', borderRadius: 4, fontSize: 12, lineHeight: 1.45, color: '#3D4044' }}>Permits are cross-checked against existing case detections immediately after saving.</p>
          {form.err && <p role="alert" style={{ margin: 0, padding: '8px 10px', border: '1px solid #17181A', borderRadius: 4, fontSize: 12, fontWeight: 500 }}>{form.err}</p>}
        </Modal>
      )}

      {modal === 'delete' && delTarget && (
        <Modal title={`Delete permit ${delTarget.no}?`} labelledBy="mt-dp" alertdialog onClose={() => setModal(null)}
          footer={<><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button type="button" className="btn btn-dark" onClick={confirmDelete}>Delete permit</button></>}>
          <span style={{ fontSize: 12.5, color: '#3D4044', lineHeight: 1.45 }}>{delTarget.holder} · {delTarget.prov}. Cases referencing this permit are re-cross-checked after deletion and may change status. This is recorded in the activity log and cannot be undone.</span>
        </Modal>
      )}

      {modal === 'reimport' && (
        <Modal title="Re-import base registry?" labelledBy="mt-ri" alertdialog onClose={() => setModal(null)}
          footer={<><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button type="button" className="btn btn-dark" disabled={reimportBusy} onClick={confirmReimport}>{reimportBusy ? 'Re-importing…' : 'Re-import'}</button></>}>
          <div style={{ padding: '10px 12px', background: '#FBF0D6', borderRadius: 4, fontSize: 12.5, lineHeight: 1.45 }}><b>Bulk action.</b> This re-reads the permit registry from disk and re-runs the permit cross-check on every case.</div>
          <span style={{ fontSize: 12.5, color: '#3D4044', lineHeight: 1.45 }}>Case statuses can change. It is recorded in the activity log.</span>
        </Modal>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ Log --
function LogTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState('');
  const [range, setRange] = useState('all');

  useEffect(() => {
    const t = setTimeout(() => api(`/api/admin/log?q=${encodeURIComponent(q)}&range=${range}`).then(setData).catch((e) => setErr(e.message)), 200);
    return () => clearTimeout(t);
  }, [q, range]);

  if (err) return <div className="banner">Error: {err}</div>;
  if (!data) return <div className="muted">Loading…</div>;

  return (
    <section aria-label="Activity log" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '8px 12px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by actor, action or detail" style={{ ...inStyle, width: 300 }} />
          <select className="select" value={range} onChange={(e) => setRange(e.target.value)}>{RANGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </div>
        <span className="mono muted" style={{ fontSize: 11.5 }}>{data.shown} of {data.total} entries</span>
      </div>
      <div className="card">
        <div className="mw-scroll" style={{ overflowX: 'auto' }}>
          <div role="table" aria-label="Admin activity log, newest first" style={{ minWidth: 900 }}>
            <div role="row" style={{ display: 'grid', gridTemplateColumns: '170px 120px minmax(220px,1.1fr) minmax(260px,2fr)', background: '#F7F7F5', borderBottom: '1px solid #E2E2DE', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#5F6368' }}>
              <span role="columnheader" style={{ padding: '9px 14px' }}>TIMESTAMP (UTC) ↓</span><span role="columnheader" style={{ padding: '9px 10px' }}>ACTOR</span>
              <span role="columnheader" style={{ padding: '9px 10px' }}>ACTION</span><span role="columnheader" style={{ padding: '9px 14px 9px 10px' }}>DETAIL</span>
            </div>
            {data.items.map((e) => (
              <div key={e.id} role="row" style={{ display: 'grid', gridTemplateColumns: '170px 120px minmax(220px,1.1fr) minmax(260px,2fr)', alignItems: 'center', minHeight: 38, borderBottom: '1px solid #EFEFEB', fontSize: 12.5 }}>
                <span role="cell" className="mono" style={{ padding: '7px 14px', fontSize: 11.5, color: '#3D4044' }}>{fmtDateTime(e.at)}</span>
                <span role="cell" className="mono" style={{ padding: '7px 10px', fontSize: 11.5, fontWeight: 500 }}>{e.actor}</span>
                <span role="cell" style={{ padding: '7px 10px', fontWeight: 500 }}>{e.action}</span>
                <span role="cell" style={{ padding: '7px 14px 7px 10px', color: '#4A4D52', lineHeight: 1.4 }}>{e.detail}</span>
              </div>
            ))}
            {data.items.length === 0 && <div style={{ padding: '22px 14px', textAlign: 'center', color: '#5F6368' }}>No log entries match this filter and date range.</div>}
          </div>
        </div>
        <div style={{ padding: '8px 14px', borderTop: '1px solid #E2E2DE', fontSize: 11.5, color: '#5F6368' }}>Append-only. Log entries cannot be edited or deleted from this interface.</div>
      </div>
    </section>
  );
}

// ----------------------------------------------------------------- Data --
function DataTab() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api('/api/admin/status').then(setData).catch((e) => setErr(e.message)); }, []);
  if (err) return <div className="banner">Error: {err}</div>;
  if (!data) return <div className="muted">Loading…</div>;

  return (
    <section aria-label="Data status" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '4px 12px', fontSize: 12, color: '#5F6368' }}>
        <span>Read-only technical health check. Nothing on this tab can be changed.</span>
        <span className="mono" style={{ fontSize: 11.5 }}>checked {fmtDateTime(data.checked_at)}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 1, background: '#D6D6D1', border: '1px solid #D6D6D1', borderRadius: 6, overflow: 'hidden' }}>
        {data.cards.map((c) => (
          <div key={c.label} style={{ background: '#fff', padding: '14px 16px 15px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Lbl>{c.label}</Lbl>
            <span className="mono" style={{ fontSize: 20, fontWeight: 500, letterSpacing: '-0.02em' }}>{c.value}</span>
            <span className="mono muted" style={{ fontSize: 11, lineHeight: 1.5 }}>{c.sub}</span>
          </div>
        ))}
      </div>
      <div className="card" style={{ marginTop: 4 }}>
        <div style={{ padding: '9px 14px', borderBottom: '1px solid #E2E2DE', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', color: '#5F6368' }}>INTEGRATIONS</div>
        {data.integrations.map((i) => (
          <div key={i.name} style={{ display: 'grid', gridTemplateColumns: 'minmax(180px,1.2fr) minmax(200px,2fr) 90px', alignItems: 'center', minHeight: 38, borderBottom: '1px solid #EFEFEB', fontSize: 12.5 }}>
            <span style={{ padding: '0 14px', fontWeight: 500 }}>{i.name}</span>
            <span className="mono" style={{ padding: '0 10px', fontSize: 11.5, color: '#3D4044' }}>{i.note}</span>
            <span style={{ padding: '0 14px 0 10px', textAlign: 'right' }}><span style={{ display: 'inline-flex', alignItems: 'center', height: 19, padding: '0 7px', border: '1px solid #8A8D91', borderRadius: 3, fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fontWeight: 600, letterSpacing: '0.05em', color: '#3D4044' }}>{i.state}</span></span>
          </div>
        ))}
      </div>
    </section>
  );
}
