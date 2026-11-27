import { useEffect, useRef, useState } from 'react';
import { autoDailyImport, dailyLog, saveDay } from '../api.js';
import { Table, shortDate } from '../components/Charts.jsx';
import DailyImport from '../components/DailyImport.jsx';
import { todayISO } from '../lib/dates.js';
import { balanceText, macroText } from '../lib/daily.js';
import { card, dim, longDate, number, outline, solid } from './workoutStyles.js';

const GROUPS = [
  ['Weigh-in', [['weight', 'Home (lb)'], ['weight_pf', 'PF (lb)']]],
  ['Burned', [['burned_total', 'Total calories'], ['burned_active', 'Active calories']]],
  ['Eaten', [['calories_in', 'Calories'], ['carbs_g', 'Carbs (g)'], ['fat_g', 'Fat (g)'], ['protein_g', 'Protein (g)']]],
];
const NOTES = [
  ['weight_note', 'Home weigh-in note'], ['weight_pf_note', 'PF weigh-in note'], ['body_note', 'Body update'],
  ['gym_session', 'Gym session'], ['gym_note', 'Focus, feel, notes'],
];
const TEXT_KEYS = NOTES.map(([key]) => key);
const CALORIE_KEYS = ['burned_total', 'burned_active', 'calories_in', 'carbs_g', 'fat_g', 'protein_g'];
const AVERAGES = [
  ['weight', 'Home (lb)'], ['weight_pf', 'PF (lb)'], ['calories_in', 'Eaten'], ['burned_total', 'Burned'], ['burned_active', 'Active'],
  ['balance', 'Balance'], ['carbs_g', 'Carbs (g)'], ['fat_g', 'Fat (g)'], ['protein_g', 'Protein (g)'],
];
const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '9px 10px', fontSize: 16, width: '100%', minWidth: 0 };
const heading = { fontSize: 12, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent)' };

function dayLine(day) {
  return [
    day.weight !== null && `home ${number(day.weight)}`,
    day.weight_pf !== null && `PF ${number(day.weight_pf)}`,
    day.calories_in !== null && `in ${number(day.calories_in)}`,
    day.burned_total !== null && `out ${number(day.burned_total)}`,
    day.balance !== null && balanceText(day.balance),
    day.burned_total === null && day.burned_active !== null && `active ${number(day.burned_active)}`,
    macroText(day),
    day.calories_partial && `so far${day.calories_as_of ? ` at ${day.calories_as_of}` : ''}`,
    day.gym_session,
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
      <div style={dim}>Each average covers only the days with that number, shown in brackets. Unfinished (“so far”) calorie days are left out.</div>
    </section>
  );
}

// Opening Daily again sooner than this doesn't re-read the notes.
const CHECK_EVERY = 2 * 60 * 1000;

const shortDays = (dates) => dates.map(shortDate).join(', ');

