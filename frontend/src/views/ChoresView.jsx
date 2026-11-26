import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { choreHistory, deleteChore, listChores, logChore, saveChore, unlogChore } from '../api.js';
import { card, dim, longDate, outline, solid } from './workoutStyles.js';

const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '9px 10px', fontSize: 16, width: '100%', minWidth: 0 };
const label = { ...dim, display: 'flex', flexDirection: 'column', gap: 4 };
const small = { ...outline, padding: '4px 10px', fontSize: 12, fontWeight: 400 };
const danger = { ...small, borderColor: '#ff6b6b', color: '#ff6b6b' };

function agoText(chore) {
  if (chore.days_ago === null) return 'never';
  if (chore.days_ago <= 0) return 'done today';
  if (chore.days_ago === 1) return 'yesterday';
  return `${chore.days_ago} days ago`;
}

// Adds a chore, or edits `chore`.
function ChoreForm({ chore, onSave, onCancel }) {
  const [name, setName] = useState(chore?.name || '');
  const [every, setEvery] = useState(chore?.every_days ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onSave({ name, every_days: every === '' ? null : Number(every) });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 14, fontWeight: 600 }}>{chore ? 'Edit chore' : 'Add chore'}</div>
      <label style={label}>
        Chore
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="Dust ceiling fans" autoFocus required style={field} />
      </label>
      <label style={label}>
        About every … days (optional)
        <input type="number" inputMode="numeric" min="1" max="3650" step="1" value={every} onChange={(e) => setEvery(e.target.value)} style={field} />
      </label>
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      <div style={{ display: 'flex', gap: 10 }}>
        <button type="submit" disabled={busy} style={solid}>{busy ? 'Saving…' : chore ? 'Save changes' : 'Add'}</button>
        <button type="button" onClick={onCancel} style={outline}>Cancel</button>
      </div>
    </form>
  );
}

function History({ chore, today, change, onEdit }) {
  const [dates, setDates] = useState(null);
  const [date, setDate] = useState('');
  const [failed, setFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let current = true;
    choreHistory(chore.id)
      .then((next) => current && (setDates(next), setFailed(false)))
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [chore.id, chore.times, chore.last_done]);

  async function addDate(event) {
    event.preventDefault();
    if (await change(() => logChore(chore.id, date))) setDate('');
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--border)', paddingTop: 10 }}>
      <form onSubmit={addDate} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 8 }}>
        <label style={{ ...label, flex: '1 1 150px' }}>
          Did it on another day
          <input type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} required style={field} />
        </label>
        <button type="submit" style={{ ...outline, height: 40 }}>Add date</button>
      </form>
      {failed && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>Couldn’t load the history.</div>}
      {!failed && dates === null && <div style={dim}>Loading…</div>}
      {dates?.length === 0 && <div style={dim}>No history yet.</div>}
      {dates?.length > 0 && (
        <div style={{ maxHeight: 220, overflowY: 'auto' }}>
          {dates.map((done) => (
            <div key={done} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
              {longDate(done)}
              <button type="button" onClick={() => change(() => unlogChore(chore.id, done))} aria-label={`Remove ${longDate(done)}`} style={{ ...small, marginLeft: 'auto' }}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button type="button" onClick={onEdit} style={small}>Edit chore</button>
        {confirming ? (
          <>
            <button type="button" onClick={() => change(() => deleteChore(chore.id))} style={danger}>Delete it and its history</button>
            <button type="button" onClick={() => setConfirming(false)} style={small}>Keep</button>
          </>
        ) : (
          <button type="button" onClick={() => setConfirming(true)} style={small}>Delete chore</button>
        )}
      </div>
    </div>
  );
}

function Chore({ chore, today, open, onToggle, change }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const doneToday = chore.last_done === today;

  if (editing) {
    return (
      <ChoreForm
        chore={chore}
        onCancel={() => setEditing(false)}
        onSave={async (body) => {
          // Errors stay on the form.
          await change(() => saveChore(body, chore.id), true);
          setEditing(false);
        }}
      />
    );
  }

  async function toggleToday() {
    setBusy(true);
    await change(() => (doneToday ? unlogChore(chore.id, today) : logChore(chore.id)));
    setBusy(false);
  }

  return (
    <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10, ...(chore.due && { borderColor: '#ffb020' }) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="button" onClick={onToggle} aria-expanded={open} style={{ flex: 1, minWidth: 0, background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left' }}>
          <div style={{ fontSize: 15, fontWeight: 600, overflowWrap: 'anywhere' }}>{chore.name}</div>
          <div style={dim}>
            {[agoText(chore), chore.every_days && `every ${chore.every_days} days`].filter(Boolean).join(' · ')}
            {/* Said in words, not by the border color alone. */}
            {chore.due && <span style={{ color: '#ffb020', marginLeft: 6, fontWeight: 600 }}>⚠ due</span>}
          </div>
        </button>
        <button type="button" onClick={toggleToday} disabled={busy} style={{ ...(doneToday ? outline : solid), flexShrink: 0, minHeight: 40 }}>
          {doneToday ? 'Undo' : 'Did it'}
        </button>
      </div>
      {open && <History chore={chore} today={today} change={change} onEdit={() => setEditing(true)} />}
    </div>
  );
}

export default function ChoresView({ onOpenDrawer, active }) {
  const [data, setData] = useState(null);
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState(null);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!active) return;
    listChores()
      .then((next) => (setData(next), setError('')))
      .catch(() => setError('Couldn’t load chores.'));
  }, [active]);

  // Runs a change and shows the list it returns. A form passes `raise` to
  // show the problem itself.
  async function change(action, raise) {
    setError('');
    try {
      setData(await action());
      return true;
    } catch (err) {
      if (raise) throw err;
      setError(err.message);
      return false;
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Chores" subtitle="longest ago first" onOpenDrawer={onOpenDrawer} />
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: isMobile ? 14 : 24 }}>
        <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 10, paddingBottom: 88 }}>
          {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
          {!data && !error && <div style={dim}>Loading…</div>}
          {data?.chores.length === 0 && !adding && <div style={dim}>No chores yet. Tap + to add one.</div>}
          {adding && (
            <ChoreForm
              onCancel={() => setAdding(false)}
              onSave={async (body) => {
                await change(() => saveChore(body), true);
                setAdding(false);
              }}
            />
          )}
          {data?.chores.map((chore) => (
            <Chore
              key={chore.id}
              chore={chore}
              today={data.today}
              open={openId === chore.id}
              onToggle={() => setOpenId(openId === chore.id ? null : chore.id)}
              change={change}
            />
          ))}
        </div>
      </div>
      {!adding && (
        <button
          type="button"
          onClick={(event) => {
            setAdding(true);
            // The form opens at the top of the list.
            event.currentTarget.parentElement.children[1].scrollTop = 0;
          }}
          aria-label="Add chore"
          title="Add chore"
          style={{ position: 'fixed', right: 'calc(20px + env(safe-area-inset-right))', bottom: 'calc(20px + env(safe-area-inset-bottom))', zIndex: 30, width: 64, height: 64, borderRadius: '50%', border: 'none', background: 'var(--accent)', color: 'var(--accent-text)', boxShadow: '0 4px 20px var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}
        >
          <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
            <path d="M15 4v22M4 15h22" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </div>
  );
}
