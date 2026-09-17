import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { completeTask, createTask, deleteTask, listTasks, updateTask } from '../api.js';

const QUADRANTS = [
  { key: 'do', label: 'TODO', color: '#3bffa0', glow: 'rgba(59,255,160,0.35)' },
  { key: 'schedule', label: 'Schedule / plan', color: '#ff9d3b', glow: 'rgba(255,157,59,0.35)' },
  { key: 'next', label: 'NEXT', color: '#eaff3b', glow: 'rgba(234,255,59,0.35)' },
  { key: 'backlog', label: 'Backlog', color: '#6a6b70', glow: 'transparent', dim: true },
];

function TaskRow({ task, quadrant, onDragStart, onComplete, onDelete }) {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task.id)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--bg)',
        border: `1px solid ${quadrant.color}`,
        boxShadow: quadrant.dim ? 'none' : `0 0 6px ${quadrant.glow}`,
        borderRadius: 8,
        padding: '8px 10px',
        fontSize: 13,
        cursor: 'grab',
      }}
    >
      <button
        onClick={() => onComplete(task.id)}
        aria-label="Mark done"
        title="Mark done"
        style={{
          width: 16,
          height: 16,
          flexShrink: 0,
          borderRadius: 4,
          background: 'transparent',
          border: `1px solid ${quadrant.color}`,
          padding: 0,
        }}
      />
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {task.title}
        {task.due_date && <span style={{ color: 'var(--text-faint)', fontSize: 11, marginLeft: 8 }}>due {task.due_date}</span>}
      </div>
      <button
        onClick={() => onDelete(task.id)}
        aria-label="Delete task"
        title="Delete task"
        style={{ flexShrink: 0, width: 20, height: 20, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}

function QuadrantBox({ quadrant, items, isDragOver, onDragOver, onDragLeave, onDrop, onDragStart, onComplete, onDelete, onAdd }) {
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
        background: 'var(--bg)',
        border: `1px solid ${isDragOver ? quadrant.color : quadrant.dim ? 'var(--border)' : quadrant.color}`,
        boxShadow: isDragOver || quadrant.dim ? 'none' : `0 0 10px ${quadrant.glow}`,
        borderStyle: isDragOver ? 'dashed' : 'solid',
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
        <div style={{ fontSize: 13, fontWeight: 600, color: quadrant.dim ? 'var(--text-faint)' : quadrant.color, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
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
        <TaskRow key={t.id} task={t} quadrant={quadrant} onDragStart={onDragStart} onComplete={onComplete} onDelete={onDelete} />
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
    await createTask({ title, quadrant: quadrant.key });
    refresh();
  }

  async function handleComplete(id) {
    await completeTask(id);
    refresh();
  }

  async function handleDelete(id) {
    await deleteTask(id);
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
    if (!task || task.quadrant === quadrant.key) return;
    // Optimistic move so the card doesn't snap back while the request is in flight.
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, quadrant: quadrant.key } : t)));
    await updateTask(taskId, quadrant.key);
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
            items={tasks.filter((t) => t.quadrant === q.key)}
            isDragOver={dragOverKey === q.key}
            onDragOver={(e) => {
              e.preventDefault();
              if (dragOverKey !== q.key) setDragOverKey(q.key);
            }}
            onDragLeave={() => setDragOverKey((k) => (k === q.key ? null : k))}
            onDrop={(e) => handleDrop(e, q)}
            onDragStart={handleDragStart}
            onComplete={handleComplete}
            onDelete={handleDelete}
            onAdd={(title) => handleAddToQuadrant(q, title)}
          />
        ))}
      </div>
    </div>
  );
}
