import { useEffect, useState } from 'react';
import { deleteActivity, listActivities, saveActivity } from '../api.js';
import { parseISODate, todayISO } from '../lib/dates.js';
import { groupBy, minutesText, paceText, totalsText, weekStart } from '../lib/activities.js';
import { card, dim, longDate, number, outline, solid } from './workoutStyles.js';

const NEW = '__new__';
const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '8px 10px', fontSize: 14, width: '100%', minWidth: 0 };
const label = { ...dim, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 };
const shortDate = (iso) => parseISODate(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

const blank = (activity) => ({ activity, custom: '', date: todayISO(), distance: '', unit: 'mi', minutes: '' });

function ActivityForm({ types, entry, onSaved, onCancel }) {
  const [form, setForm] = useState(() =>
    entry
      ? { activity: entry.activity, custom: '', date: entry.date, distance: entry.distance ?? '', unit: entry.distance_unit || 'mi', minutes: entry.duration_seconds ? entry.duration_seconds / 60 : '' }
      : blank(types[0])
  );
  // The default date moves with the calendar unless one was picked.
  const [dated, setDated] = useState(!!entry);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const set = (key) => (event) => {
    const { value } = event.target;
    setForm((current) => ({ ...current, [key]: value }));
    setMessage('');
  };

  async function submit(event) {
    event.preventDefault();
    const activity = (form.activity === NEW ? form.custom : form.activity).trim();
    if (!activity) return setError('Name the activity');
    setBusy(true);
    setError('');
    try {
      await saveActivity(
        {
          activity,
          date: dated ? form.date : todayISO(),
          minutes: Number(form.minutes),
          distance: form.distance === '' ? null : Number(form.distance),
          distance_unit: form.unit,
        },
        entry?.id
      );
      const types = await onSaved();
      if (!entry) {
        // Keep the activity and date for the next one; select the stored
        // spelling of a newly typed name.
        const stored = types?.find((t) => t.toLowerCase() === activity.replace(/\s+/g, ' ').toLowerCase()) || form.activity;
        setForm((current) => ({ ...current, activity: stored, custom: '', distance: '', minutes: '' }));
        setMessage(`Added ${activity}.`);
      }
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  }

  return (
    <form onSubmit={submit} style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 14, fontWeight: 600 }}>{entry ? 'Edit activity' : 'Add activity'}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
        <label style={label}>
          Activity
          <select value={form.activity} onChange={set('activity')} style={field}>
            {types.map((type) => <option key={type} value={type}>{type}</option>)}
            <option value={NEW}>+ New activity…</option>
          </select>
        </label>
        {form.activity === NEW && (
          <label style={label}>
            Name
            <input value={form.custom} onChange={set('custom')} maxLength={80} placeholder="Deep Squat Sit" autoFocus required style={field} />
          </label>
        )}
        <label style={label}>
          Date
          <input type="date" value={dated ? form.date : todayISO()} onChange={(e) => { setDated(true); set('date')(e); }} required style={field} />
        </label>
        <label style={label}>
          Distance (optional)
          <span style={{ display: 'flex', gap: 6 }}>
            <input type="number" inputMode="decimal" min="0.01" max="1000" step="any" value={form.distance} onChange={set('distance')} style={field} />
            <select value={form.unit} onChange={set('unit')} aria-label="Distance unit" style={{ ...field, width: 70, flexShrink: 0 }}>
              <option value="mi">mi</option>
              <option value="km">km</option>
            </select>
          </span>
        </label>
        <label style={label}>
          Time (minutes)
          <input type="number" inputMode="decimal" min="0.02" max="1440" step="any" value={form.minutes} onChange={set('minutes')} required style={field} />
        </label>
      </div>
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b', whiteSpace: 'pre-line' }}>{error}</div>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="submit" disabled={busy} style={solid}>{busy ? 'Saving…' : entry ? 'Save changes' : 'Add'}</button>
        {entry && <button type="button" onClick={onCancel} style={outline}>Cancel</button>}
        {message && <span role="status" style={{ fontSize: 13, color: 'var(--accent)' }}>{message}</span>}
      </div>
    </form>
  );
}

