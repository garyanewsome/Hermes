import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import AddButton from '../components/AddButton.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { importWorkoutSheet, listExercises, listWorkouts, previewWorkoutSheet, setWarningDismissed } from '../api.js';
import { minutesText, paceText } from '../lib/activities.js';
import ActivityTab from './ActivityTab.jsx';
import ChartsTab from './ChartsTab.jsx';
import DailyTab from './DailyTab.jsx';
import ExercisesTab from './ExercisesTab.jsx';
import { card, dim, longDate, number, outline, solid } from './workoutStyles.js';

const TABS = [
  ['daily', 'Daily'],
  ['history', 'History'],
  ['charts', 'Charts'],
  ['exercises', 'Search'],
  ['import', 'Import'],
];
const HISTORY_VIEWS = [
  ['all', 'Everything'],
  ['activities', 'Activities'],
];

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;

function weightText(set) {
  if (set.weight === null) return set.bodyweight ? 'bodyweight' : '—';
  return `${number(set.weight)}${set.unit === 'kg' ? ' kg' : ''}`;
}

const columns = { display: 'grid', gridTemplateColumns: '1.2fr 0.6fr 1fr 0.9fr', columnGap: 10, fontSize: 13 };

// Sets in recorded order, grouped under their exercise.
function SetList({ sets }) {
  const groups = [];
  sets.forEach((set) => {
    const last = groups[groups.length - 1];
    if (last && last.name === set.exercise) last.sets.push(set);
    else groups.push({ name: set.exercise, sets: [set] });
  });
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 12, maxWidth: 480 }}>
      {groups.map((group, index) => (
        <div key={index} role="table" aria-label={group.name}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {group.name}
            {group.sets[0].superset && <span style={{ ...dim, marginLeft: 8 }}>superset</span>}
          </div>
          {group.sets[0].note && <div style={dim}>{group.sets[0].note}</div>}
          <div role="row" style={{ ...columns, ...dim, fontSize: 11, marginTop: 4, borderBottom: '1px solid var(--border)' }}>
            {['Weight', 'Reps', 'Myo', 'Volume'].map((heading) => <span key={heading} role="columnheader">{heading}</span>)}
          </div>
          {group.sets.map((set, i) => {
            const side = set.per_side === null || set.per_side === undefined ? null : `${number(set.per_side)} a side`;
            const detail = [set.set_type, set.target && `target ${set.target}`, side].filter(Boolean).join(' · ');
            return (
              <div key={i} style={{ padding: '3px 0' }}>
                <div role="row" style={columns}>
                  <span role="cell">{weightText(set)}</span>
                  <span role="cell">{set.reps}</span>
                  {/* The x fallback covers sets saved before the text was kept. */}
                  <span role="cell">{set.myo_raw || (set.myo ? 'x' : '')}</span>
                  <span role="cell">{set.weight === null ? '—' : number(set.weight * set.reps)}</span>
                </div>
                {detail && <div style={{ ...dim, fontSize: 11 }}>{detail}</div>}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function Workout({ title, summary, sets, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={card}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        style={{ width: '100%', display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 12, background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left' }}
      >
        <span style={{ fontSize: 14, fontWeight: 600 }}>{title}</span>
        <span style={{ ...dim, marginLeft: 'auto', color: 'var(--accent)' }}>{summary}</span>
      </button>
      {children}
      {open && <SetList sets={sets} />}
    </div>
  );
}

function History({ days }) {
  if (days === null) return <div style={dim}>Loading…</div>;
  if (days.length === 0) return <div style={dim}>No workouts or activities yet. Upload your spreadsheet on the Import tab, or tap + to add an activity.</div>;
  return days.map((day) => {
    const sessions = [...new Set(day.sets.map((s) => s.session).filter(Boolean))];
    const volume = Object.entries(day.volume).map(([unit, total]) => `${number(total)} ${unit}`);
    const parts = [day.sets.length > 0 && plural(day.sets.length, 'set'), ...volume, day.activities.length > 0 && (day.activities.length === 1 ? '1 activity' : `${day.activities.length} activities`)];
    return (
      <Workout key={day.date} title={[longDate(day.date), ...sessions].join(' · ')} summary={parts.filter(Boolean).join(' · ')} sets={day.sets}>
        {day.activities.map((entry) => (
          <div key={entry.id} style={{ ...dim, marginTop: 6 }}>
            {[
              entry.activity,
              entry.distance !== null && `${number(entry.distance)} ${entry.distance_unit}`,
              entry.duration_seconds && minutesText(entry.duration_seconds),
              paceText(entry),
            ]
              .filter(Boolean)
              .join(' · ')}
          </div>
        ))}
      </Workout>
    );
  });
}

// Sheet warnings worth checking, with the hidden ones folded away underneath.
function Warnings({ shown, hidden, onChange }) {
  const [error, setError] = useState('');
  const small = { ...outline, padding: '3px 9px', fontSize: 11, fontWeight: 400, flexShrink: 0 };
  const row = { display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 8, fontSize: 13 };

  async function set(text, dismissed) {
    setError('');
    try {
      await setWarningDismissed(text, dismissed);
      // A restored warning is shown again, whatever hid it before.
      onChange(
        dismissed ? shown.filter((t) => t !== text) : [...shown, text],
        dismissed ? [...hidden, { text, reason: 'dismissed' }] : hidden.filter((h) => h.text !== text)
      );
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      {shown.length > 0 && (
        <div style={{ ...card, borderColor: '#ffb020' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#ffb020' }}>Worth checking ({shown.length})</div>
          {shown.map((text) => (
            <div key={text} style={row}>
              <span style={{ minWidth: 0, flex: 1, overflowWrap: 'anywhere' }}>{text}</span>
              <button type="button" onClick={() => set(text, true)} aria-label={`Dismiss: ${text}`} style={small}>Dismiss</button>
            </div>
          ))}
        </div>
      )}
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      {hidden.length > 0 && (
        <details>
          <summary style={{ ...dim, cursor: 'pointer', padding: '4px 0' }}>Show {plural(hidden.length, 'hidden warning')}</summary>
          <div style={card}>
            {hidden.map((item) => (
              <div key={item.text} style={row}>
                <span style={{ minWidth: 0, flex: 1, overflowWrap: 'anywhere' }}>
                  {item.text}
                  <span style={{ ...dim, display: 'block' }}>{item.reason === 'dismissed' ? 'Dismissed' : 'In a saved, unchanged workout'}</span>
                </span>
                {item.reason === 'dismissed' && (
                  <button type="button" onClick={() => set(item.text, false)} aria-label={`Restore: ${item.text}`} style={small}>Restore</button>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </>
  );
}

function Import({ onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const input = useRef(null);

  async function choose(event) {
    const chosen = event.target.files[0];
    // Cleared so picking the same file again (after fixing the sheet) fires.
    event.target.value = '';
    if (!chosen) return;
    setFile(chosen);
    setPreview(null);
    setError('');
    setMessage('');
    setBusy('Reading…');
    try {
      setPreview(await previewWorkoutSheet(chosen));
    } catch (err) {
      // Browsers refuse to re-read a file that changed on disk after picking.
      setError(err.message);
    }
    setBusy('');
  }

  async function save() {
    setBusy('Saving…');
    setError('');
    try {
      const result = await importWorkoutSheet(file);
      const saved = result.workouts.filter((w) => w.status !== 'unchanged').length;
      const same = result.workouts.length - saved;
      setMessage(`Saved ${plural(saved, 'workout')}.${same ? ` ${same} unchanged.` : ''}`);
      setPreview(null);
      onImported();
    } catch (err) {
      setError(err.message);
    }
    setBusy('');
  }

  const blocked = preview && preview.errors.length > 0;
  const withStatus = (status) => preview?.workouts.filter((w) => w.status === status) || [];
  const [added, changed, unchanged] = [withStatus('new'), withStatus('changed'), withStatus('unchanged')];
  const writing = [...added, ...changed].sort((a, b) => b.date.localeCompare(a.date));
  const previewCard = (w) => (
    <Workout
      key={`${w.date}-${w.session}`}
      title={`${longDate(w.date)} · ${w.session}`}
      summary={`${plural(w.set_count, 'set')} · ${number(w.volume)} lb (${number(w.entered_volume)} as entered)`}
      sets={w.sets}
    >
      {w.status !== 'unchanged' && (
        <div style={{ fontSize: 12, color: 'var(--accent)', marginTop: 6 }}>
          {w.status === 'new'
            ? 'New'
            : `Changed · replaces ${plural(w.replaces.sets + w.replaces.pasted_sets, 'saved set')}`}
          {w.changes.length > 0 && <span style={dim}> · {w.changes.join(', ')}</span>}
        </div>
      )}
    </Workout>
  );
  return (
    <>
      <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-start' }}>
        <div style={dim}>In Google Sheets: File → Download → Microsoft Excel (.xlsx). Nothing is saved until you check the preview.</div>
        <input ref={input} type="file" accept=".xlsx" onChange={choose} style={{ display: 'none' }} />
        <button type="button" onClick={() => input.current.click()} disabled={!!busy} style={outline}>
          {busy || 'Choose spreadsheet'}
        </button>
        {file && <div style={dim}>{file.name}</div>}
        {message && <div style={{ fontSize: 13, color: 'var(--accent)' }}>{message}</div>}
        {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b', whiteSpace: 'pre-line' }}>{error}</div>}
      </div>

      {preview && (
        <>
          {blocked && (
            <div style={{ ...card, borderColor: '#ff6b6b' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#ff6b6b' }}>Fix these in the sheet, then upload it again</div>
              {preview.errors.map((text, i) => <div key={i} style={{ fontSize: 13, marginTop: 6 }}>{text}</div>)}
            </div>
          )}
          <Warnings
            shown={preview.warnings}
            hidden={preview.hidden_warnings}
            onChange={(warnings, hidden_warnings) => setPreview((current) => ({ ...current, warnings, hidden_warnings }))}
          />
          {preview.new_exercises.length > 0 && (
            <div style={card}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>New exercise names ({preview.new_exercises.length})</div>
              <div style={{ ...dim, marginTop: 6 }}>{preview.new_exercises.join(', ')}</div>
              <div style={{ ...dim, marginTop: 6 }}>If one is a lift you already track under another name, link it on the Search tab after saving.</div>
            </div>
          )}
          {preview.skipped_tabs.length > 0 && <div style={dim}>Tabs not read: {preview.skipped_tabs.join(', ')}</div>}
          {preview.workouts.length > 0 && (
            <div style={dim}>
              {[`${added.length} new`, `${changed.length} changed`, `${unchanged.length} unchanged`].join(' · ')}
            </div>
          )}
          {writing.map(previewCard)}
          {unchanged.length > 0 && (
            <details>
              <summary style={{ ...dim, cursor: 'pointer', padding: '4px 0' }}>Show {plural(unchanged.length, 'unchanged workout')}</summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>{unchanged.map(previewCard)}</div>
            </details>
          )}
          {!blocked && (writing.length > 0 ? (
            <button type="button" onClick={save} disabled={!!busy} style={{ ...solid, alignSelf: 'flex-start' }}>
              {busy || `Save ${plural(writing.length, 'workout')}`}
            </button>
          ) : (
            preview.workouts.length > 0 && <div style={{ fontSize: 13 }}>Nothing new to save. Naradi already matches this file.</div>
          ))}
        </>
      )}
    </>
  );
}

export default function WorkoutsView({ onOpenDrawer, active }) {
  const [tab, setTab] = useState('daily');
  const [historyView, setHistoryView] = useState('all');
  const [focus, setFocus] = useState(0);
  const [days, setDays] = useState(null);
  const [exercises, setExercises] = useState(null);
  const [error, setError] = useState('');
  // Bumped after the + button saves, so the tabs showing activities reload.
  const [version, setVersion] = useState(0);
  const isMobile = useIsMobile();

  async function refresh() {
    try {
      const [nextDays, nextExercises] = await Promise.all([listWorkouts(), listExercises()]);
      setDays(nextDays);
      setExercises(nextExercises);
      setError('');
    } catch {
      setError('Couldn’t load workouts.');
    }
  }

  useEffect(() => {
    if (active) refresh();
  }, [active]);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Fitness" onOpenDrawer={onOpenDrawer}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {TABS.map(([key, label]) => (
            <button key={key} type="button" onClick={() => setTab(key)} aria-pressed={tab === key} style={{ ...(tab === key ? solid : outline), ...(isMobile && { padding: '6px 9px', fontSize: 12 }) }}>
              {label}
            </button>
          ))}
        </div>
      </TopBar>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: isMobile ? 14 : 24 }}>
        {/* The bottom padding lets the last card scroll clear of the + button. */}
        <div style={{ maxWidth: 760, display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 88 }}>
          {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
          {/* Stays mounted so half-typed numbers aren't lost. */}
          <div style={{ display: tab === 'daily' ? 'contents' : 'none' }}>
            <DailyTab active={active && tab === 'daily'} focus={focus} />
          </div>
          {tab === 'history' && (
            <div style={{ display: 'flex', gap: 6 }}>
              {HISTORY_VIEWS.map(([key, text]) => (
                <button key={key} type="button" onClick={() => setHistoryView(key)} aria-pressed={historyView === key} style={{ ...(historyView === key ? solid : outline), padding: '5px 12px', fontSize: 12 }}>
                  {text}
                </button>
              ))}
            </div>
          )}
          {tab === 'history' && historyView === 'all' && <History days={days} />}
          {tab === 'charts' && <ChartsTab active={active} version={version} />}
          {/* Stays mounted so a half-typed entry isn't lost. */}
          <div style={{ display: tab === 'history' && historyView === 'activities' ? 'contents' : 'none' }}>
            <ActivityTab active={active && tab === 'history' && historyView === 'activities'} version={version} onChange={refresh} />
          </div>
          {/* Stays mounted so a preview survives a look at another tab. */}
          <div style={{ display: tab === 'import' ? 'contents' : 'none' }}>
            <Import onImported={refresh} />
          </div>
          {/* Stays mounted so the search is still there after a look elsewhere. */}
          <div style={{ display: tab === 'exercises' ? 'contents' : 'none' }}>
            <ExercisesTab exercises={exercises} onChange={setExercises} />
          </div>
        </div>
      </div>
      <AddButton
        onDaily={() => {
          setTab('daily');
          setFocus((n) => n + 1);
        }}
        onAdded={() => {
          setVersion((n) => n + 1);
          refresh();
        }}
      />
    </div>
  );
}
