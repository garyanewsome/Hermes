import { addDays, parseISODate } from './dates.js';

const number = (value) => value.toLocaleString(undefined, { maximumFractionDigits: 2 });

export const minutesText = (seconds) => `${number(seconds / 60)} min`;

// Miles and kilometres are totalled separately, never mixed.
export function totalsText(entries) {
  const distance = {};
  let seconds = 0;
  entries.forEach((entry) => {
    if (entry.distance !== null) distance[entry.distance_unit] = (distance[entry.distance_unit] || 0) + entry.distance;
    seconds += entry.duration_seconds || 0;
  });
  return [
    `${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}`,
    ...Object.entries(distance).map(([unit, total]) => `${number(total)} ${unit}`),
    seconds > 0 && minutesText(seconds),
  ]
    .filter(Boolean)
    .join(' · ');
}

export function paceText(entry) {
  if (entry.distance === null || !entry.duration_seconds) return '';
  const perUnit = Math.round(entry.duration_seconds / entry.distance);
  return `${Math.floor(perUnit / 60)}:${String(perUnit % 60).padStart(2, '0')} /${entry.distance_unit}`;
}

// Monday of the entry's week.
export function weekStart(iso) {
  return addDays(iso, -((parseISODate(iso).getDay() + 6) % 7));
}

// Keeps the order entries arrive in (newest first).
export function groupBy(entries, key) {
  const groups = new Map();
  entries.forEach((entry) => {
    const name = key(entry);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(entry);
  });
  return [...groups];
}