function Entry({ entry, showDate, onEdit, onDelete }) {
  const [confirming, setConfirming] = useState(false);
  const small = { ...outline, padding: '3px 9px', fontSize: 11, fontWeight: 400 };
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: '1px solid var(--border)' }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13 }}>
          {[showDate && shortDate(entry.date), entry.activity].filter(Boolean).join(' · ')}
        </div>
        <div style={dim}>
          {[entry.distance !== null && `${number(entry.distance)} ${entry.distance_unit}`, entry.duration_seconds && minutesText(entry.duration_seconds), paceText(entry)]
            .filter(Boolean)
            .join(' · ')}
        </div>
      </div>
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
        {confirming ? (
          <>
            <button type="button" onClick={() => onDelete(entry)} style={{ ...small, borderColor: '#ff6b6b', color: '#ff6b6b' }}>Confirm delete</button>
            <button type="button" onClick={() => setConfirming(false)} style={small}>Keep</button>
          </>
        ) : (
          <>
            <button type="button" onClick={() => onEdit(entry)} style={small}>Edit</button>
            <button type="button" onClick={() => setConfirming(true)} style={small}>Delete</button>
          </>
        )}
      </div>
    </div>
  );
}

// A total that opens to show what's in it.
function Group({ title, entries, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={card}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        style={{ width: '100%', display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 12, background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left' }}
      >
        <span style={{ fontSize: 14, fontWeight: 600, overflowWrap: 'anywhere' }}>{title}</span>
        <span style={{ ...dim, marginLeft: 'auto', color: 'var(--accent)' }}>{totalsText(entries)}</span>
      </button>
      {open && <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>{children}</div>}
    </div>
  );
}

const VIEWS = [
  ['day', 'By day'],
  ['week', 'By week'],
  ['type', 'By activity'],
];

export default function ActivityTab({ active, onChange }) {
  const [data, setData] = useState(null);
  const [view, setView] = useState('day');
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');

  async function refresh() {
    try {
      const next = await listActivities();
      setData(next);
      setError('');
      return next.types;
    } catch {
      setError('Couldn’t load activities.');
      return null;
    }
  }

  useEffect(() => {
    if (active) refresh();
  }, [active]);

  async function changed() {
    const types = await refresh();
    onChange();
    return types;
  }

  async function remove(entry) {
    try {
      await deleteActivity(entry.id);
      if (editing?.id === entry.id) setEditing(null);
    } catch (err) {
      setError(err.message);
    }
    changed();
  }

  if (data === null) return <div style={dim}>{error || 'Loading…'}</div>;

  const list = (entries, showDate) =>
    entries.map((entry) =>
      editing?.id === entry.id ? (
        <ActivityForm key={entry.id} types={data.types} entry={entry} onCancel={() => setEditing(null)} onSaved={async () => { setEditing(null); await changed(); }} />
      ) : (
        <Entry key={entry.id} entry={entry} showDate={showDate} onEdit={setEditing} onDelete={remove} />
      )
    );
  const days = (entries) =>
    groupBy(entries, (e) => e.date).map(([date, items]) => (
      <Group key={date} title={longDate(date)} entries={items}>{list(items)}</Group>
    ));

  return (
    <>
      <ActivityForm types={data.types} onSaved={changed} />
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      {data.entries.length > 0 && (
        <div style={{ display: 'flex', gap: 6 }}>
          {VIEWS.map(([key, text]) => (
            <button key={key} type="button" onClick={() => setView(key)} aria-pressed={view === key} style={{ ...(view === key ? solid : outline), padding: '5px 12px', fontSize: 12 }}>
              {text}
            </button>
          ))}
        </div>
      )}
      {view === 'day' && days(data.entries)}
      {view === 'week' &&
        groupBy(data.entries, (e) => weekStart(e.date)).map(([start, items]) => (
          <Group key={start} title={`Week of ${shortDate(start)}`} entries={items}>{days(items)}</Group>
        ))}
      {view === 'type' &&
        groupBy(data.entries, (e) => e.activity).map(([name, items]) => (
          <Group key={name} title={name} entries={items}>{list(items, true)}</Group>
        ))}
    </>
  );
}
