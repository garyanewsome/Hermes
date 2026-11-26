// Shared by the Workouts page's tabs.
import { parseISODate } from '../lib/dates.js';

export const card = { background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px' };
export const dim = { fontSize: 12, color: 'var(--text-dim)' };
export const outline = { background: 'transparent', border: '1px solid var(--accent-glow)', color: 'var(--accent)', borderRadius: 8, padding: '7px 14px', fontSize: 13, fontWeight: 600 };
export const solid = { ...outline, background: 'var(--accent)', color: 'var(--accent-text)' };

export const number = (value) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });
export const longDate = (iso) => parseISODate(iso).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
