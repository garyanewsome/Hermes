import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import { completeTask, createTask, deleteTask, listTasks, reopenTask, updateTask } from '../api.js';
import useIsMobile from '../hooks/useIsMobile.js';

const QUADRANTS = [
  { key: 'do', label: 'TODO', color: '#3bffa0', glow: 'rgba(59,255,160,0.35)' },
  { key: 'schedule', label: 'Schedule / plan', color: '#ff9d3b', glow: 'rgba(255,157,59,0.35)' },
  { key: 'next', label: 'NEXT', color: '#eaff3b', glow: 'rgba(234,255,59,0.35)' },
  { key: 'backlog', label: 'Backlog', color: '#6a6b70', glow: 'transparent', dim: true },
];

const QUADRANT_BY_KEY = Object.fromEntries(QUADRANTS.map((q) => [q.key, q]));

function timeAgo(isoString) {
  if (!isoString) return '';
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function TaskRow({ task, quadrant, isDragOver, onDragStart, onDragOverRow, onDragLeaveRow, onDropOnRow, onComplete, onDelete, onOpen }) {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task.id)}
      onDragOver={onDragOverRow}
      onDragLeave={onDragLeaveRow}
      onDrop={onDropOnRow}
      onClick={() => onOpen(task)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'var(--bg)',
        border: `1px solid ${quadrant.color}`,
        borderTop: isDragOver ? `2px solid ${quadrant.color}` : `1px solid ${quadrant.color}`,
        boxShadow: quadrant.dim ? 'none' : `0 0 6px ${quadrant.glow}`,
        borderRadius: 8,
        padding: '8px 10px',
        fontSize: 13,
        cursor: 'pointer',
      }}
    >
      <button
        onClick={(e) => {
          e.stopPropagation();
          onComplete(task.id);
        }}
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
        {task.notes && (
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none" style={{ marginLeft: 6, verticalAlign: -1 }}>
            <rect x="1" y="1" width="9" height="9" rx="1.5" stroke="var(--text-faint)" strokeWidth="1" />
            <path d="M3 4h5M3 6h3" stroke="var(--text-faint)" strokeWidth="1" strokeLinecap="round" />
          </svg>
        )}
        {task.due_date && <span style={{ color: 'var(--text-faint)', fontSize: 11, marginLeft: 8 }}>due {task.due_date}</span>}
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(task.id);
        }}
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

