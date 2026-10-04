// All dates here are plain local calendar dates as 'YYYY-MM-DD' strings —
// matching what the API stores in due_date columns. Parsed by hand instead
// of `new Date('2026-10-03')`, which JS treats as UTC midnight and so shows
// up as the previous day for anyone west of Greenwich.

export function toISODate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function todayISO() {
  return toISODate(new Date());
}

export function parseISODate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

export function addDays(iso, n) {
  const d = parseISODate(iso);
  d.setDate(d.getDate() + n);
  return toISODate(d);
}

const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function daysFromToday(iso) {
  const d = parseISODate(iso);
  if (!d) return null;
  return Math.round((d - parseISODate(todayISO())) / 86400000);
}

// "Today" / "Tomorrow" / "Yesterday" / "Oct 3" (+ year when it isn't this
// year) — an ISO string like 2026-10-03 is exact but slow to read at a
// glance, which is the whole point of showing a due date at all.
export function formatDue(iso) {
  const diff = daysFromToday(iso);
  if (diff === null) return '';
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  if (diff === -1) return 'Yesterday';
  const d = parseISODate(iso);
  const label = `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`;
  return d.getFullYear() === new Date().getFullYear() ? label : `${label}, ${d.getFullYear()}`;
}

export function dueTone(iso) {
  const diff = daysFromToday(iso);
  if (diff === null) return 'later';
  if (diff < 0) return 'overdue';
  if (diff === 0) return 'today';
  return 'later';
}

export const DUE_COLORS = {
  overdue: '#ff6b6b',
  today: 'var(--accent)',
  later: 'var(--text-dim)',
};
