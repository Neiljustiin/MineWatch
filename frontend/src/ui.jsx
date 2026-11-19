import React from 'react';
import { ST, QUALITY } from './lib.js';

export function StatusPill({ status, big }) {
  const st = ST[status] || ST.UNCHECKED;
  return (
    <span className="pill" style={{ background: st.bg, color: st.fg, ...(big ? { height: 24, padding: '0 9px', fontSize: 11, letterSpacing: '0.06em', gap: 6 } : {}) }}>
      <span className="mk" style={{ background: st.dot, borderRadius: st.rad, transform: `rotate(${st.rot})`, ...(big ? { width: 7, height: 7 } : {}) }} />
      {st.label}
    </span>
  );
}

export function QualityChip({ q }) {
  const s = QUALITY[q] || QUALITY.light_caveat;
  return <span className="pill" style={{ background: s.bg, color: s.fg, fontWeight: 600, letterSpacing: '0.02em' }}>{s.label}</span>;
}

