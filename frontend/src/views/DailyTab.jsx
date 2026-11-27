import { useEffect, useRef, useState } from 'react';
import { dailyLog, saveDay } from '../api.js';
import { Table, shortDate } from '../components/Charts.jsx';
import { todayISO } from '../lib/dates.js';
import { balanceText, macroText } from '../lib/daily.js';
import { card, dim, longDate, number, outline, solid } from './workoutStyles.js';

const GROUPS = [
  ['Body', [['weight', 'Weight (lb)']]],
  ['Burned', [['burned_total', 'Total calories'], ['burned_active', 'Active calories']]],
  ['Eaten', [['calories_in', 'Calories'], ['protein_g', 'Protein (g)'], ['carbs_g', 'Carbs (g)'], ['fat_g', 'Fat (g)']]],
];
const AVERAGES = [
  ['weight', 'Weight (lb)'], ['calories_in', 'Eaten'], ['burned_total', 'Burned'], ['burned_active', 'Active'],
  ['balance', 'Balance'], ['protein_g', 'Protein (g)'], ['carbs_g', 'Carbs (g)'], ['fat_g', 'Fat (g)'],
];
const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '9px 10px', fontSize: 16, width: '100%', minWidth: 0 };
const heading = { fontSize: 12, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent)' };

function dayLine(day) {
  return [
    day.weight !== null && `${number(day.weight)} lb`,
    day.calories_in !== null && `in ${number(day.calories_in)}`,
    day.burned_total !== null && `out ${number(day.burned_total)}`,
    day.balance !== null && balanceText(day.balance),
    day.burned_total === null && day.burned_active !== null && `active ${number(day.burned_active)}`,
    macroText(day),
  ]
    .filter(Boolean)
    .join(' · ');
}

// This week's averages beside last week's, each over the days that have it.
function Weeks({ now, before }) {
  if (now.days === 0 && before.days === 0) return null;
  const shown = (week, key) => {
    const value = week.average[key];
    if (value === null) return '—';
    const text = key === 'balance' ? balanceText(value) : number(value);
    return `${text} (${week.counts[key]}d)`;
  };
  const rows = AVERAGES.filter(([key]) => now.average[key] !== null || before.average[key] !== null).map(([key, name]) => [name, shown(now, key), shown(before, key)]);
  return (
    <section style={{ ...card, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>Daily averages</h2>
      <Table maxHeight={null} headings={['', 'This week', 'Last week']} rows={rows} />
      <div style={dim}>Each average covers only the days with that number, shown in brackets.</div>
    </section>
  );
}

// `focus` changes when the + button asks for today's numbers.
export default function DailyTab({ active, focus, onSaved }) {
  const [data, setData] = useState(null);
  // null follows today, so a page left open overnight moves on with it.
  const [picked, setPicked] = useState(null);
  // Only what has been typed; everything else shows the saved value.
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [all, setAll] = useState(false);
  const form = useRef(null);
  const date = picked || todayISO();

  const refresh = () =>
    dailyLog(52)
      .then((next) => (setData(next), setError('')))
      .catch(() => setError('Couldn’t load your daily numbers.'));

  useEffect(() => {
    if (active) refresh();
  }, [active]);

  function choose(next) {
    setPicked(next === todayISO() ? null : next);
    setEdits({});
    setMessage('');
    setError('');
  }

  useEffect(() => {
    if (!focus) return;
    choose(todayISO());
    // After the tab has become visible.
    setTimeout(() => form.current?.querySelector('input[inputmode]')?.focus(), 50);
  }, [focus]);

  const saved = data?.days.find((d) => d.date === date);
  const value = (key) => edits[key] ?? saved?.[key] ?? '';
  const changed = Object.keys(edits).length > 0;

  async function submit(event) {
    event.preventDefault();
    const fields = {};
    for (const [key, text] of Object.entries(edits)) {
      const trimmed = String(text).trim().replace(/,(?=\d{3}\b)/g, '').replace(',', '.');
      if (trimmed !== '' && !Number.isFinite(Number(trimmed))) return setError(`“${text}” isn’t a number`);
      fields[key] = trimmed === '' ? null : Number(trimmed);
    }
    setBusy(true);
    setError('');
    try {
      await saveDay(date, fields);
      await refresh();
      setEdits({});
      setMessage('Saved.');
      onSaved?.();
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  if (data === null) return <div style={dim}>{error || 'Loading…'}</div>;
  const days = all ? data.days : data.days.slice(0, 14);

  return (
    <>
      <form ref={form} onSubmit={submit} style={{ ...card, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>{date === todayISO() ? 'Today' : longDate(date)}</div>
          <input type="date" aria-label="Day" value={date} max={todayISO()} onChange={(e) => e.target.value && choose(e.target.value)} style={{ ...field, width: 'auto', marginLeft: 'auto', fontSize: 14 }} />
        </div>
        {GROUPS.map(([name, fields]) => (
          <fieldset key={name} style={{ border: 'none', padding: 0, margin: 0, minWidth: 0 }}>
            <legend style={{ ...heading, padding: 0, marginBottom: 6 }}>{name}</legend>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
              {fields.map(([key, label]) => (
                <label key={key} style={{ ...dim, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                  {label}
                  <input
                    inputMode="decimal"
                    value={value(key)}
                    onChange={(e) => {
                      const { value: text } = e.target;
                      setMessage('');
                      setEdits((current) => ({ ...current, [key]: text }));
                    }}
                    style={field}
                  />
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        {saved?.balance !== null && saved?.balance !== undefined && (
          <div style={{ fontSize: 14 }}>
            <strong style={{ color: 'var(--accent)' }}>{balanceText(saved.balance)}</strong>
            <span style={dim}> · eaten {number(saved.calories_in)} minus burned {number(saved.burned_total)}</span>
          </div>
        )}
        {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button type="submit" disabled={busy || !changed} style={{ ...solid, opacity: changed ? 1 : 0.5 }}>{busy ? 'Saving…' : 'Save'}</button>
          {changed && <button type="button" onClick={() => choose(date)} style={outline}>Undo changes</button>}
          {message && <span role="status" style={{ fontSize: 13, color: 'var(--accent)' }}>{message}</span>}
        </div>
      </form>

      <Weeks now={data.this_week} before={data.last_week} />

      {data.days.length > 0 && (
        <section style={card}>
          <h2 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 4px' }}>Logged days</h2>
          {days.map((day) => (
            <button
              key={day.date}
              type="button"
              onClick={() => {
                choose(day.date);
                form.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
              }}
              style={{ display: 'block', width: '100%', background: 'transparent', border: 'none', borderTop: '1px solid var(--border)', padding: '8px 0', color: 'var(--text)', textAlign: 'left' }}
            >
              <div style={{ fontSize: 13, fontWeight: day.date === date ? 700 : 400, color: day.date === date ? 'var(--accent)' : 'var(--text)' }}>
                {day.date === data.today ? 'Today' : shortDate(day.date)}
              </div>
              <div style={dim}>{dayLine(day)}</div>
            </button>
          ))}
          {data.days.length > 14 && (
            <button type="button" onClick={() => setAll(!all)} style={{ ...outline, marginTop: 8, padding: '5px 12px', fontSize: 12 }}>
              {all ? 'Show fewer' : `Show all ${data.days.length}`}
            </button>
          )}
        </section>
      )}
    </>
  );
}
