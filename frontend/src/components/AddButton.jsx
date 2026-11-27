import { useEffect, useState } from 'react';
import { listActivities } from '../api.js';
import { ActivityForm } from '../views/ActivityTab.jsx';
import { card, dim, outline, solid } from '../views/workoutStyles.js';

// The floating + on the Fitness page: today's numbers or an activity, from any
// tab.
export default function AddButton({ onDaily, onAdded }) {
  const [open, setOpen] = useState(false);
  const [activity, setActivity] = useState(false); // chosen from the two
  const [types, setTypes] = useState(null);
  const [error, setError] = useState('');
  const [added, setAdded] = useState('');

  async function showActivity() {
    setActivity(true);
    setError('');
    try {
      setTypes((await listActivities()).types);
    } catch {
      setError('Couldn’t load activities.');
    }
  }

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  useEffect(() => {
    if (!added) return undefined;
    const timer = setTimeout(() => setAdded(''), 4000);
    return () => clearTimeout(timer);
  }, [added]);

  const corner = { position: 'fixed', right: 'calc(20px + env(safe-area-inset-right))', bottom: 'calc(20px + env(safe-area-inset-bottom))' };
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setActivity(false);
          setAdded('');
          setOpen(true);
        }}
        aria-label="Add"
        title="Add"
        style={{ ...corner, zIndex: 30, width: 64, height: 64, borderRadius: '50%', border: 'none', background: 'var(--accent)', color: 'var(--accent-text)', boxShadow: '0 4px 20px var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}
      >
        <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
          <path d="M15 4v22M4 15h22" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
        </svg>
      </button>
      {added && (
        <div role="status" style={{ ...card, ...corner, right: 'calc(96px + env(safe-area-inset-right))', bottom: 'calc(30px + env(safe-area-inset-bottom))', zIndex: 30, borderColor: 'var(--accent-glow)', fontSize: 13, maxWidth: 'calc(100vw - 116px)' }}>
          Added {added}.
        </div>
      )}
      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14, zIndex: 50 }}
        >
          <div role="dialog" aria-modal="true" aria-label={activity ? 'Add activity' : 'Add'} onClick={(e) => e.stopPropagation()} style={{ width: 460, maxWidth: '100%', maxHeight: '100%', overflowY: 'auto' }}>
            {!activity ? (
              <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <button
                  type="button"
                  autoFocus
                  onClick={() => {
                    setOpen(false);
                    onDaily();
                  }}
                  style={{ ...solid, padding: 14, fontSize: 15 }}
                >
                  Daily numbers
                </button>
                <button type="button" onClick={showActivity} style={{ ...outline, padding: 14, fontSize: 15 }}>Activity</button>
                <button type="button" onClick={() => setOpen(false)} style={{ ...outline, border: 'none', color: 'var(--text-dim)' }}>Cancel</button>
              </div>
            ) : types ? (
              <ActivityForm
                types={types}
                onCancel={() => setOpen(false)}
                onSaved={(name) => {
                  setOpen(false);
                  setAdded(name);
                  onAdded();
                }}
              />
            ) : (
              <div style={{ ...card, display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={error ? { fontSize: 13, color: '#ff6b6b' } : dim}>{error || 'Loading…'}</span>
                <button type="button" onClick={() => setOpen(false)} style={{ ...outline, marginLeft: 'auto' }}>Close</button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
