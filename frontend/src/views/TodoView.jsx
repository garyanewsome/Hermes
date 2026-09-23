import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import {
  listTodoLists,
  createTodoList,
  updateTodoList,
  deleteTodoList,
  listTodoItems,
  createTodoItem,
  updateTodoItem,
  deleteTodoItem,
} from '../api.js';

function StarIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
      <path d="M6 0.5l1.64 3.53 3.86.46-2.9 2.64.79 3.87L6 9.1 2.61 11l.79-3.87-2.9-2.64 3.86-.46z" />
    </svg>
  );
}

function RepeatIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
      <path d="M2 6.5V5a3 3 0 0 1 3-3h5.5M12 2v3h-3M12 7.5V9a3 3 0 0 1-3 3H3.5M2 12v-3h3" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const WEEKDAY_LABELS = [
  { iso: 1, short: 'Mo' },
  { iso: 2, short: 'Tu' },
  { iso: 3, short: 'We' },
  { iso: 4, short: 'Th' },
  { iso: 5, short: 'Fr' },
  { iso: 6, short: 'Sa' },
  { iso: 7, short: 'Su' },
];

const RECURRENCE_PRESETS = [
  ['Daily', 1],
  ['Weekly', 7],
  ['Biweekly', 14],
  ['Monthly', 30],
];

function formatRecurrence(item) {
  if (item.recurrence_days) return `every ${item.recurrence_days}d`;
  if (item.recurrence_weekdays) {
    const days = new Set(item.recurrence_weekdays.split(',').map(Number));
    return WEEKDAY_LABELS.filter((w) => days.has(w.iso))
      .map((w) => w.short)
      .join('/');
  }
  return null;
}