function TaskModal({ task, quadrant, onClose, onSave, onMove }) {
  const [title, setTitle] = useState(task.title);
  const [notes, setNotes] = useState(task.notes || '');
  const [dueDate, setDueDate] = useState(task.due_date || '');

  async function handleSave() {
    if (!title.trim()) return;
    await onSave(task.id, { title: title.trim(), notes, due_date: dueDate });
    onClose();
  }

  return (
    <div
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
      }}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 440,
          maxWidth: '90vw',
          background: 'var(--bg)',
          border: `1px solid ${quadrant.color}`,
          boxShadow: `0 0 20px ${quadrant.glow}`,
          borderRadius: 12,
          padding: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ background: 'transparent', border: 'none', borderBottom: '1px solid var(--border)', color: 'var(--text)', fontSize: 16, fontWeight: 600, padding: '4px 0' }}
        />
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Add a description..."
          rows={5}
          style={{ background: 'var(--panel-2)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '10px 12px', fontSize: 13, resize: 'vertical', fontFamily: 'inherit' }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 12, color: 'var(--text-dim)' }}>Due</label>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            style={{ background: 'var(--panel-2)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 6, padding: '5px 8px', fontSize: 13 }}
          />
          {dueDate && (
            <button
              type="button"
              onClick={() => setDueDate('')}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-faint)', fontSize: 12, textDecoration: 'underline', padding: 0 }}
            >
              Clear
            </button>
          )}
        </div>
        <div>
          {/* Dragging cards between quadrants uses the HTML5 drag API,
              which doesn't fire from touch input at all — this is the
              only way to recategorize a task on a phone/tablet. */}
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 6 }}>Move to</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {QUADRANTS.filter((q) => q.key !== task.quadrant).map((q) => (
              <button
                key={q.key}
                type="button"
                onClick={() => onMove(q.key)}
                style={{ fontSize: 11, padding: '5px 10px', borderRadius: 6, background: 'transparent', border: `1px solid ${q.color}`, color: q.color }}
              >
                {q.label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '7px 14px', fontSize: 13 }}>
            Cancel
          </button>
          <button onClick={handleSave} style={{ background: quadrant.color, border: 'none', color: 'var(--bg)', borderRadius: 8, padding: '7px 14px', fontSize: 13, fontWeight: 600 }}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function QuadrantBox({
  quadrant,
  items,
  isDragOver,
  dragOverTaskId,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragStart,
  onDragOverRow,
  onDragLeaveRow,
  onDropOnRow,
  onComplete,
  onDelete,
  onAdd,
  onOpen,
  isMobile,
}) {
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState('');

  async function submit(e) {
    e.preventDefault();
    if (!title.trim()) return;
    const value = title.trim();
    setTitle('');
    setAdding(false);
    await onAdd(value);
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
        padding: isMobile ? '14px 14px' : '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        overflowY: 'auto',
        maxHeight: isMobile ? '42vh' : 'none',
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
        <TaskRow
          key={t.id}
          task={t}
          quadrant={quadrant}
          isDragOver={dragOverTaskId === t.id}
          onDragStart={onDragStart}
          onDragOverRow={(e) => onDragOverRow(e, t.id)}
          onDragLeaveRow={onDragLeaveRow}
          onDropOnRow={(e) => onDropOnRow(e, quadrant, t)}
          onComplete={onComplete}
          onDelete={onDelete}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

function DoneList({ tasks, onReopen, onDelete }) {
  return (
    <div style={{ flex: 1, minHeight: 0, padding: 24, display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
      {tasks.length === 0 && <div style={{ fontSize: 13, color: 'var(--text-faint)' }}>Nothing completed yet.</div>}
      {tasks.map((t) => {
        const quadrant = QUADRANT_BY_KEY[t.quadrant] || QUADRANTS[0];
        return (
          <div
            key={t.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '10px 12px',
              fontSize: 13,
            }}
          >
            <div style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: quadrant.color }} />
            <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-dim)', textDecoration: 'line-through' }}>
              {t.title}
            </div>
            <div style={{ color: 'var(--text-faint)', fontSize: 11, flexShrink: 0 }}>{timeAgo(t.completed_at)}</div>
            <button
              onClick={() => onReopen(t.id)}
              aria-label="Reopen task"
              title="Reopen task"
              style={{ flexShrink: 0, width: 22, height: 22, background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 6, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 6a4 4 0 1 1 1.2 2.85M2 6V3M2 6h3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button
              onClick={() => onDelete(t.id)}
              aria-label="Delete task"
              title="Delete task"
              style={{ flexShrink: 0, width: 22, height: 22, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default function TasksView({ onOpenDrawer }) {
  const [view, setView] = useState('board'); // 'board' | 'done'
  const [tasks, setTasks] = useState([]);
  const [doneTasks, setDoneTasks] = useState([]);
  const [dragOverKey, setDragOverKey] = useState(null);
  const [dragOverTaskId, setDragOverTaskId] = useState(null);
  const [openTaskId, setOpenTaskId] = useState(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (view === 'done') refreshDone();
  }, [view]);

  async function refresh() {
    setTasks(await listTasks('open'));
  }

  async function refreshDone() {
    setDoneTasks(await listTasks('done'));
  }

  async function handleReopen(id) {
    setDoneTasks((prev) => prev.filter((t) => t.id !== id));
    await reopenTask(id);
    refresh(); // the reopened task needs to show up on the board next time it's viewed
  }

  async function handleDeleteDone(id) {
    setDoneTasks((prev) => prev.filter((t) => t.id !== id));
    await deleteTask(id);
  }

  async function handleAddToQuadrant(quadrant, title) {
    // Optimistic: show it immediately at the end of the box instead of
    // waiting on a create + full refetch round trip before it appears at
    // all — that gap is what made it look like it "entered at the top,
    // then populated at the bottom" (the input sits above the list while
    // adding; the round trip was the delay before anything replaced it).
    const tempId = `temp-${Date.now()}`;
    const siblings = tasks.filter((t) => t.quadrant === quadrant.key);
    const maxPosition = siblings.reduce((m, t) => Math.max(m, t.position ?? 0), -1);
    const optimistic = { id: tempId, title, quadrant: quadrant.key, notes: null, due_date: null, status: 'open', position: maxPosition + 1 };
    setTasks((prev) => [...prev, optimistic]);
    const real = await createTask({ title, quadrant: quadrant.key });
    setTasks((prev) => prev.map((t) => (t.id === tempId ? real : t)));
  }

  async function handleComplete(id) {
    setTasks((prev) => prev.filter((t) => t.id !== id));
    await completeTask(id);
  }

  async function handleDelete(id) {
    setTasks((prev) => prev.filter((t) => t.id !== id));
    await deleteTask(id);
  }

  async function handleSaveTask(id, updates) {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, ...updates } : t)));
    await updateTask(id, updates);
  }

  function handleDragStart(e, taskId) {
    e.dataTransfer.setData('text/plain', String(taskId));
    e.dataTransfer.effectAllowed = 'move';
  }

  async function moveTaskToQuadrant(taskId, quadrantKey) {
    const task = tasks.find((t) => t.id === taskId);
    if (!task || task.quadrant === quadrantKey) return;
    // Append to the end of the target quadrant's own order.
    const siblings = tasks.filter((t) => t.quadrant === quadrantKey);
    const maxPosition = siblings.reduce((m, t) => Math.max(m, t.position ?? 0), -1);
    const newPosition = maxPosition + 1;
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, quadrant: quadrantKey, position: newPosition } : t)));
    await updateTask(taskId, { quadrant: quadrantKey, position: newPosition });
  }

  async function handleDrop(e, quadrant) {
    e.preventDefault();
    setDragOverKey(null);
    const taskId = Number(e.dataTransfer.getData('text/plain'));
    await moveTaskToQuadrant(taskId, quadrant.key);
  }

  async function handleDropOnTask(e, quadrant, targetTask) {
    e.preventDefault();
    e.stopPropagation(); // don't also fire the box-level onDrop for this same drop
    setDragOverKey(null);
    setDragOverTaskId(null);
    const taskId = Number(e.dataTransfer.getData('text/plain'));
    if (taskId === targetTask.id) return;

    // Insert immediately before the target card, wherever it came from —
    // fractional position between it and its current previous sibling, so
    // nothing else in the box needs renumbering.
    const siblings = tasks
      .filter((t) => t.quadrant === quadrant.key && t.id !== taskId)
      .sort((a, b) => a.position - b.position);
    const targetIndex = siblings.findIndex((t) => t.id === targetTask.id);
    const prevSibling = siblings[targetIndex - 1];
    const newPosition = prevSibling ? (prevSibling.position + targetTask.position) / 2 : targetTask.position - 1;

    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, quadrant: quadrant.key, position: newPosition } : t)));
    await updateTask(taskId, { quadrant: quadrant.key, position: newPosition });
  }

  const openTask = tasks.find((t) => t.id === openTaskId);
  const openTaskQuadrant = openTask && QUADRANTS.find((q) => q.key === openTask.quadrant);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Tasks" subtitle={view === 'board' ? 'drag a card to recategorize or reorder' : 'what actually got done'} onOpenDrawer={onOpenDrawer}>
        <div style={{ display: 'flex', border: '1px solid var(--border-strong)', borderRadius: 8, overflow: 'hidden' }}>
          <button
            onClick={() => setView('board')}
            style={{
              padding: '5px 12px',
              fontSize: 12,
              fontWeight: 600,
              background: view === 'board' ? 'rgba(255,255,255,0.08)' : 'transparent',
              color: view === 'board' ? 'var(--text)' : 'var(--text-faint)',
              border: 'none',
            }}
          >
            Board
          </button>
          <button
            onClick={() => setView('done')}
            style={{
              padding: '5px 12px',
              fontSize: 12,
              fontWeight: 600,
              background: view === 'done' ? 'rgba(255,255,255,0.08)' : 'transparent',
              color: view === 'done' ? 'var(--text)' : 'var(--text-faint)',
              border: 'none',
            }}
          >
            Done
          </button>
        </div>
      </TopBar>

      {view === 'board' ? (
        <div
          style={
            isMobile
              ? { flex: 1, minHeight: 0, padding: 12, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }
              : { flex: 1, minHeight: 0, padding: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: '1fr 1fr', gap: 16 }
          }
        >
          {QUADRANTS.map((q) => (
            <QuadrantBox
              key={q.key}
              quadrant={q}
              items={tasks.filter((t) => t.quadrant === q.key).sort((a, b) => a.position - b.position)}
              isDragOver={dragOverKey === q.key}
              dragOverTaskId={dragOverTaskId}
              isMobile={isMobile}
              onDragOver={(e) => {
                e.preventDefault();
                if (dragOverKey !== q.key) setDragOverKey(q.key);
              }}
              onDragLeave={() => setDragOverKey((k) => (k === q.key ? null : k))}
              onDrop={(e) => handleDrop(e, q)}
              onDragStart={handleDragStart}
              onDragOverRow={(e, taskId) => {
                e.preventDefault();
                e.stopPropagation();
                if (dragOverTaskId !== taskId) setDragOverTaskId(taskId);
              }}
              onDragLeaveRow={() => setDragOverTaskId(null)}
              onDropOnRow={(e, quadrant, targetTask) => handleDropOnTask(e, quadrant, targetTask)}
              onComplete={handleComplete}
              onDelete={handleDelete}
              onAdd={(title) => handleAddToQuadrant(q, title)}
              onOpen={(task) => setOpenTaskId(task.id)}
            />
          ))}
        </div>
      ) : (
        <DoneList tasks={doneTasks} onReopen={handleReopen} onDelete={handleDeleteDone} />
      )}

      {openTask && (
        <TaskModal
          task={openTask}
          quadrant={openTaskQuadrant}
          onClose={() => setOpenTaskId(null)}
          onSave={handleSaveTask}
          onMove={(quadrantKey) => {
            moveTaskToQuadrant(openTask.id, quadrantKey);
            setOpenTaskId(null);
          }}
        />
      )}
    </div>
  );
}
