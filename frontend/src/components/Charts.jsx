// Small single-series SVG charts for the Workouts page. Hovering, tapping or
// tabbing to a mark puts its details in the line above the plot, which works
// the same with a mouse, a thumb or a keyboard.
import { useEffect, useRef, useState } from 'react';
import { addDays, parseISODate } from '../lib/dates.js';
import { card, dim, number, outline } from '../views/workoutStyles.js';

const AXIS = { fill: 'var(--text-dim)', fontSize: 11 };
const GRID = 'var(--border)';
const HEIGHT = 190;
const MARGIN = { top: 8, right: 8, bottom: 22, left: 42 };

export const shortDate = (iso) => parseISODate(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
const tickText = (value) => (value >= 10000 ? `${number(value / 1000)}K` : number(value));

// Evenly spaced round numbers covering [low, high].
function ticks(low, high, count = 4) {
  const span = high - low || Math.abs(high) || 1;
  const rough = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough);
  const first = Math.floor(low / step) * step;
  const out = [first];
  while (out[out.length - 1] < high || out.length < 2) out.push(out[out.length - 1] + step);
  return out;
}

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    // Reports 0 while the tab is hidden, and again once it's shown.
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export function ChartCard({ title, controls, readout, table, children }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section style={{ ...card, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>{title}</h2>
        {table && (
          <button type="button" onClick={() => setAsTable(!asTable)} aria-pressed={asTable} style={{ ...outline, marginLeft: 'auto', padding: '3px 9px', fontSize: 11, fontWeight: 400 }}>
            {asTable ? 'Show chart' : 'Show table'}
          </button>
        )}
      </div>
      {controls}
      {readout !== undefined && !asTable && <div aria-live="polite" style={{ fontSize: 13, minHeight: 18 }}>{readout}</div>}
      {asTable ? <Table {...table} /> : children}
    </section>
  );
}

// maxHeight keeps a long chart table scrolling; null shows every row.
export function Table({ headings, rows, maxHeight = 320 }) {
  const cell = { textAlign: 'left', padding: '5px 10px 5px 0', borderBottom: `1px solid ${GRID}`, fontSize: 13, verticalAlign: 'top' };
  return (
    <div style={{ overflow: 'auto', maxHeight: maxHeight ?? undefined }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>{headings.map((h) => <th key={h} style={{ ...cell, ...dim, fontWeight: 400 }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j} style={cell}>{value}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function YAxis({ values, y, width }) {
  return values.map((value) => (
    <g key={value}>
      <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(value)} y2={y(value)} stroke={GRID} />
      <text x={MARGIN.left - 6} y={y(value) + 4} textAnchor="end" style={AXIS}>{tickText(value)}</text>
    </g>
  ));
}

const interactive = (index, setActive, label) => ({
  tabIndex: 0,
  role: 'img',
  'aria-label': label,
  onPointerEnter: () => setActive(index),
  onPointerDown: () => setActive(index),
  onFocus: () => setActive(index),
});

// points: [{ key, label, value, detail }], one per week, oldest first.
export function Bars({ title, controls, points, valueHeading }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const shown = points[active] || points[points.length - 1];
  const values = ticks(0, Math.max(...points.map((p) => p.value), 1));
  const top = values[values.length - 1];
  const inner = Math.max(width - MARGIN.left - MARGIN.right, 0);
  const slot = inner / points.length;
  const bar = Math.max(Math.min(24, slot - 2), 1);
  const y = (value) => MARGIN.top + (HEIGHT - MARGIN.top - MARGIN.bottom) * (1 - value / top);
  const every = Math.max(Math.ceil(52 / (slot || 1)), 1);

  return (
    <ChartCard
      title={title}
      controls={controls}
      readout={shown && `${shown.label} · ${shown.detail}`}
      table={{ headings: ['Week of', valueHeading], rows: [...points].reverse().map((p) => [shortDate(p.key), p.detail]) }}
    >
      <div ref={ref} onPointerLeave={() => setActive(null)}>
        {width > 0 && (
          <svg width={width} height={HEIGHT} style={{ display: 'block' }}>
            <YAxis values={values} y={y} width={width} />
            {points.map((point, i) => {
              const x = MARGIN.left + slot * i + (slot - bar) / 2;
              const height = y(0) - y(point.value);
              const radius = Math.min(4, bar / 2, height);
              return (
                <g key={point.key} {...interactive(i, setActive, `${point.label}: ${point.detail}`)}>
                  {/* The whole column is the target, not just the bar. */}
                  <rect x={MARGIN.left + slot * i} y={MARGIN.top} width={slot} height={y(0) - MARGIN.top} fill="transparent" />
                  {height > 0 && (
                    <path
                      d={`M${x},${y(0)}v${radius - height}q0,${-radius} ${radius},${-radius}h${bar - 2 * radius}q${radius},0 ${radius},${radius}v${height - radius}z`}
                      fill="var(--accent)"
                      opacity={active === null || active === i ? 1 : 0.5}
                    />
                  )}
                  {/* The last label ends at the edge so it isn't cut off. */}
                  {(points.length - 1 - i) % every === 0 && (
                    <text
                      x={i === points.length - 1 ? width : x + bar / 2}
                      y={HEIGHT - 6}
                      textAnchor={i === points.length - 1 ? 'end' : 'middle'}
                      style={AXIS}
                    >
                      {shortDate(point.key)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </ChartCard>
  );
}

// points: [{ date, value, detail }], oldest first. Spaced by date.
export function Line({ title, controls, points, start, end, valueHeading }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null);
  const shown = points[active] || points[points.length - 1];
  const all = points.map((p) => p.value);
  const pad = Math.max((Math.max(...all) - Math.min(...all)) * 0.15, Math.max(...all) * 0.05, 1);
  const values = points.length ? ticks(Math.max(Math.min(...all) - pad, 0), Math.max(...all) + pad) : [0, 1];
  const [low, high] = [values[0], values[values.length - 1]];
  const day = (iso) => parseISODate(iso).getTime();
  const left = MARGIN.left + 8;
  const right = width - MARGIN.right - 8;
  const x = (iso) => left + ((day(iso) - day(start)) / (day(end) - day(start) || 1)) * (right - left);
  const y = (value) => MARGIN.top + (HEIGHT - MARGIN.top - MARGIN.bottom) * (1 - (value - low) / (high - low));

  return (
    <ChartCard
      title={title}
      controls={controls}
      readout={shown ? `${shortDate(shown.date)} · ${shown.detail}` : ''}
      table={points.length ? { headings: ['Date', valueHeading], rows: [...points].reverse().map((p) => [shortDate(p.date), p.detail]) } : undefined}
    >
      <div ref={ref} onPointerLeave={() => setActive(null)}>
        {points.length === 0 && <div style={dim}>Nothing in this range.</div>}
        {width > 0 && points.length > 0 && (
          <svg width={width} height={HEIGHT} style={{ display: 'block' }}>
            <YAxis values={values} y={y} width={width} />
            <text x={left} y={HEIGHT - 6} style={AXIS}>{shortDate(start)}</text>
            <text x={right} y={HEIGHT - 6} textAnchor="end" style={AXIS}>{shortDate(end)}</text>
            <polyline points={points.map((p) => `${x(p.date)},${y(p.value)}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {points.map((point, i) => (
              <g key={point.date} {...interactive(i, setActive, `${shortDate(point.date)}: ${point.detail}`)}>
                <circle cx={x(point.date)} cy={y(point.value)} r="12" fill="transparent" />
                <circle cx={x(point.date)} cy={y(point.value)} r={active === i ? 6 : 4} fill="var(--accent)" stroke="var(--panel)" strokeWidth="2" />
              </g>
            ))}
          </svg>
        )}
      </div>
    </ChartCard>
  );
}

// Gym is a filled square, other activity an outline, both a filled square
// with a dot: told apart by shape, not color alone.
function Cell({ x, y, size, info }) {
  const gym = info?.sets > 0;
  const other = info?.activities > 0;
  return (
    <>
      <rect
        x={x + 0.75}
        y={y + 0.75}
        width={size - 1.5}
        height={size - 1.5}
        rx="3"
        fill={gym ? 'var(--accent)' : info ? 'transparent' : 'var(--border)'}
        stroke={other && !gym ? 'var(--accent)' : 'none'}
        strokeWidth="1.5"
      />
      {gym && other && <circle cx={x + size / 2} cy={y + size / 2} r={size / 6} fill="var(--panel)" />}
    </>
  );
}

export function DayGrid({ start, today, weeks, days, describe }) {
  const [ref, width] = useWidth();
  const scroller = useRef(null);
  const [active, setActive] = useState(null);
  const size = Math.max(Math.min(24, Math.floor((width - 30) / weeks) - 2), 13);
  const step = size + 2;
  const byDate = new Map(days.map((d) => [d.date, d]));
  const cells = [];
  for (let i = 0; i < weeks * 7; i += 1) {
    const date = addDays(start, i);
    // Future days are left blank, apart from anything already logged on them.
    if (date <= today || byDate.has(date)) cells.push({ date, week: Math.floor(i / 7), weekday: i % 7 });
  }
  // A year doesn't fit a phone; start at the recent end.
  useEffect(() => {
    if (scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth;
  }, [width, weeks]);
  const key = (info) => (
    <svg width="14" height="14" aria-hidden="true" style={{ verticalAlign: -2, marginRight: 5 }}>
      <Cell x={0} y={0} size={14} info={info} />
    </svg>
  );
  const shown = active || today;
  return (
    <ChartCard title="Workout days" readout={`${shortDate(shown)} · ${describe(byDate.get(shown))}`}>
      <div ref={ref}>
        {width > 0 && (
          <div ref={scroller} onPointerLeave={() => setActive(null)} style={{ overflowX: 'auto' }}>
            <svg width={28 + weeks * step} height={16 + 7 * step} style={{ display: 'block' }}>
              {['Mon', '', 'Wed', '', 'Fri', '', 'Sun'].map((name, i) => (
                <text key={i} x="0" y={16 + i * step + size / 2 + 4} style={AXIS}>{name}</text>
              ))}
              {Array.from({ length: weeks }, (_, week) => {
                const monday = addDays(start, week * 7);
                // A month name where the month changes.
                return parseISODate(monday).getDate() <= 7 ? (
                  <text key={week} x={28 + week * step} y="10" style={AXIS}>
                    {parseISODate(monday).toLocaleDateString(undefined, { month: 'short' })}
                  </text>
                ) : null;
              })}
              {cells.map(({ date, week, weekday }) => (
                <g
                  key={date}
                  {...interactive(date, setActive, `${shortDate(date)}: ${describe(byDate.get(date))}`)}
                  tabIndex={byDate.has(date) ? 0 : -1}
                >
                  <rect x={28 + week * step} y={16 + weekday * step} width={step} height={step} fill="transparent" />
                  <Cell x={28 + week * step} y={16 + weekday * step} size={size} info={byDate.get(date)} />
                </g>
              ))}
            </svg>
          </div>
        )}
      </div>
      <div style={{ ...dim, display: 'flex', flexWrap: 'wrap', gap: 14 }}>
        <span>{key({ sets: 1, activities: 0 })}Gym</span>
        <span>{key({ sets: 0, activities: 1 })}Activity</span>
        <span>{key({ sets: 1, activities: 1 })}Both</span>
      </div>
    </ChartCard>
  );
}
