import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { listHabits, logHabit, setHabitDay } from '../api.js';

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

export default function HabitsView({ onOpenDrawer }) {
  const [habits, setHabits] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');

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
    </div>
  );
}
