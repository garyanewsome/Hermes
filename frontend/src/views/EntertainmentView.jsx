import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { deleteEntertainment, listEntertainment, saveEntertainment } from '../api.js';
import { card, dim, longDate, outline, solid } from './workoutStyles.js';

const STATUSES = [
  ['want', 'Want to watch'],
  ['watching', 'Watching'],
  ['waiting', 'Waiting'],
  ['paused', 'Paused'],
  ['done', 'Done'],
];
const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '9px 10px', fontSize: 16, width: '100%', minWidth: 0 };
const label = { ...dim, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 };
const small = { ...outline, padding: '5px 10px', fontSize: 12, flexShrink: 0 };
const heading = { fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent)', margin: '8px 0 0' };
const alertText = { fontSize: 13, color: '#ff6b6b' };

// What the API takes, from a stored entry or a form.
const body = (e) => ({
  title: e.title,
  kind: e.kind,
  group_name: e.group_name || null,
  status: e.status,
  season: e.season ? Number(e.season) : null,
  episode: e.episode ? Number(e.episode) : null,
  return_date: e.return_date || null,
  where_to_watch: e.where_to_watch || null,
  note: e.note || null,
});

// "S4 · after E3", or "Season 4" when nothing in it has been watched yet.
function placeText(entry) {
  if (entry.episode) return `${entry.season ? `S${entry.season} · ` : ''}watched E${entry.episode}`;
  return entry.season ? `Season ${entry.season}` : '';
}

function whenText(entry) {
  if (!entry.return_date) return 'no date yet';
  if (entry.days_until > 1) return `${longDate(entry.return_date)} · in ${entry.days_until} days`;
  if (entry.days_until === 1) return 'tomorrow';
  if (entry.days_until === 0) return 'out today';
  return `out since ${longDate(entry.return_date)}`;
}

function Overlay({ label: name, onClose, children }) {
  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14, zIndex: 50 }}>
      <div role="dialog" aria-modal="true" aria-label={name} style={{ width: 520, maxWidth: '100%', maxHeight: '100%', overflowY: 'auto', background: 'var(--bg)', borderRadius: 12 }}>
        {children}
      </div>
    </div>
  );
}

function EntryForm({ entry, groups, onSave, onDelete, onClose }) {
  const [form, setForm] = useState(() => ({
    title: '', kind: 'tv', group_name: '', status: 'want', season: '', episode: '', return_date: '', where_to_watch: '', note: '',
    ...Object.fromEntries(Object.entries(entry || {}).map(([k, v]) => [k, v ?? ''])),
  }));
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  const set = (key) => (event) => {
    const { value } = event.target;
    setForm((current) => ({ ...current, [key]: value }));
  };

  async function run(action) {
    setBusy(true);
    setError('');
    try {
      await action();
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const tv = form.kind === 'tv';
  return (
    <Overlay label={entry ? 'Edit entry' : 'Add to your list'} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(() => onSave(body(form)));
        }}
        style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}
      >
        <div style={{ fontSize: 14, fontWeight: 600 }}>{entry ? 'Edit' : 'Add to your list'}</div>
        <label style={label}>
          Title
          <input value={form.title} onChange={set('title')} maxLength={200} autoFocus={!entry} required style={field} />
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
          <label style={label}>
            Type
            <select value={form.kind} onChange={set('kind')} style={field}>
              <option value="tv">TV</option>
              <option value="movie">Movie</option>
            </select>
          </label>
          <label style={label}>
            Status
            <select value={form.status} onChange={set('status')} style={field}>
              {STATUSES.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </label>
          {tv && (
            <>
              <label style={label}>
                Season
                <input type="number" inputMode="numeric" min="1" max="200" value={form.season} onChange={set('season')} style={field} />
              </label>
              <label style={label}>
                Last episode watched
                <input type="number" inputMode="numeric" min="1" max="2000" value={form.episode} onChange={set('episode')} style={field} />
              </label>
            </>
          )}
          <label style={label}>
            Return or release date
            <input type="date" value={form.return_date} onChange={set('return_date')} style={field} />
          </label>
          <label style={label}>
            Group (optional)
            <input value={form.group_name} onChange={set('group_name')} maxLength={100} list="entertainment-groups" placeholder="Star Trek" style={field} />
            <datalist id="entertainment-groups">{groups.map((g) => <option key={g} value={g} />)}</datalist>
          </label>
        </div>
        <label style={label}>
          Where to watch (optional)
          <input value={form.where_to_watch} onChange={set('where_to_watch')} maxLength={100} style={field} />
        </label>
        <label style={label}>
          Note (optional)
          <textarea value={form.note} onChange={set('note')} maxLength={1000} rows={2} style={{ ...field, resize: 'vertical' }} />
        </label>
        {error && <div role="alert" style={alertText}>{error}</div>}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          <button type="submit" disabled={busy} style={solid}>{busy ? 'Saving…' : entry ? 'Save changes' : 'Add'}</button>
          <button type="button" onClick={onClose} style={outline}>Cancel</button>
          {entry && (
            <button type="button" disabled={busy} onClick={() => (confirming ? run(onDelete) : setConfirming(true))} style={{ ...outline, marginLeft: 'auto', borderColor: '#ff6b6b', color: '#ff6b6b' }}>
              {confirming ? 'Confirm delete' : 'Delete'}
            </button>
          )}
        </div>
      </form>
    </Overlay>
  );
}

