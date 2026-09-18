import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { deleteHabit, listHabits, logHabit, setHabitDay } from '../api.js';

function Dot({ day, onToggle }) {
  return (
    <button
      onClick={() => onToggle(day.date, !day.logged)}
      title={`${day.date}${day.logged ? ' — click to undo' : ' — click to log'}`}
      style={{
        width: 16,
        height: 16,
        padding: 0,
        borderRadius: '50%',
        background: day.logged ? 'var(--accent)' : 'transparent',
        border: day.logged ? 'none' : '1px solid var(--border-strong)',
        boxShadow: day.logged ? '0 0 6px var(--accent-glow)' : 'none',
        cursor: 'pointer',
      }}
    />
  );
}

function ConfirmDeleteHabit({ habit, onCancel, onConfirm }) {
  return (
    <div
      onClick={onCancel}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm();
        }}
        style={{
          width: 340,
          maxWidth: '90vw',
          background: 'var(--bg)',
          border: '1px solid var(--accent)',
          boxShadow: '0 0 20px var(--accent-glow)',
          borderRadius: 12,
          padding: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        <div style={{ fontSize: 14, color: 'var(--text)' }}>
          Delete "{habit.name}"? Its whole log history goes with it — this can't be undone.
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={onCancel} style={{ background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '7px 14px', fontSize: 13 }}>
            Cancel
          </button>
          <button type="submit" autoFocus style={{ background: '#ff6b6b', border: 'none', color: '#2b0808', borderRadius: 8, padding: '7px 14px', fontSize: 13, fontWeight: 600 }}>
            Delete
          </button>
        </div>
      </form>
    </div>
  );
}

export default function HabitsView({ onOpenDrawer }) {
  const [habits, setHabits] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(null); // habit, or null

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setHabits(await listHabits());
  }

  async function handleLog(habitName) {
    await logHabit(habitName);
    refresh();
  }

  async function handleToggleDay(habitId, date, logged) {
    await setHabitDay(habitId, date, logged);
    refresh();
  }

  async function handleAdd(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setName('');
    setShowForm(false);
    await logHabit(trimmed);
    refresh();
  }

  async function handleConfirmDelete() {
    const habit = confirmingDelete;
    setConfirmingDelete(null);
    setHabits((prev) => prev.filter((h) => h.id !== habit.id));
    await deleteHabit(habit.id);
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Habits" subtitle="last 7 days" onOpenDrawer={onOpenDrawer} />

      <div style={{ flex: 1, minHeight: 0, padding: 24, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
        {habits.map((h) => (
          <div
            key={h.id}
            style={{
              background: h.streak > 0 ? 'var(--accent-wash)' : 'var(--panel)',
              border: h.streak > 0 ? '1px solid var(--accent-glow)' : '1px solid var(--border)',
              borderRadius: 12,
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 16,
            }}
          >
            <div style={{ width: 140, fontSize: 14, fontWeight: 600, color: h.streak > 0 ? 'var(--text)' : '#c7c8cc' }}>{h.name}</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {h.last_7_days.map((day) => (
                <Dot key={day.date} day={day} onToggle={(date, logged) => handleToggleDay(h.id, date, logged)} />
              ))}
            </div>
            <button
              onClick={() => handleLog(h.name)}
              style={{
                marginLeft: 'auto',
                height: 30,
                padding: '0 12px',
                borderRadius: 8,
                background: 'transparent',
                border: '1px solid var(--accent-glow)',
                color: 'var(--accent)',
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              Log today
            </button>
            <div style={{ fontSize: 13, color: h.streak > 0 ? 'var(--accent)' : 'var(--text-faint)', fontWeight: 600, minWidth: 90, textAlign: 'right' }}>
              {h.streak > 0 ? `${h.streak} day streak` : 'no streak yet'}
            </div>
            <button
              onClick={() => setConfirmingDelete(h)}
              aria-label="Delete habit"
              title="Delete habit"
              style={{ flexShrink: 0, width: 22, height: 22, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        ))}

        {showForm ? (
          <form onSubmit={handleAdd} style={{ display: 'flex', gap: 10 }}>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Habit name"
              style={{ flex: 1, maxWidth: 240, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '8px 12px', fontSize: 13 }}
            />
            <button type="submit" style={{ background: 'var(--accent)', color: 'var(--accent-text)', border: 'none', borderRadius: 8, padding: '8px 16px', fontSize: 13, fontWeight: 600 }}>
              Add and log today
            </button>
          </form>
        ) : (
          <button
            onClick={() => setShowForm(true)}
            style={{
              alignSelf: 'flex-start',
              marginTop: 8,
              height: 40,
              padding: '0 18px',
              borderRadius: 10,
              background: 'transparent',
              border: '1px solid var(--accent-glow)',
              color: 'var(--accent)',
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            + New habit
          </button>
        )}
      </div>

      {confirmingDelete && (
        <ConfirmDeleteHabit habit={confirmingDelete} onCancel={() => setConfirmingDelete(null)} onConfirm={handleConfirmDelete} />
      )}
    </div>
  );
}
