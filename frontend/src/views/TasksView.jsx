import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { completeTask, createTask, listTasks, updateTask } from '../api.js';

const QUADRANTS = [
  { key: 'do', label: 'Do first', hint: 'Urgent and important', urgent: true, important: true, accent: true },
  { key: 'next', label: 'Do next', hint: 'Urgent, not important', urgent: true, important: false, accent: false },
  { key: 'schedule', label: 'Schedule / plan', hint: 'Important, not urgent', urgent: false, important: true, accent: false },
  { key: 'backlog', label: 'Backlog', hint: "Neither — someday, maybe", urgent: false, important: false, accent: false, dim: true },
];

function quadrantOf(task) {
  return QUADRANTS.find((q) => q.urgent === task.urgent && q.important === task.important);
}

export default function TasksView({ onOpenDrawer }) {
  const [tasks, setTasks] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [urgent, setUrgent] = useState(false);
  const [important, setImportant] = useState(false);
  const [dueDate, setDueDate] = useState('');
  const [dragOverKey, setDragOverKey] = useState(null);

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

  function handleDragStart(e, taskId) {
    e.dataTransfer.setData('text/plain', String(taskId));
    e.dataTransfer.effectAllowed = 'move';
  }

  async function handleDrop(e, quadrant) {
    e.preventDefault();
    setDragOverKey(null);
    const taskId = Number(e.dataTransfer.getData('text/plain'));
    const task = tasks.find((t) => t.id === taskId);
    if (!task || (task.urgent === quadrant.urgent && task.important === quadrant.important)) return;
    // Optimistic move so the card doesn't snap back while the request is in flight.
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, urgent: quadrant.urgent, important: quadrant.important } : t)));
    await updateTask(taskId, { urgent: quadrant.urgent, important: quadrant.important });
    refresh();
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Tasks" subtitle="drag a card to recategorize" onOpenDrawer={onOpenDrawer}>
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
          const items = tasks.filter((t) => quadrantOf(t)?.key === q.key);
          const isDragOver = dragOverKey === q.key;
          return (
            <div
              key={q.key}
              onDragOver={(e) => {
                e.preventDefault();
                if (dragOverKey !== q.key) setDragOverKey(q.key);
              }}
              onDragLeave={() => setDragOverKey((k) => (k === q.key ? null : k))}
              onDrop={(e) => handleDrop(e, q)}
              style={{
                background: q.accent ? 'var(--accent-wash)' : q.dim ? 'rgba(255,255,255,0.02)' : 'var(--panel)',
                border: isDragOver ? '1px dashed var(--accent)' : q.accent ? '1px solid var(--accent-glow)' : '1px solid var(--border)',
                borderRadius: 12,
                padding: '18px 20px',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                overflowY: 'auto',
                transition: 'border-color 0.1s ease',
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
                  draggable
                  onDragStart={(e) => handleDragStart(e, t.id)}
                  onClick={() => handleComplete(t.id)}
                  title="Drag to recategorize, click to mark done"
                  style={{
                    background: 'var(--panel-2)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    padding: '10px 12px',
                    fontSize: 13,
                    cursor: 'grab',
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
