import { useEffect, useState } from 'react';
import { exerciseHistory, workoutCharts } from '../api.js';
import { Bars, ChartCard, DayGrid, Line, Table, shortDate } from '../components/Charts.jsx';
import { minutesText } from '../lib/activities.js';
import { dim, number, outline, solid } from './workoutStyles.js';

const RANGES = [
  [4, '4 weeks'],
  [13, '3 months'],
  [52, 'Year'],
];
const LB_PER_KG = 2.20462;
const select = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '7px 10px', fontSize: 13, maxWidth: '100%' };
const plural = (count, word, many = `${word}s`) => `${count} ${count === 1 ? word : many}`;

function setText(set) {
  if (set.weight === null) return `${set.reps} reps`;
  const side = set.per_side === null ? '' : ` (${number(set.per_side)} a side)`;
  return `${number(set.weight)} ${set.unit || 'lb'}${side} × ${set.reps}`;
}

const nowrap = (text) => <span style={{ whiteSpace: 'nowrap' }}>{text}</span>;

function Toggle({ options, value, onChange }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {options.map(([key, text, disabled]) => (
        <button key={key} type="button" disabled={disabled} onClick={() => onChange(key)} aria-pressed={value === key} style={{ ...(value === key ? solid : outline), padding: '5px 12px', fontSize: 12, opacity: disabled ? 0.4 : 1 }}>
          {text}
        </button>
      ))}
    </div>
  );
}

function ExerciseChart({ data }) {
  const names = data.bests.map((b) => b.exercise);
  // Start on the most recently trained lift that has a weight to plot.
  const fallback = (data.bests.find((b) => b.weight !== null) || data.bests[0]).exercise;
  const [choice, setChoice] = useState('');
  const name = names.includes(choice) ? choice : fallback;
  const [history, setHistory] = useState(null);

  useEffect(() => {
    let current = true;
    exerciseHistory(name)
      .then((next) => current && setHistory({ name, ...next }))
      .catch(() => current && setHistory({ name, failed: true }));
    return () => {
      current = false;
    };
  }, [name, data]);

  const ready = history && history.name === name && !history.failed;
  const weighted = ready && history.best.weight !== null;
  const points = ready
    ? history.days
        .filter((d) => d.date >= data.start && (d.best.weight !== null) === weighted)
        .map((d) => ({
          date: d.date,
          value: weighted ? d.best.weight * (d.best.unit === 'kg' ? LB_PER_KG : 1) : d.best.reps,
          detail: setText(d.best),
        }))
        .reverse()
    : [];
  const picker = (
    <select value={name} onChange={(e) => setChoice(e.target.value)} aria-label="Exercise" style={select}>
      {[...names].sort((a, b) => a.localeCompare(b)).map((n) => <option key={n} value={n}>{n}</option>)}
    </select>
  );
  if (!ready) {
    return (
      <ChartCard title="Top set" controls={picker}>
        <div style={dim}>{history?.failed && history.name === name ? 'Couldn’t load that exercise.' : 'Loading…'}</div>
      </ChartCard>
    );
  }
  return (
    <Line
      key={`${name}|${data.start}`}
      title={weighted ? 'Top set weight (lb)' : 'Top set reps'}
      controls={picker}
      points={points}
      start={data.start}
      end={data.today}
      valueHeading="Top set"
    />
  );
}

function ActivityChart({ data }) {
  const [choice, setChoice] = useState('');
  const [measure, setMeasure] = useState('time');
  const chosen =
    data.activities.find((a) => a.activity === choice) ||
    data.activities.find((a) => a.activity === 'Work walk') ||
    data.activities[0];
  if (!chosen) {
    return (
      <ChartCard title="Activities">
        <div style={dim}>No activities in this range. Add one on the Activity tab.</div>
      </ChartCard>
    );
  }
  const hasDistance = chosen.weeks.some((w) => w.miles > 0);
  const shown = hasDistance ? measure : 'time';
  const points = chosen.weeks.map((w) => ({
    key: w.start,
    label: `Week of ${shortDate(w.start)}`,
    value: shown === 'time' ? w.seconds / 60 : w.miles,
    detail: [plural(w.count, 'entry', 'entries'), minutesText(w.seconds), w.miles > 0 && `${number(w.miles)} mi`].filter(Boolean).join(' · '),
  }));
  return (
    <Bars
      title={shown === 'time' ? 'Activity minutes per week' : 'Activity miles per week'}
      controls={
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <select value={chosen.activity} onChange={(e) => setChoice(e.target.value)} aria-label="Activity" style={select}>
            {data.activities.map((a) => <option key={a.activity} value={a.activity}>{a.activity}</option>)}
          </select>
          <Toggle options={[['time', 'Time'], ['distance', 'Distance', !hasDistance]]} value={shown} onChange={setMeasure} />
        </div>
      }
      points={points}
      valueHeading="Total"
    />
  );
}

function Bests({ bests }) {
  const [all, setAll] = useState(false);
  const shown = all ? bests : bests.slice(0, 8);
  return (
    <ChartCard title="Personal bests, all time">
      <Table
        maxHeight={null}
        headings={['Exercise', 'Best', 'Date']}
        rows={shown.map((b) => [b.exercise, nowrap(setText(b)), nowrap(shortDate(b.date))])}
      />
      {bests.length > 8 && (
        <button type="button" onClick={() => setAll(!all)} style={{ ...outline, alignSelf: 'flex-start', padding: '5px 12px', fontSize: 12 }}>
          {all ? 'Show fewer' : `Show all ${bests.length}`}
        </button>
      )}
    </ChartCard>
  );
}

export default function ChartsTab({ active }) {
  const [weeks, setWeeks] = useState(13);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    workoutCharts(weeks)
      .then((next) => current && (setData({ ...next, range: weeks }), setError('')))
      .catch(() => current && setError('Couldn’t load the charts.'));
    return () => {
      current = false;
    };
  }, [active, weeks]);

  const describe = (day) => {
    if (!day) return 'nothing logged';
    return [
      day.sets > 0 && `${plural(day.sets, 'set')}, ${number(day.volume)} lb`,
      day.activities > 0 && `${day.activities === 1 ? '1 activity' : `${day.activities} activities`}, ${minutesText(day.seconds)}`,
    ]
      .filter(Boolean)
      .join(' · ');
  };

  return (
    <>
      <Toggle options={RANGES} value={weeks} onChange={setWeeks} />
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      {!data && !error && <div style={dim}>Loading…</div>}
      {data && (
        <>
          <DayGrid start={data.start} today={data.today} weeks={data.range} days={data.days} describe={describe} />
          <Bars
            key={`volume-${data.range}`}
            title="Lifting volume per week (lb)"
            valueHeading="Volume"
            points={data.weeks.map((w) => ({
              key: w.start,
              label: `Week of ${shortDate(w.start)}`,
              value: w.volume,
              detail: `${number(w.volume)} lb · ${plural(w.sets, 'set')} · ${plural(w.gym_days, 'gym day')}`,
            }))}
          />
          {data.bests.length > 0 && <ExerciseChart data={data} />}
          <ActivityChart data={data} />
          {data.bests.length > 0 && <Bests bests={data.bests} />}
        </>
      )}
    </>
  );
}
