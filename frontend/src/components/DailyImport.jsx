import { useEffect, useState } from 'react';
import { previewDailyImport, saveDailyImport } from '../api.js';
import { card, dim, longDate, number, outline, solid } from '../views/workoutStyles.js';

const RANGES = [
  [7, 'Last 7 days'],
  [31, 'Last month'],
  [400, 'Everything'],
];
const NAMES = {
  weight: 'Home weight', weight_pf: 'PF weight', burned_total: 'Burned', burned_active: 'Active', calories_in: 'Eaten',
  carbs_g: 'Carbs', fat_g: 'Fat', protein_g: 'Protein', weight_note: 'Home note', weight_pf_note: 'PF note',
  body_note: 'Body update', gym_session: 'Gym session', gym_note: 'Gym notes', calories_as_of: 'Calories as of',
};
const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '7px 9px', fontSize: 16, width: 90 };
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
const shown = (value) => (value === null || value === undefined ? '—' : typeof value === 'number' ? number(value) : value);
const minutes = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

// One day of the preview. `choice` holds what the user changed from the note.
function Day({ day, choice, onChange }) {
  const { include = true, weights = {}, counted } = choice;
  const partial = day.fields.calories_partial === true;
  const changed = Object.keys(day.changes).filter((name) => name !== 'calories_partial');
  const weightKeys = ['weight', 'weight_pf'].filter((key) => day.changes[key] || (day.weights[key] && day.changes[`${key}_note`]));
  return (
    <section style={{ ...card, display: 'flex', flexDirection: 'column', gap: 8, opacity: include ? 1 : 0.55 }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14, fontWeight: 600 }}>
        {day.status !== 'unchanged' && (
          <input type="checkbox" checked={include} onChange={(e) => onChange({ include: e.target.checked })} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} />
        )}
        {longDate(day.date)}
        <span style={{ ...dim, marginLeft: 'auto', color: 'var(--accent)', fontWeight: 400 }}>{day.status}</span>
      </label>
      {weightKeys.map((key) => (
        <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, fontSize: 13 }}>
            {NAMES[key]}
            <input inputMode="decimal" aria-label={`${NAMES[key]} ${day.date}`} value={weights[key] ?? day.fields[key] ?? ''} onChange={(e) => onChange({ weights: { ...weights, [key]: e.target.value } })} style={field} />
            {(day.weights[key] || []).length > 1 &&
              day.weights[key].map((option) => (
                <button key={option} type="button" onClick={() => onChange({ weights: { ...weights, [key]: String(option) } })} style={{ ...outline, padding: '4px 10px', fontSize: 12 }}>
                  {option}
                </button>
              ))}
            {day.weights[key] && <span style={{ fontSize: 12, color: '#ffb020' }}>check this</span>}
          </div>
          <div style={{ ...dim, overflowWrap: 'anywhere' }}>“{day.fields[`${key}_note`]}”</div>
        </div>
      ))}
      {changed
        // A cleared time is covered by the "now final" line below.
        .filter((name) => !name.startsWith('weight') && !(name === 'calories_as_of' && day.changes[name][1] === null))
        .map((name) => {
          const [before, after] = day.changes[name];
          return (
            <div key={name} style={{ fontSize: 13, overflowWrap: 'anywhere', whiteSpace: 'pre-line' }}>
              <span style={dim}>{NAMES[name]}: </span>
              {before !== null && before !== undefined && <span style={{ ...dim, textDecoration: 'line-through' }}>{shown(before)} </span>}
              {shown(after)}
            </div>
          );
        })}
      {day.changes.calories_partial?.[0] === true && !partial && <div style={{ fontSize: 13 }}>Calories now counted as final.</div>}
      {partial && (
        <label style={{ ...dim, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={!!counted} onChange={(e) => onChange({ counted: e.target.checked })} style={{ width: 16, height: 16, accentColor: 'var(--accent)' }} />
          Calories are “so far”. Tick if these are the day’s final numbers.
        </label>
      )}
      {(day.new_walks > 0 || day.removed_walks > 0) && (
        <div style={{ fontSize: 13 }}>
          <span style={dim}>Walks: </span>
          {day.walks.map((w) => [minutes(w.seconds), w.distance !== null && `${number(w.distance)} ${w.unit}`].filter(Boolean).join(' ')).join(', ')}
          <span style={dim}> ({day.new_walks} new{day.removed_walks > 0 && `, replaces ${day.removed_walks} imported`})</span>
        </div>
      )}
      {day.warnings.map((text) => <div key={text} style={{ fontSize: 12, color: '#ffb020' }}>{text}</div>)}
    </section>
  );
}