function Row({ entry, detail, actions, onEdit }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0', borderTop: '1px solid var(--border)' }}>
      <button type="button" onClick={() => onEdit(entry)} style={{ flex: 1, minWidth: 0, background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left' }}>
        <div style={{ fontSize: 15, overflowWrap: 'anywhere' }}>{entry.title}</div>
        {detail && <div style={dim}>{detail}</div>}
      </button>
      {actions}
    </div>
  );
}

// Entries under their group name; ungrouped ones first.
function grouped(entries) {
  const groups = new Map([['', []]]);
  entries.forEach((e) => {
    const name = e.group_name || '';
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(e);
  });
  return [...groups].filter(([, list]) => list.length > 0);
}

function Folding({ title, count, children }) {
  const [open, setOpen] = useState(false);
  return (
    <section style={card}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} style={{ width: '100%', display: 'flex', background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left', fontSize: 14, fontWeight: 600 }}>
        {title}
        <span style={{ ...dim, marginLeft: 'auto' }}>{count} {open ? '▾' : '▸'}</span>
      </button>
      {open && <div style={{ marginTop: 8 }}>{children}</div>}
    </section>
  );
}

export default function EntertainmentView({ onOpenDrawer, active }) {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null); // an entry, 'new', or null
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!active) return;
    listEntertainment()
      .then((next) => (setData(next), setError('')))
      .catch(() => setError('Couldn’t load your list.'));
  }, [active]);

  // A one-tap change to an entry.
  async function quick(entry, patch) {
    setBusyId(entry.id);
    setError('');
    try {
      setData(await saveEntertainment(body({ ...entry, ...patch }), entry.id));
    } catch (err) {
      setError(err.message);
    }
    setBusyId(null);
  }

  const entries = data?.entries || [];
  const by = (status) => entries.filter((e) => e.status === status);
  const watching = by('watching');
  const waiting = [...by('waiting')].sort((a, b) => (a.return_date || '9999').localeCompare(b.return_date || '9999'));
  const want = by('want');
  const button = (entry, text, patch, name) => (
    <button type="button" disabled={busyId === entry.id} onClick={() => quick(entry, patch)} aria-label={`${name || text}: ${entry.title}`} style={small}>
      {text}
    </button>
  );
  const list = (items, detail, actions) =>
    grouped(items).map(([group, inGroup]) => (
      <div key={group || ' '}>
        {group && <div style={{ ...dim, fontWeight: 600, margin: '10px 0 2px' }}>{group}</div>}
        {inGroup.map((entry) => (
          <Row key={entry.id} entry={entry} detail={detail?.(entry)} actions={actions?.(entry)} onEdit={setEditing} />
        ))}
      </div>
    ));
  const groups = [...new Set(entries.map((e) => e.group_name).filter(Boolean))];

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Entertainment" onOpenDrawer={onOpenDrawer} />
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: isMobile ? 14 : 24 }}>
        <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 88 }}>
          {error && <div role="alert" style={alertText}>{error}</div>}
          {!data && !error && <div style={dim}>Loading…</div>}
          {data && entries.length === 0 && <div style={dim}>Nothing yet. Tap + to add something.</div>}

          {watching.length > 0 && (
            <section style={card}>
              <h2 style={{ ...heading, marginTop: 0, marginBottom: 4 }}>Continue</h2>
              {watching.map((entry) => (
                <Row
                  key={entry.id}
                  entry={entry}
                  detail={[placeText(entry), entry.where_to_watch].filter(Boolean).join(' · ')}
                  onEdit={setEditing}
                  actions={
                    <>
                      {entry.kind === 'tv' && button(entry, '+1 ep', { episode: (entry.episode || 0) + 1 }, 'Watched the next episode')}
                      {button(entry, 'Done', { status: 'done' })}
                    </>
                  }
                />
              ))}
            </section>
          )}

          {waiting.length > 0 && (
            <section style={card}>
              <h2 style={{ ...heading, marginTop: 0, marginBottom: 4 }}>Coming up</h2>
              {waiting.map((entry) => (
                <Row
                  key={entry.id}
                  entry={entry}
                  detail={[entry.season && `Season ${entry.season}`, whenText(entry)].filter(Boolean).join(' · ')}
                  onEdit={setEditing}
                  actions={entry.days_until !== null && entry.days_until <= 0 && button(entry, 'Start', { status: 'watching', return_date: null, episode: null })}
                />
              ))}
            </section>
          )}

          {want.length > 0 && (
            <section style={card}>
              <h2 style={{ ...heading, marginTop: 0 }}>Want to watch</h2>
              {[['tv', 'TV'], ['movie', 'Movies']].map(([kind, name]) => {
                const items = want.filter((e) => e.kind === kind);
                return (
                  items.length > 0 && (
                    <div key={kind}>
                      <div style={{ fontSize: 14, fontWeight: 600, marginTop: 10 }}>{name}</div>
                      {list(items, (e) => [placeText(e), e.where_to_watch].filter(Boolean).join(' · '), (e) => button(e, 'Start', { status: 'watching' }))}
                    </div>
                  )
                );
              })}
            </section>
          )}

          {by('paused').length > 0 && (
            <Folding title="Paused" count={by('paused').length}>
              {list(by('paused'), placeText, (e) => button(e, 'Resume', { status: 'watching' }))}
            </Folding>
          )}
          {by('done').length > 0 && (
            <Folding title="Done" count={by('done').length}>{list(by('done'))}</Folding>
          )}
          {data?.vault &&
            (data.vault.error ? (
              <div role="alert" style={alertText}>The vault copy wasn’t updated: {data.vault.error} Hermes will keep trying.</div>
            ) : (
              <div style={dim}>Copied to {data.vault.path} shortly after changes.</div>
            ))}
        </div>
      </div>

      <button
        type="button"
        onClick={() => setEditing('new')}
        aria-label="Add to your list"
        title="Add to your list"
        style={{ position: 'fixed', right: 'calc(20px + env(safe-area-inset-right))', bottom: 'calc(20px + env(safe-area-inset-bottom))', zIndex: 30, width: 64, height: 64, borderRadius: '50%', border: 'none', background: 'var(--accent)', color: 'var(--accent-text)', boxShadow: '0 4px 20px var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}
      >
        <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
          <path d="M15 4v22M4 15h22" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
        </svg>
      </button>

      {editing && (
        <EntryForm
          entry={editing === 'new' ? null : editing}
          groups={groups}
          onClose={() => setEditing(null)}
          onSave={async (values) => setData(await saveEntertainment(values, editing === 'new' ? undefined : editing.id))}
          onDelete={async () => setData(await deleteEntertainment(editing.id))}
        />
      )}
    </div>
  );
}
