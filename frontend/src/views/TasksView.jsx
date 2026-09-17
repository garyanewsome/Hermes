import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { completeTask, createTask, listTasks } from '../api.js';

const QUADRANTS = [
  { key: 'do', label: 'Do first', hint: 'Urgent and important', match: (t) => t.urgent && t.important, accent: true },
  { key: 'schedule', label: 'Schedule', hint: 'Important, not urgent', match: (t) => !t.urgent && t.important, accent: false },
  { key: 'delegate', label: 'Delegate', hint: 'Urgent, not important', match: (t) => t.urgent && !t.important, accent: false },
  { key: 'eliminate', label: 'Eliminate', hint: 'Neither urgent nor important', match: (t) => !t.urgent && !t.important, accent: false, dim: true },
];

export default function TasksView({ onOpenDrawer }) {
  const [tasks, setTasks] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [important, setImportant] = useState(false);
  const [dueDate, setDueDate] = useState('');

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setTasks(await listTasks('open'));
  }

  async function handleAdd(e) {
    e.preventDefault();
    if (!title.trim()) return;
    await createTask({ title: title.trim(), urgent, important, dueDate });
    setTitle('');
    setUrgent(false);
    setImportant(false);
    setDueDate('');
    setShowForm(false);
    refresh();
  }

  async function handleComplete(id) {
    await completeTask(id);
    refresh();
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Tasks" subtitle="Eisenhower matrix" onOpenDrawer={onOpenDrawer}>
        <button
          onClick={() => setShowForm((v) => !v)}
          style={{
            height: 32,
            padding: '0 14px',
            borderRadius: 8,
            background: 'transparent',
            border: '1px solid var(--accent-glow)',
            color: 'var(--accent)',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          + Add task
        </button>
      </TopBar>

      {showForm && (
        <form onSubmit={handleAdd} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '14px 32px', borderBottom: '1px solid var(--border)' }}>
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Task title"
            style={{ flex: 1, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '8px 12px', fontSize: 14 }}
          />
          <label style={{ fontSize: 13, color: 'var(--text-dim)', display: 'flex', gap: 5, alignItems: 'center' }}>
            <input type="checkbox" checked={urgent} onChange={(e) => setUrgent(e.target.checked)} /> Urgent
          </label>
          <label style={{ fontSize: 13, color: 'var(--text-dim)', display: 'flex', gap: 5, alignItems: 'center' }}>
            <input type="checkbox" checked={important} onChange={(e) => setImportant(e.target.checked)} /> Important
          </label>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '7px 10px', fontSize: 13 }}
          />
          <button type="submit" style={{ background: 'var(--accent)', color: 'var(--accent-text)', border: 'none', borderRadius: 8, padding: '8px 16px', fontSize: 13, fontWeight: 600 }}>
            Add
          </button>
        </form>
      )}

      <div style={{ flex: 1, minHeight: 0, padding: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr', gap: 16 }}>
        {QUADRANTS.map((q) => {
          const items = tasks.filter(q.match);
          return (
            <div
              key={q.key}
              style={{
                background: q.accent ? 'var(--accent-wash)' : q.dim ? 'rgba(255,255,255,0.02)' : 'var(--panel)',
                border: q.accent ? '1px solid var(--accent-glow)' : '1px solid var(--border)',
                borderRadius: 12,
                padding: '18px 20px',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                overflowY: 'auto',
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: q.accent ? 'var(--accent)' : q.dim ? 'var(--text-faint)' : '#c7c8cc', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                {q.label}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: -8 }}>{q.hint}</div>
              {items.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Nothing here.</div>}
              {items.map((t) => (
                <div
                  key={t.id}
                  onClick={() => handleComplete(t.id)}
                  title="Click to mark done"
                  style={{
                    background: 'var(--panel-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    padding: '10px 12px',
                    fontSize: 13,
                    cursor: 'pointer',
                  }}
                >
                  {t.title}
                  {t.due_date && <span style={{ color: 'var(--text-faint)', fontSize: 11, marginLeft: 8 }}>due {t.due_date}</span>}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