function RecurrencePopover({ item, onApply, onClear, onClose }) {
  const [mode, setMode] = useState(item.recurrence_weekdays ? 'weekdays' : 'days');
  const [daysValue, setDaysValue] = useState(item.recurrence_days ? String(item.recurrence_days) : '');
  const [selectedWeekdays, setSelectedWeekdays] = useState(
    new Set(item.recurrence_weekdays ? item.recurrence_weekdays.split(',').map(Number) : [])
  );

  function toggleWeekday(iso) {
    setSelectedWeekdays((prev) => {
      const next = new Set(prev);
      if (next.has(iso)) next.delete(iso);
      else next.add(iso);
      return next;
    });
  }

  const canApply = mode === 'days' ? parseInt(daysValue, 10) > 0 : selectedWeekdays.size > 0;

  function handleApply() {
    if (!canApply) return;
    if (mode === 'days') {
      onApply({ recurrence_days: parseInt(daysValue, 10) });
    } else {
      onApply({ recurrence_weekdays: [...selectedWeekdays].sort((a, b) => a - b).join(',') });
    }
  }

  const hasExistingRecurrence = Boolean(item.recurrence_days || item.recurrence_weekdays);

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 300,
          maxWidth: '90vw',
          background: 'var(--bg)',
          border: '1px solid var(--accent)',
          boxShadow: '0 0 20px var(--accent-glow)',
          borderRadius: 12,
          padding: 18,
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Repeat</div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', fontSize: 18, padding: 0, lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        <div style={{ display: 'flex', gap: 4, background: 'var(--panel-2)', borderRadius: 8, padding: 3 }}>
          {[
            ['days', 'Every N days'],
            ['weekdays', 'Days of week'],
          ].map(([m, label]) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                flex: 1,
                padding: '6px 0',
                fontSize: 12.5,
                borderRadius: 6,
                border: 'none',
                background: mode === m ? 'var(--accent)' : 'transparent',
                color: mode === m ? 'var(--accent-text)' : 'var(--text-dim)',
                fontWeight: mode === m ? 600 : 400,
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === 'days' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>Every</span>
              {/* type="text" + digit filtering, not type="number" — that's
                  exactly what caused the native spinner arrows to overlap
                  the value in the old inline input. */}
              <input
                type="text"
                inputMode="numeric"
                autoFocus
                value={daysValue}
                onChange={(e) => setDaysValue(e.target.value.replace(/[^0-9]/g, ''))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canApply) handleApply();
                }}
                style={{
                  width: 56,
                  textAlign: 'center',
                  background: 'var(--panel-2)',
                  border: '1px solid var(--border-strong)',
                  color: 'var(--text)',
                  borderRadius: 6,
                  padding: '6px 4px',
                  fontSize: 14,
                }}
              />
              <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>days</span>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {RECURRENCE_PRESETS.map(([label, n]) => (
                <button
                  key={label}
                  onClick={() => setDaysValue(String(n))}
                  style={{
                    background: String(n) === daysValue ? 'var(--accent-wash)' : 'var(--panel-2)',
                    border: `1px solid ${String(n) === daysValue ? 'var(--accent)' : 'var(--border-strong)'}`,
                    color: String(n) === daysValue ? 'var(--accent)' : 'var(--text-dim)',
                    borderRadius: 6,
                    padding: '4px 10px',
                    fontSize: 11.5,
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 5, justifyContent: 'space-between' }}>
            {WEEKDAY_LABELS.map((w) => (
              <button
                key={w.iso}
                onClick={() => toggleWeekday(w.iso)}
                aria-pressed={selectedWeekdays.has(w.iso)}
                style={{
                  width: 34,
                  height: 34,
                  flexShrink: 0,
                  borderRadius: '50%',
                  border: `1px solid ${selectedWeekdays.has(w.iso) ? 'var(--accent)' : 'var(--border-strong)'}`,
                  background: selectedWeekdays.has(w.iso) ? 'var(--accent-wash)' : 'transparent',
                  color: selectedWeekdays.has(w.iso) ? 'var(--accent)' : 'var(--text-dim)',
                  fontSize: 12,
                  fontWeight: selectedWeekdays.has(w.iso) ? 700 : 400,
                }}
              >
                {w.short}
              </button>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
          {hasExistingRecurrence ? (
            <button onClick={onClear} style={{ background: 'transparent', border: 'none', color: '#ff6b6b', fontSize: 12.5, padding: 0 }}>
              Stop repeating
            </button>
          ) : (
            <span />
          )}
          <button
            onClick={handleApply}
            disabled={!canApply}
            style={{
              background: canApply ? 'var(--accent)' : 'var(--panel-2)',
              color: canApply ? 'var(--accent-text)' : 'var(--text-faint)',
              border: 'none',
              borderRadius: 8,
              padding: '7px 16px',
              fontSize: 13,
              fontWeight: 600,
              cursor: canApply ? 'pointer' : 'default',
            }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfirmDeleteList({ list, onCancel, onConfirm }) {
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
          Delete "{list.name}"? Everything on it goes with it — this can't be undone.
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

function ListPicker({ lists, activeId, onSelect, onCreate, onRename, onReorder, onDelete, isMobile, mobileOpen, onMobileClose }) {
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);

  if (isMobile && !mobileOpen) return null;

  async function submitCreate(e) {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) return;
    setNewName('');
    setAdding(false);
    const list = await onCreate(trimmed);
    onSelect(list.id);
    if (isMobile) onMobileClose();
  }

  async function commitRename(list) {
    const trimmed = renameValue.trim();
    setRenamingId(null);
    if (trimmed && trimmed !== list.name) {
      onRename(list.id, trimmed);
    }
  }

  async function confirmDelete() {
    const list = confirmingDelete;
    setConfirmingDelete(null);
    onDelete(list.id);
  }

  function handleDragStart(e, listId) {
    e.dataTransfer.setData('text/plain', String(listId));
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDropOnList(e, targetList) {
    e.preventDefault();
    e.stopPropagation(); // don't also fire the container's own onDrop (append-to-end) for this same drop
    setDragOverId(null);
    const draggedId = Number(e.dataTransfer.getData('text/plain'));
    if (draggedId === targetList.id) return;

    // Insert immediately before the target — fractional position between
    // it and its current previous sibling, same approach already used for
    // reordering task cards (see TasksView.jsx's handleDropOnTask).
    const siblings = lists.filter((l) => l.id !== draggedId);
    const targetIndex = siblings.findIndex((l) => l.id === targetList.id);
    const prevSibling = siblings[targetIndex - 1];
    const newPosition = prevSibling ? (prevSibling.position + targetList.position) / 2 : targetList.position - 1;
    onReorder(draggedId, newPosition);
  }

  function handleDropAtEnd(e) {
    e.preventDefault();
    const draggedId = Number(e.dataTransfer.getData('text/plain'));
    const last = lists[lists.length - 1];
    if (!last || draggedId === last.id) return;
    onReorder(draggedId, last.position + 1);
  }

  return (
    <>
      {isMobile && (
        <div onClick={onMobileClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 40 }} />
      )}
      <div
        style={
          isMobile
            ? {
                position: 'fixed',
                top: 0,
                right: 0,
                bottom: 0,
                width: 'min(280px, 85vw)',
                background: 'var(--panel)',
                borderLeft: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
                zIndex: 41,
                paddingTop: 'env(safe-area-inset-top)',
              }
            : {
                width: 220,
                flexShrink: 0,
                background: 'var(--panel)',
                borderLeft: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
              }
        }
      >
        <div style={{ padding: 12 }}>
          {adding ? (
            <form onSubmit={submitCreate} style={{ display: 'flex', gap: 6 }}>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  // Explicit, not just relying on native "Enter submits a
                  // single-input form" — every other commit-on-Enter field
                  // in this app already does this explicitly, and it's the
                  // one that's actually reliable across input methods.
                  if (e.key === 'Enter') { e.preventDefault(); submitCreate(e); }
                  if (e.key === 'Escape') {
                    setAdding(false);
                    setNewName('');
                  }
                }}
                onBlur={() => {
                  if (!newName.trim()) setAdding(false);
                }}
                placeholder="List name"
                style={{ flex: 1, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 6, padding: '6px 10px', fontSize: 13 }}
              />
            </form>
          ) : (
            <button
              onClick={() => setAdding(true)}
              style={{
                width: '100%',
                padding: '9px 12px',
                background: 'var(--accent)',
                color: 'var(--accent-text)',
                border: 'none',
                borderRadius: 8,
                fontSize: 13.5,
                textAlign: 'left',
                boxShadow: '0 0 14px var(--accent-glow)',
              }}
            >
              + New list
            </button>
          )}
        </div>

        <div
          style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDropAtEnd}
        >
          {lists.map((list) => (
            <div key={list.id} style={{ marginBottom: 2 }}>
              {renamingId === list.id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={() => commitRename(list)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { e.preventDefault(); commitRename(list); }
                    if (e.key === 'Escape') { e.preventDefault(); setRenamingId(null); }
                  }}
                  style={{
                    width: '100%',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                    border: '1px solid var(--accent)',
                    borderRadius: 5,
                    padding: '7px 8px',
                    fontSize: 13,
                    fontFamily: 'inherit',
                    outline: 'none',
                  }}
                />
              ) : (
                <div
                  draggable
                  onDragStart={(e) => handleDragStart(e, list.id)}
                  onDragOver={(e) => {
                    e.preventDefault();
                    if (dragOverId !== list.id) setDragOverId(list.id);
                  }}
                  onDragLeave={() => setDragOverId((id) => (id === list.id ? null : id))}
                  onDrop={(e) => handleDropOnList(e, list)}
                  onClick={() => {
                    onSelect(list.id);
                    if (isMobile) onMobileClose();
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '9px 10px',
                    borderRadius: 8,
                    fontSize: 13,
                    color: list.id === activeId ? 'var(--text)' : 'var(--text-dim)',
                    cursor: 'grab',
                    background: list.id === activeId ? 'rgba(255,255,255,0.06)' : 'transparent',
                    boxShadow: list.id === activeId ? 'inset 2px 0 0 var(--accent)' : 'none',
                    borderTop: dragOverId === list.id ? '2px solid var(--accent)' : '2px solid transparent',
                  }}
                >
                  {list.due_today_count > 0 && (
                    <div
                      title={`${list.due_today_count} item${list.due_today_count === 1 ? '' : 's'} due today`}
                      style={{ flexShrink: 0, color: 'var(--accent)', display: 'flex' }}
                    >
                      <StarIcon />
                    </div>
                  )}
                  <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {list.name}
                  </div>
                  {list.open_count > 0 && (
                    <div style={{ fontSize: 11, color: 'var(--text-faint)', flexShrink: 0 }}>{list.open_count}</div>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setRenamingId(list.id);
                      setRenameValue(list.name);
                    }}
                    aria-label="Rename list"
                    title="Rename list"
                    style={{ flexShrink: 0, width: 18, height: 18, background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <path d="M8.5 1.5l2 2-6 6-2.4.4.4-2.4 6-6z" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmingDelete(list);
                    }}
                    aria-label="Delete list"
                    title="Delete list"
                    style={{ flexShrink: 0, width: 18, height: 18, background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                  >
                    <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                      <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {confirmingDelete && (
        <ConfirmDeleteList list={confirmingDelete} onCancel={() => setConfirmingDelete(null)} onConfirm={confirmDelete} />
      )}
    </>
  );
}

function TodoItemRow({ item, onToggle, onUpdate, onDelete, onDragStart, isDragOver, onDragOverRow, onDragLeaveRow, onDropOnRow }) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(item.text);
  const [pickingDate, setPickingDate] = useState(false);
  const [pickingRecurrence, setPickingRecurrence] = useState(false);

  function commitEdit() {
    const trimmed = editValue.trim();
    setEditing(false);
    if (trimmed && trimmed !== item.text) onUpdate(item.id, { text: trimmed });
  }

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, item.id)}
      onDragOver={onDragOverRow}
      onDragLeave={onDragLeaveRow}
      onDrop={onDropOnRow}
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 10,
        background: 'var(--bg)',
        border: '1px solid var(--border)',
        borderTop: isDragOver ? '2px solid var(--accent)' : '1px solid var(--border)',
        borderRadius: 8,
        padding: '10px 12px',
        fontSize: 14,
        cursor: 'grab',
      }}
    >
      <button
        onClick={() => onToggle(item.id, !item.done)}
        aria-label={item.done ? 'Mark not done' : 'Mark done'}
        style={{
          width: 18,
          height: 18,
          flexShrink: 0,
          borderRadius: 5,
          background: 'transparent',
          border: `1px solid ${item.done ? 'var(--accent)' : 'var(--border-strong)'}`,
          padding: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {item.done && (
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <path d="M2.3 6.2l2.3 2.3 4.7-5" stroke="var(--accent)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>
      {editing ? (
        <input
          autoFocus
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); commitEdit(); }
            if (e.key === 'Escape') { e.preventDefault(); setEditValue(item.text); setEditing(false); }
          }}
          style={{
            flex: 1,
            minWidth: 120,
            background: 'var(--panel-2)',
            border: '1px solid var(--accent)',
            color: 'var(--text)',
            borderRadius: 5,
            padding: '4px 6px',
            fontSize: 14,
            fontFamily: 'inherit',
            outline: 'none',
          }}
        />
      ) : (
        <div
          onClick={() => { setEditValue(item.text); setEditing(true); }}
          style={{
            flex: 1,
            minWidth: 120,
            overflowWrap: 'break-word',
            cursor: 'text',
            color: item.done ? 'var(--text-faint)' : 'var(--text)',
            textDecoration: item.done ? 'line-through' : 'none',
          }}
        >
          {item.text}
        </div>
      )}

      {pickingDate ? (
        <input
          type="date"
          autoFocus
          defaultValue={item.due_date || ''}
          onChange={(e) => {
            onUpdate(item.id, { due_date: e.target.value });
            setPickingDate(false);
          }}
          onBlur={() => setPickingDate(false)}
          style={{ background: 'var(--panel-2)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 6, padding: '4px 6px', fontSize: 12 }}
        />
      ) : item.due_date ? (
        <button
          onClick={() => setPickingDate(true)}
          style={{ flexShrink: 0, background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 6, padding: '3px 8px', fontSize: 11 }}
        >
          due {item.due_date}
        </button>
      ) : (
        <button
          onClick={() => setPickingDate(true)}
          aria-label="Set due date"
          title="Set due date"
          style={{ flexShrink: 0, width: 22, height: 22, background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1.5" y="2.5" width="11" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.1" />
            <path d="M1.5 5.5h11M4 1.3v2M10 1.3v2" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
          </svg>
        </button>
      )}
      {item.due_date && !pickingDate && (
        <button
          onClick={() => onUpdate(item.id, { due_date: '' })}
          aria-label="Clear due date"
          title="Clear due date"
          style={{ flexShrink: 0, background: 'transparent', border: 'none', color: 'var(--text-dim)', fontSize: 12, padding: 0 }}
        >
          ×
        </button>
      )}

      {formatRecurrence(item) ? (
        <button
          onClick={() => setPickingRecurrence(true)}
          title="Repeats — click to change"
          style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4, background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 6, padding: '5px 10px', fontSize: 11 }}
        >
          <RepeatIcon />
          {formatRecurrence(item)}
        </button>
      ) : (
        <button
          onClick={() => setPickingRecurrence(true)}
          aria-label="Make recurring"
          title="Make recurring"
          style={{ flexShrink: 0, width: 22, height: 22, background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <RepeatIcon />
        </button>
      )}
      {pickingRecurrence && (
        <RecurrencePopover
          item={item}
          onApply={(updates) => {
            setPickingRecurrence(false);
            onUpdate(item.id, updates);
          }}
          onClear={() => {
            setPickingRecurrence(false);
            onUpdate(item.id, { recurrence_days: 0, recurrence_weekdays: '' });
          }}
          onClose={() => setPickingRecurrence(false)}
        />
      )}

      <button
        onClick={() => onDelete(item.id)}
        aria-label="Delete item"
        title="Delete item"
        style={{ flexShrink: 0, width: 20, height: 20, background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
          <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}

const TODO_POLL_INTERVAL_MS = 30000;

export default function TodoView({ onOpenDrawer, onDueTodayChange }) {
  const [lists, setLists] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [items, setItems] = useState([]);
  const [newItemText, setNewItemText] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [hideDone, setHideDone] = useState(false);
  const [dragOverItemId, setDragOverItemId] = useState(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    refreshLists();
    // TodoView stays mounted even when another view is active (see
    // App.jsx's comment on why), so this is also what keeps the nav
    // drawer's "due today" star fresh while you're looking at Chat/Notes/
    // whatever else — not just when Todo happens to be the active view.
    const interval = setInterval(refreshLists, TODO_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeId != null) refreshItems(activeId);
  }, [activeId]);

  useEffect(() => {
    onDueTodayChange?.(lists.reduce((sum, l) => sum + (l.due_today_count || 0), 0));
  }, [lists, onDueTodayChange]);

  async function refreshLists() {
    const fetched = await listTodoLists();
    setLists(fetched);
    setActiveId((current) => {
      if (current != null && fetched.some((l) => l.id === current)) return current;
      return fetched[0]?.id ?? null;
    });
  }

  async function refreshItems(listId) {
    setItems(await listTodoItems(listId));
  }

  async function handleCreateList(name) {
    const list = await createTodoList(name);
    setLists((prev) => [...prev, list]);
    return list;
  }

  async function handleRenameList(listId, name) {
    setLists((prev) => prev.map((l) => (l.id === listId ? { ...l, name } : l)));
    await updateTodoList(listId, { name });
  }

  async function handleReorderList(listId, position) {
    setLists((prev) =>
      prev.map((l) => (l.id === listId ? { ...l, position } : l)).sort((a, b) => a.position - b.position)
    );
    await updateTodoList(listId, { position });
  }

  async function handleDeleteList(listId) {
    setLists((prev) => prev.filter((l) => l.id !== listId));
    if (activeId === listId) setActiveId(null);
    await deleteTodoList(listId);
  }

  async function handleAddItem(e) {
    e.preventDefault();
    const text = newItemText.trim();
    if (!text || activeId == null) return;
    setNewItemText('');
    const tempId = `temp-${Date.now()}`;
    // Append after the other open items, before any done ones — matches
    // the server's own ORDER BY (done, created_at), so this doesn't
    // silently reshuffle on the next refresh.
    setItems((prev) => [...prev.filter((i) => !i.done), { id: tempId, text, done: false }, ...prev.filter((i) => i.done)]);
    const real = await createTodoItem(activeId, text);
    setItems((prev) => prev.map((i) => (i.id === tempId ? real : i)));
    setLists((prev) => prev.map((l) => (l.id === activeId ? { ...l, open_count: (l.open_count || 0) + 1 } : l)));
  }

  async function handleToggle(itemId, done) {
    const prevItem = items.find((i) => i.id === itemId);
    setItems((prev) => {
      const next = prev.map((i) => (i.id === itemId ? { ...i, done } : i));
      return [...next.filter((i) => !i.done), ...next.filter((i) => i.done)];
    });
    const updated = await updateTodoItem(itemId, { done });
    // Reconcile with what actually happened, not what was asked for — a
    // recurring item's "mark done" silently turns into "stays open,
    // due_date pushed out" server-side, so the optimistic flip above can
    // be wrong. Confirmed live: without this, a recurring item visually
    // stayed checked off forever instead of resetting for its next cycle.
    setItems((prev) => {
      const next = prev.map((i) => (i.id === itemId ? updated : i));
      return [...next.filter((i) => !i.done), ...next.filter((i) => i.done)];
    });
    if (prevItem && prevItem.done !== updated.done) {
      const delta = updated.done ? -1 : 1;
      setLists((prev) =>
        prev.map((l) => (l.id === activeId ? { ...l, open_count: Math.max(0, (l.open_count || 0) + delta) } : l))
      );
    }
    // done and due_date both feed the sidebar's "due today" marker
    // (recurring items also move due_date here) — an optimistic patch
    // would need to know the old due_date too to get right, so just
    // refetch rather than trying to diff it client-side.
    if (prevItem && (prevItem.done !== updated.done || prevItem.due_date !== updated.due_date)) {
      refreshLists();
    }
  }

  async function handleUpdateItem(itemId, updates) {
    setItems((prev) => prev.map((i) => (i.id === itemId ? { ...i, ...updates } : i)));
    const updated = await updateTodoItem(itemId, updates);
    setItems((prev) => prev.map((i) => (i.id === itemId ? updated : i)));
    if ('due_date' in updates) refreshLists();
  }

  async function handleDeleteItem(itemId) {
    const item = items.find((i) => i.id === itemId);
    setItems((prev) => prev.filter((i) => i.id !== itemId));
    if (item && !item.done) {
      setLists((prev) => prev.map((l) => (l.id === activeId ? { ...l, open_count: Math.max(0, (l.open_count || 0) - 1) } : l)));
    }
    await deleteTodoItem(itemId);
    // After the delete completes, not before — refetching too early would
    // still see the item server-side and get a stale due-today count.
    if (item && item.due_date) refreshLists();
  }

  async function handleReorderItem(itemId, position) {
    setItems((prev) => {
      const next = prev.map((i) => (i.id === itemId ? { ...i, position } : i));
      // Same shape as the server's own ORDER BY (done, position).
      return [...next].sort((a, b) => (a.done !== b.done ? (a.done ? 1 : -1) : a.position - b.position));
    });
    await updateTodoItem(itemId, { position });
  }

  function handleItemDragStart(e, itemId) {
    e.dataTransfer.setData('text/plain', String(itemId));
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDropOnItem(e, targetItem) {
    e.preventDefault();
    e.stopPropagation();
    setDragOverItemId(null);
    const draggedId = Number(e.dataTransfer.getData('text/plain'));
    if (draggedId === targetItem.id) return;

    const siblings = items.filter((i) => i.id !== draggedId);
    const targetIndex = siblings.findIndex((i) => i.id === targetItem.id);
    const prevSibling = siblings[targetIndex - 1];
    const newPosition =
      prevSibling && prevSibling.done === targetItem.done
        ? (prevSibling.position + targetItem.position) / 2
        : targetItem.position - 1;
    handleReorderItem(draggedId, newPosition);
  }

  function handleDropAtEndOfItems(e) {
    e.preventDefault();
    setDragOverItemId(null);
    const draggedId = Number(e.dataTransfer.getData('text/plain'));
    const last = items[items.length - 1];
    if (!last || draggedId === last.id) return;
    handleReorderItem(draggedId, last.position + 1);
  }

  const activeList = lists.find((l) => l.id === activeId);

  return (
    <div style={{ flex: 1, display: 'flex', minWidth: 0 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar title="Todo" subtitle={activeList ? activeList.name : undefined} onOpenDrawer={onOpenDrawer}>
          {isMobile && (
            <button
              onClick={() => setPickerOpen(true)}
              aria-label="Open lists"
              style={{
                marginLeft: 'auto',
                width: 34,
                height: 34,
                flexShrink: 0,
                borderRadius: 8,
                background: 'transparent',
                border: '1px solid var(--accent-glow)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 4h12M2 8h12M2 12h8" stroke="var(--accent)" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </TopBar>

        {!activeList ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13, padding: 24, textAlign: 'center' }}>
            {lists.length === 0 ? 'No lists yet — create one to get started.' : 'Pick a list.'}
          </div>
        ) : (
          <div style={{ flex: 1, minHeight: 0, padding: isMobile ? 14 : 24, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
            <form onSubmit={handleAddItem} style={{ display: 'flex', gap: 8 }}>
              <input
                value={newItemText}
                onChange={(e) => setNewItemText(e.target.value)}
                placeholder="Add an item..."
                style={{ flex: 1, background: 'var(--panel-2)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '10px 12px', fontSize: 14 }}
              />
              <button
                type="submit"
                style={{ background: 'var(--accent)', color: 'var(--accent-text)', border: 'none', borderRadius: 8, padding: '0 18px', fontSize: 14, fontWeight: 600, boxShadow: '0 0 14px var(--accent-glow)' }}
              >
                Add
              </button>
            </form>

            {items.some((i) => i.done) && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-dim)', alignSelf: 'flex-start' }}>
                <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
                Hide done
              </label>
            )}

            {items.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Nothing on this list yet.</div>}
            <div
              style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0 }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDropAtEndOfItems}
            >
              {(hideDone ? items.filter((i) => !i.done) : items).map((item) => (
                <TodoItemRow
                  key={item.id}
                  item={item}
                  onToggle={handleToggle}
                  onUpdate={handleUpdateItem}
                  onDelete={handleDeleteItem}
                  onDragStart={handleItemDragStart}
                  isDragOver={dragOverItemId === item.id}
                  onDragOverRow={(e) => {
                    e.preventDefault();
                    if (dragOverItemId !== item.id) setDragOverItemId(item.id);
                  }}
                  onDragLeaveRow={() => setDragOverItemId((id) => (id === item.id ? null : id))}
                  onDropOnRow={(e) => handleDropOnItem(e, item)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <ListPicker
        lists={lists}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={handleCreateList}
        onRename={handleRenameList}
        onReorder={handleReorderList}
        onDelete={handleDeleteList}
        isMobile={isMobile}
        mobileOpen={pickerOpen}
        onMobileClose={() => setPickerOpen(false)}
      />
    </div>
  );
}