// The day as it will be saved, with the preview's edits applied.
function payload(day, { weights = {}, counted }) {
  const fields = { ...day.fields };
  for (const [key, text] of Object.entries(weights)) {
    const trimmed = String(text).trim().replace(',', '.');
    if (trimmed === '') delete fields[key];
    else if (Number.isFinite(Number(trimmed))) fields[key] = Number(trimmed);
    else throw new Error(`${longDate(day.date)}: “${text}” isn’t a weight`);
  }
  if (fields.calories_partial && counted) Object.assign(fields, { calories_partial: false, calories_as_of: null });
  return { date: day.date, fields, walks: day.walks };
}

export default function DailyImport({ onClose, onSaved }) {
  const [range, setRange] = useState(7);
  const [countOld, setCountOld] = useState(false);
  const [preview, setPreview] = useState(null);
  const [choices, setChoices] = useState({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    setPreview(null);
    setChoices({});
    setError('');
    previewDailyImport(range, countOld)
      .then((next) => current && setPreview(next))
      .catch((err) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [range, countOld, version]);

  const days = preview?.days || [];
  const different = days.filter((d) => d.status !== 'unchanged');
  const chosen = different.filter((d) => choices[d.date]?.include !== false);
  const count = (status) => days.filter((d) => d.status === status).length;
  const card_ = (day) => (
    <Day key={day.date} day={day} choice={choices[day.date] || {}} onChange={(patch) => setChoices((all) => ({ ...all, [day.date]: { ...all[day.date], ...patch } }))} />
  );

  async function save() {
    setBusy('Saving…');
    setError('');
    try {
      await saveDailyImport(chosen.map((d) => payload(d, choices[d.date] || {})));
      setMessage(`Saved ${plural(chosen.length, 'day')}.`);
      await onSaved();
      setVersion((n) => n + 1);
    } catch (err) {
      setError(err.message);
    }
    setBusy('');
  }

  return (
    <>
      <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Import from daily notes</div>
          <button type="button" onClick={onClose} style={{ ...outline, marginLeft: 'auto', padding: '4px 12px', fontSize: 12 }}>Close</button>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {RANGES.map(([value, text]) => (
            <button key={value} type="button" onClick={() => { setRange(value); setMessage(''); }} aria-pressed={range === value} style={{ ...(range === value ? solid : outline), padding: '5px 12px', fontSize: 12 }}>
              {text}
            </button>
          ))}
        </div>
        <div style={dim}>Your notes aren’t changed. Nothing is saved until you check the preview, and blanks never erase what’s here.</div>
        <label style={{ ...dim, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <input type="checkbox" checked={countOld} onChange={(e) => { setCountOld(e.target.checked); setMessage(''); }} style={{ width: 16, height: 16, flexShrink: 0, accentColor: 'var(--accent)' }} />
          Count older calorie entries (one block, no “Yesterday’s Totals”) as final, so they’re in charts and averages
        </label>
        {message && <div role="status" style={{ fontSize: 13, color: 'var(--accent)' }}>{message}</div>}
        {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
        {!preview && !error && <div style={dim}>Reading your notes…</div>}
        {preview && (
          <div style={dim}>
            {plural(preview.notes, 'note')} read · {count('new')} new · {count('changed')} changed · {count('unchanged')} unchanged
          </div>
        )}
      </div>
      {different.map(card_)}
      {preview &&
        (different.length > 0 ? (
          <button type="button" disabled={!!busy || chosen.length === 0} onClick={save} style={{ ...solid, alignSelf: 'flex-start', opacity: chosen.length ? 1 : 0.5 }}>
            {busy || `Save ${plural(chosen.length, 'day')}`}
          </button>
        ) : (
          <div style={{ fontSize: 13 }}>Nothing new to save.</div>
        ))}
    </>
  );
}