// What the last automatic read of the daily notes did.
function NoteCheck({ check, onAgain }) {
  if (!check) return null;
  const link = { background: 'transparent', border: 'none', padding: 0, color: 'var(--accent)', fontSize: 12, textDecoration: 'underline' };
  if (check.busy) return <div role="status" style={dim}>Checking your daily notes…</div>;
  return (
    <div role="status" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ ...dim, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {check.error ? (
          <span style={{ color: '#ff6b6b' }}>Couldn’t check your notes: {check.error}</span>
        ) : (
          <span>
            Notes checked {check.at} · {check.saved.length ? `saved ${shortDays(check.saved)}` : 'nothing new'}
            {check.notes === 0 && ' · no notes found for the last week'}
          </span>
        )}
        <button type="button" onClick={onAgain} style={link}>Check again</button>
      </div>
      {check.review?.length > 0 && (
        <div style={{ ...card, borderColor: '#ffb020', fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ fontWeight: 600, color: '#ffb020' }}>For you to look at</div>
          {check.review.map((item) => (
            <div key={`${item.date}${item.text}`} style={{ overflowWrap: 'anywhere' }}>
              <span style={dim}>{shortDate(item.date)}: </span>
              {item.text}
            </div>
          ))}
          <div style={dim}>Use Import from daily note to pick a weight or take the note’s value, or fix the note.</div>
        </div>
      )}
    </div>
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
  const [importing, setImporting] = useState(false);
  const [check, setCheck] = useState(null);
  const checked = useRef(0);
  const form = useRef(null);
  const date = picked || todayISO();

  const refresh = () =>
    dailyLog(52)
      .then((next) => (setData(next), setError('')))
      .catch(() => setError('Couldn’t load your daily numbers.'));

  async function checkNotes() {
    checked.current = Date.now();
    setCheck({ busy: true });
    try {
      const result = await autoDailyImport();
      if (result.saved.length) await refresh();
      setCheck({ ...result, at: new Date().toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) });
    } catch (err) {
      setCheck({ error: err.message });
    }
  }

  useEffect(() => {
    if (!active) return;
    refresh();
    if (Date.now() - checked.current > CHECK_EVERY) checkNotes();
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
  const hasCalories = CALORIE_KEYS.some((key) => String(value(key)) !== '');
  // Numbers typed for today start as "so far"; earlier days as final.
  const savedCalories = saved && CALORIE_KEYS.some((key) => saved[key] !== null);
  const partial = edits.calories_partial ?? (savedCalories ? saved.calories_partial : date === todayISO());

  async function submit(event) {
    event.preventDefault();
    const fields = {};
    for (const [key, text] of Object.entries(edits)) {
      if (key === 'calories_partial') continue;
      if (TEXT_KEYS.includes(key)) {
        fields[key] = text.trim() || null;
        continue;
      }
      const trimmed = String(text).trim().replace(/,(?=\d{3}\b)/g, '').replace(',', '.');
      if (trimmed !== '' && !Number.isFinite(Number(trimmed))) return setError(`“${text}” isn’t a number`);
      fields[key] = trimmed === '' ? null : Number(trimmed);
    }
    if (hasCalories && (edits.calories_partial !== undefined || CALORIE_KEYS.some((key) => key in edits))) {
      fields.calories_partial = partial;
      if (!partial) fields.calories_as_of = null;
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
      {importing ? (
        <DailyImport
          onClose={() => setImporting(false)}
          onSaved={async () => {
            setEdits({});
            await refresh();
          }}
        />
      ) : (
        <button type="button" onClick={() => setImporting(true)} style={{ ...outline, alignSelf: 'flex-start' }}>Import from daily note</button>
      )}
      {!importing && <NoteCheck check={check} onAgain={checkNotes} />}

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
        {hasCalories && (
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={!!partial} onChange={(e) => setEdits((current) => ({ ...current, calories_partial: e.target.checked }))} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} />
            Calories are “so far”{saved?.calories_as_of && partial ? ` (as of ${saved.calories_as_of})` : ''}; leave out of averages
          </label>
        )}
        <details key={date}>
          <summary style={{ ...dim, cursor: 'pointer' }}>Notes{TEXT_KEYS.some((key) => saved?.[key]) ? ' (saved)' : ''}</summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
            {NOTES.map(([key, label]) => (
              <label key={key} style={{ ...dim, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {label}
                <textarea
                  rows={key === 'gym_note' || key === 'body_note' ? 4 : 2}
                  value={value(key)}
                  maxLength={2000}
                  onChange={(e) => {
                    const { value: text } = e.target;
                    setMessage('');
                    setEdits((current) => ({ ...current, [key]: text }));
                  }}
                  style={{ ...field, resize: 'vertical' }}
                />
              </label>
            ))}
          </div>
        </details>
        {saved?.balance !== null && saved?.balance !== undefined && (
          <div style={{ fontSize: 14 }}>
            <strong style={{ color: 'var(--accent)' }}>{balanceText(saved.balance)}</strong>
            <span style={dim}> {saved.calories_partial ? 'so far ' : ''}· eaten {number(saved.calories_in)} minus burned {number(saved.burned_total)}</span>
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
