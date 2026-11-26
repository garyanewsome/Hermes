import { useEffect, useState } from 'react';
import { exerciseHistory, linkExercise, unlinkExercise } from '../api.js';
import { card, dim, longDate, number, outline } from './workoutStyles.js';

const normal = (name) => name.toLowerCase().replace(/\s+/g, ' ').trim();
const columns = { display: 'grid', gridTemplateColumns: '1.2fr 0.6fr 1fr', columnGap: 10, fontSize: 14 };

// "230 lb (105 a side)": the per-side figure is what gets loaded on the machine.
function weightText(set) {
  if (set.weight === null) return set.bodyweight ? 'bodyweight' : '—';
  const total = `${number(set.weight)} ${set.unit || 'lb'}`;
  return set.per_side === null ? total : `${total} (${number(set.per_side)} a side)`;
}

const setText = (set) => `${set.weight === null ? '' : `${weightText(set)} × `}${set.reps}${set.weight === null ? ' reps' : ''}${set.myo_raw ? ` (${set.myo_raw})` : ''}`;

function PastSets({ name, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let current = true;
    exerciseHistory(name)
      .then((next) => current && (setData(next), setError('')))
      .catch((err) => current && setError(err.message));
    return () => {
      current = false;
    };
  }, [name, version]);

  if (error) return <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>;
  if (!data) return <div style={dim}>Loading…</div>;
  const [last] = data.days;
  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, background: 'var(--accent-wash)', border: '1px solid var(--accent-glow)', borderRadius: 8, padding: '10px 12px' }}>
        <div style={{ fontSize: 14 }}>
          <span style={dim}>Last, {longDate(last.date)}</span>
          {last.sets.map((set, i) => <div key={i}>{setText(set)}</div>)}
        </div>
        <div style={{ fontSize: 14 }}>
          <span style={dim}>Best, {longDate(data.best.date)}</span>
          <div>{setText(data.best)}</div>
        </div>
      </div>
      {data.days.map((day) => (
        <div key={day.date} role="table" aria-label={longDate(day.date)}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{[longDate(day.date), ...day.sessions].join(' · ')}</div>
          <div role="row" style={{ ...columns, ...dim, fontSize: 11, marginTop: 4, borderBottom: '1px solid var(--border)' }}>
            {['Weight', 'Reps', 'Myo'].map((heading) => <span key={heading} role="columnheader">{heading}</span>)}
          </div>
          {day.sets.map((set, i) => {
            const detail = [
              // Only worth saying which name when linked names are mixed in.
              normal(set.exercise) !== normal(name) && set.exercise,
              set.set_type,
              set.target && `target ${set.target}`,
              set.per_side !== null && `${number(set.per_side)} a side`,
              set.note,
            ]
              .filter(Boolean)
              .join(' · ');
            return (
              <div key={i} style={{ padding: '3px 0' }}>
                <div role="row" style={columns}>
                  <span role="cell">{set.weight === null ? weightText(set) : `${number(set.weight)}${set.unit === 'kg' ? ' kg' : ''}`}</span>
                  <span role="cell">{set.reps}</span>
                  <span role="cell">{set.myo_raw || (set.myo ? 'x' : '')}</span>
                </div>
                {detail && <div style={{ ...dim, fontSize: 11 }}>{detail}</div>}
              </div>
            );
          })}
        </div>
      ))}
    </>
  );
}

function Exercise({ entry, exercises, open, onToggle, onLinkChange }) {
  const linked = entry.variants.filter((v) => normal(v) !== normal(entry.name));
  return (
    <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <button type="button" onClick={onToggle} aria-expanded={open} style={{ background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left' }}>
        <div style={{ fontSize: 14, fontWeight: 600, overflowWrap: 'anywhere' }}>{entry.name}</div>
        <div style={dim}>
          {entry.sets} {entry.sets === 1 ? 'set' : 'sets'} · last {longDate(entry.last_done)}
        </div>
      </button>
      {open && (
        <>
          <PastSets name={entry.name} version={`${entry.sets}|${entry.last_done}|${entry.variants.join('|')}`} />
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
            {linked.map((variant) => (
              <button key={variant} type="button" onClick={() => onLinkChange(() => unlinkExercise(variant))} title="Unlink this name" style={{ ...outline, padding: '3px 8px', fontSize: 11, fontWeight: 400 }}>
                includes {variant} ×
              </button>
            ))}
            <select
              value=""
              onChange={(e) => e.target.value && onLinkChange(() => linkExercise(entry.name, e.target.value), e.target.value)}
              aria-label={`Count ${entry.name} as another exercise`}
              style={{ marginLeft: 'auto', maxWidth: 170, background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '5px 8px', fontSize: 12 }}
            >
              <option value="">Same as…</option>
              {exercises.filter((o) => o.name !== entry.name).map((o) => <option key={o.name} value={o.name}>{o.name}</option>)}
            </select>
          </div>
        </>
      )}
    </div>
  );
}

export default function ExercisesTab({ exercises, onChange }) {
  const [search, setSearch] = useState('');
  const [opened, setOpened] = useState(null); // name, '' for closed by hand, null for no choice yet
  const [error, setError] = useState('');
  if (exercises === null) return <div style={dim}>Loading…</div>;
  if (exercises.length === 0) return <div style={dim}>No exercises yet. Upload your spreadsheet on the Import tab.</div>;

  async function change(action, nowOpen) {
    setError('');
    try {
      onChange(await action());
      if (nowOpen) setOpened(nowOpen);
    } catch (err) {
      setError(err.message);
    }
  }

  // Every word typed must appear, in any order, in one of the exercise's names.
  const words = normal(search).split(' ').filter(Boolean);
  const shown = exercises.filter((e) => [e.name, ...e.variants].some((n) => words.every((word) => normal(n).includes(word))));
  // A search that narrows to one exercise opens it, saving a tap.
  const open = opened === null && words.length > 0 && shown.length === 1 ? shown[0].name : opened;

  return (
    <>
      <input
        type="search"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setOpened(null);
        }}
        placeholder={`Search ${exercises.length} ${exercises.length === 1 ? 'exercise' : 'exercises'}`}
        aria-label="Search exercises"
        style={{ background: 'var(--panel)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '10px 12px', fontSize: 16 }}
      />
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      {shown.length === 0 && <div style={dim}>Nothing logged under that name.</div>}
      {shown.map((entry) => (
        <Exercise
          key={entry.name}
          entry={entry}
          exercises={exercises}
          open={open === entry.name}
          onToggle={() => setOpened(open === entry.name ? '' : entry.name)}
          onLinkChange={change}
        />
      ))}
    </>
  );
}
