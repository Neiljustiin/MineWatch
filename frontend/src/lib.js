// Shared constants + helpers. Colours / marker shapes are taken 1:1 from Main.dc.html & Case.dc.html.

export const ST = {
  HIGH: { fg: '#A3241C', bg: '#FBE8E5', dot: '#C8322A', map: '#E5483D', bar: '#C8322A', rad: '1px', rot: '45deg', label: 'No Matching Permit', short: 'No Match' },
  MEDIUM: { fg: '#6E4A00', bg: '#FBF0D6', dot: '#C98A12', map: '#E8A92E', bar: '#D99A1E', rad: '2px', rot: '0deg', label: 'Permit Expired', short: 'Expired' },
  LOW: { fg: '#1E6A3E', bg: '#E4F1E8', dot: '#2E8B57', map: '#45AE72', bar: '#7FB08F', rad: '50%', rot: '0deg', label: 'Inside Valid Permit', short: 'Active' },
  UNCHECKED: { fg: '#3D4044', bg: '#EDEDE9', dot: '#8A8D91', map: '#9AA0A4', bar: '#CFCFCA', rad: '50%', rot: '0deg', label: 'Not Assessed' },
};
export const STATUSES = ['HIGH', 'MEDIUM', 'LOW'];

export const COM = { Au: 'Gold', Ni: 'Nickel', C: 'Coal', Sn: 'Tin' };
export const COM_LONG = { Au: 'Gold (emas)', Ni: 'Nickel (nikel)', C: 'Coal (batubara)', Sn: 'Tin (timah)' };

export const QUALITY = {
  reliable: { label: 'Reliable', fg: '#1E6A3E', bg: '#E4F1E8' },
  light_caveat: { label: 'Light caveat', fg: '#3D4044', bg: '#EDEDE9' },
  medium_caveat: { label: 'Medium caveat', fg: '#6E4A00', bg: '#FBF0D6' },
  unreliable: { label: 'Unreliable', fg: '#A3241C', bg: '#FBE8E5' },
};

export const PST = {
  active: { label: 'ACTIVE', bg: '#E4F1E8', fg: '#1E6A3E' },
  expired: { label: 'EXPIRED', bg: '#FBF0D6', fg: '#6E4A00' },
  unknown: { label: 'UNKNOWN', bg: '#EDEDE9', fg: '#3D4044' },
};

export const DECISIONS = {
  confirmed: 'Confirmed illegal',
  verify: 'Needs field verification',
  fp: 'False positive',
  legal: 'Legal',
};

const MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const monthName = (i) => MO[i];

export function fmtDate(d) {
  if (!d) return '—';
  const p = d.slice(0, 10).split('-');
  return p[2] + ' ' + MO[parseInt(p[1], 10) - 1] + ' ' + p[0];
}

export function fmtDateTime(iso) {
  if (!iso) return '—';
  const dt = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(dt.getDate())} ${MO[dt.getMonth()]} ${dt.getFullYear()} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

export function dms(v, pos, neg) {
  const a = Math.abs(v), d = Math.floor(a), mf = (a - d) * 60, m = Math.floor(mf), s = ((mf - m) * 60).toFixed(1);
  return d + '°' + String(m).padStart(2, '0') + '′' + s.padStart(4, '0') + '″ ' + (v < 0 ? neg : pos);
}

export const ha = (v) => (v == null ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
export const pct = (v, digits = 1) => (v == null ? '—' : (v * 100).toFixed(digits) + '%');

export function monthIndex(dateStr) {
  const [y, m] = dateStr.split('-').map(Number);
  return y * 12 + (m - 1);
}

export function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
}

export async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401) {
    window.location.href = '/login';
    throw new Error('login required');
  }
  if (!r.ok) {
    let msg = r.status + ' ' + r.statusText;
    try { const j = await r.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}
