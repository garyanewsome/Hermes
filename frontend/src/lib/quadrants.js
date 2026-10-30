// The Board's four quadrants — shared by the Board itself and the Today page.
export const QUADRANTS = [
  { key: 'do', label: 'TODO', color: '#3bffa0', glow: 'rgba(59,255,160,0.35)' },
  { key: 'schedule', label: 'Schedule / plan', color: '#ff9d3b', glow: 'rgba(255,157,59,0.35)' },
  { key: 'next', label: 'NEXT', color: '#eaff3b', glow: 'rgba(234,255,59,0.35)' },
  { key: 'backlog', label: 'Backlog', color: '#6a6b70', glow: 'transparent', dim: true },
];

export const QUADRANT_BY_KEY = Object.fromEntries(QUADRANTS.map((q) => [q.key, q]));

// Stacked top to bottom on mobile, where reading order is priority order:
// TODO, NEXT, Schedule, Backlog. The desktop grid keeps QUADRANTS' order
// (TODO | Schedule over NEXT | Backlog), which reads correctly as a 2x2.
export const MOBILE_QUADRANTS = ['do', 'next', 'schedule', 'backlog'].map((key) => QUADRANT_BY_KEY[key]);
