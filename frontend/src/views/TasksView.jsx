import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { completeTask, createTask, listTasks, updateTask } from '../api.js';

const QUADRANTS = [
  { key: 'do', label: 'Do first', urgent: true, important: true, accent: true },
  { key: 'schedule', label: 'Schedule / plan', urgent: false, important: true, accent: false },
  { key: 'next', label: 'Do next', urgent: true, important: false, accent: false },
  { key: 'backlog', label: 'Backlog', urgent: false, important: false, accent: false, dim: true },
];

function quadrantOf(task) {
  return QUADRANTS.find((q) => q.urgent === task.urgent && q.important === task.important);
}

function QuadrantBox({ quadrant, items, isDragOver, onDragOver, onDragLeave, onDrop, onDragStart, onComplete, onAdd }) {
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState('');

  async function submit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    await onAdd(title.trim());
    setTitle('');
    setAdding(false);
  }

  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      style={{
        background: quadrant.accent ? 'var(--accent-wash)' : quadrant.dim ? 'rgba(255,255,255,0.02)' : 'var(--panel)',
        border: isDragOver ? '1px dashed var(--accent)' : quadrant.accent ? '1px solid var(--accent-glow)' : '1px solid var(--border)',
        borderRadius: 12,
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        overflowY: 'auto',
        transition: 'border-color 0.1s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: quadrant.accent ? 'var(--accent)' : quadrant.dim ? 'var(--text-faint)' : '#c7c8cc', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {quadrant.label}
        </div>
        <button
          onClick={() => setAdding((v) => !v)}
          aria-label={`Add task to ${quadrant.label}`}
          style={{
            width: 22,
            height: 22,
            borderRadius: 6,
            background: 'transparent',
            border: '1px solid var(--border-strong)',
            color: 'var(--text-faint)',
            fontSize: 14,
            lineHeight: '20px',
            padding: 0,
          }}
        >
          +
        </button>
      </div>

      {adding && (
        <form onSubmit={submit} style={{ display: 'flex', gap: 6 }}>
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setAdding(false);
                setTitle('');
              }
            }}
            onBlur={() => {
              if (!title.trim()) setAdding(false);
            }}
            placeholder="Task title"
            style={{ flex: 1, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 6, padding: '6px 10px', fontSize: 13 }}
          />
        </form>
      )}

      {items.length === 0 && !adding && <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Nothing here.</div>}
      {items.map((t) => (
        <div
          key={t.id}
          draggable
          onDragStart={(e) => onDragStart(e, t.id)}
          onClick={() => onComplete(t.id)}
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
}

export default function TasksView({ onOpenDrawer }) {
  const [tasks, setTasks] = useState([]);
  const [dragOverKey, setDragOverKey] = useState(null);

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setTasks(await listTasks('open'));
  }

  async function handleAddToQuadrant(quadrant, title) {
    await createTask({ title, urgent: quadrant.urgent, important: quadrant.important });
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
      <TopBar title="Tasks" subtitle="drag a card to recategorize" onOpenDrawer={onOpenDrawer} />

      <div style={{ flex: 1, minHeight: 0, padding: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr', gap: 16 }}>
        {QUADRANTS.map((q) => (
          <QuadrantBox
            key={q.key}
            quadrant={q}
            items={tasks.filter((t) => quadrantOf(t)?.key === q.key)}
            isDragOver={dragOverKey === q.key}
            onDragOver={(e) => {
              e.preventDefault();
              if (dragOverKey !== q.key) setDragOverKey(q.key);
            }}
            onDragLeave={() => setDragOverKey((k) => (k === q.key ? null : k))}
            onDrop={(e) => handleDrop(e, q)}
            onDragStart={handleDragStart}
            onComplete={handleComplete}
            onAdd={(title) => handleAddToQuadrant(q, title)}
          />
        ))}
      </div>
    </div>
  );
}
