import { useEffect, useState } from 'react';
import { putHabitAmount, setHabitDay } from '../api.js';
import { card, dim, longDate, number, outline, solid } from '../views/workoutStyles.js';

// Enters one day's number for a habit that counts something. `day` is what the
// date holds now: { logged, amount }.
export default function AmountDialog({ habit, date, today, day, onClose, onSaved }) {
  const adding = habit.add_up && day.amount !== null;
  const [value, setValue] = useState(!habit.add_up && day.amount !== null ? String(day.amount) : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const parsed = Number(value.replace(',', '.'));
  const valid = value.trim() !== '' && parsed > 0;

  useEffect(() => {
    const onKey = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function run(action) {
    setBusy(true);
    setError('');
    try {
      await action();
      await onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }
  const save = (mode) => run(() => putHabitAmount(habit.id, date, parsed, mode));

  return (
    <div
      onClick={(event) => {
        event.stopPropagation();
        onClose();
      }}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14, zIndex: 70 }}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label={`${habit.name} amount`}
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) save('add');
        }}
        style={{ ...card, background: 'var(--bg)', borderColor: 'var(--accent)', width: 340, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 10, color: 'var(--text)', textAlign: 'left' }}
      >
        <div style={{ fontSize: 15, fontWeight: 600, overflowWrap: 'anywhere' }}>{habit.name}</div>
        <div style={dim}>
          {date === today ? 'Today' : longDate(date)}
          {day.amount !== null && ` · ${number(day.amount)} ${habit.unit} so far`}
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
          <input
            autoFocus
            inputMode="decimal"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            aria-label={`${habit.unit} ${adding ? 'to add' : ''}`}
            style={{ flex: 1, minWidth: 0, background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '9px 10px', fontSize: 18 }}
          />
          {habit.unit}
        </label>
        {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <button type="submit" disabled={busy || !valid} style={{ ...solid, opacity: valid ? 1 : 0.5 }}>{adding ? 'Add' : 'Save'}</button>
          {adding && (
            <button type="button" disabled={busy || !valid} onClick={() => save('set')} style={{ ...outline, opacity: valid ? 1 : 0.5 }}>Set as total</button>
          )}
          <button type="button" onClick={onClose} style={outline}>Cancel</button>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => run(() => setHabitDay(habit.id, date, !day.logged))}
          style={{ alignSelf: 'flex-start', background: 'transparent', border: 'none', padding: 0, color: 'var(--text-dim)', fontSize: 13, textDecoration: 'underline' }}
        >
          {day.logged ? 'Remove this day' : 'Done, without a number'}
        </button>
      </form>
    </div>
  );
}
