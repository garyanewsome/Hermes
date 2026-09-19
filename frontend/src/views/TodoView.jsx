import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import {
  listTodoLists,
  createTodoList,
  renameTodoList,
  deleteTodoList,
  listTodoItems,
  createTodoItem,
  updateTodoItem,
  deleteTodoItem,
} from '../api.js';

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

function ListPicker({ lists, activeId, onSelect, onCreate, onRename, onDelete, isMobile, mobileOpen, onMobileClose }) {
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(null);

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

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
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
                    cursor: 'pointer',
                    background: list.id === activeId ? 'rgba(255,255,255,0.06)' : 'transparent',
                    boxShadow: list.id === activeId ? 'inset 2px 0 0 var(--accent)' : 'none',
                  }}
                >
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
                    style={{ flexShrink: 0, width: 18, height: 18, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
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
                    style={{ flexShrink: 0, width: 18, height: 18, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
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

function TodoItemRow({ item, onToggle, onUpdate, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(item.text);
  const [pickingDate, setPickingDate] = useState(false);

  function commitEdit() {
    const trimmed = editValue.trim();
    setEditing(false);
    if (trimmed && trimmed !== item.text) onUpdate(item.id, { text: trimmed });
  }

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: 10,
        background: 'var(--bg)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '10px 12px',
        fontSize: 14,
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
          background: item.done ? 'var(--accent)' : 'transparent',
          border: item.done ? 'none' : '1px solid var(--border-strong)',
          boxShadow: item.done ? '0 0 6px var(--accent-glow)' : 'none',
          padding: 0,
        }}
      />
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
          style={{ flexShrink: 0, background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-faint)', borderRadius: 6, padding: '3px 8px', fontSize: 11 }}
        >
          due {item.due_date}
        </button>
      ) : (
        <button
          onClick={() => setPickingDate(true)}
          aria-label="Set due date"
          title="Set due date"
          style={{ flexShrink: 0, width: 22, height: 22, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
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
          style={{ flexShrink: 0, background: 'transparent', border: 'none', color: 'var(--text-faint)', fontSize: 12, padding: 0 }}
        >
          ×
        </button>
      )}

      <button
        onClick={() => onDelete(item.id)}
        aria-label="Delete item"
        title="Delete item"
        style={{ flexShrink: 0, width: 20, height: 20, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
          <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}

export default function TodoView({ onOpenDrawer }) {
  const [lists, setLists] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [items, setItems] = useState([]);
  const [newItemText, setNewItemText] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const isMobile = useIsMobile();

  useEffect(() => {
    refreshLists();
  }, []);

  useEffect(() => {
    if (activeId != null) refreshItems(activeId);
  }, [activeId]);

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
    await renameTodoList(listId, name);
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
    setItems((prev) => {
      const next = prev.map((i) => (i.id === itemId ? { ...i, done } : i));
      return [...next.filter((i) => !i.done), ...next.filter((i) => i.done)];
    });
    setLists((prev) => prev.map((l) => (l.id === activeId ? { ...l, open_count: (l.open_count || 0) + (done ? -1 : 1) } : l)));
    await updateTodoItem(itemId, { done });
  }

  async function handleUpdateItem(itemId, updates) {
    setItems((prev) => prev.map((i) => (i.id === itemId ? { ...i, ...updates } : i)));
    await updateTodoItem(itemId, updates);
  }

  async function handleDeleteItem(itemId) {
    const item = items.find((i) => i.id === itemId);
    setItems((prev) => prev.filter((i) => i.id !== itemId));
    if (item && !item.done) {
      setLists((prev) => prev.map((l) => (l.id === activeId ? { ...l, open_count: Math.max(0, (l.open_count || 0) - 1) } : l)));
    }
    await deleteTodoItem(itemId);
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

            {items.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>Nothing on this list yet.</div>}
            {items.map((item) => (
              <TodoItemRow key={item.id} item={item} onToggle={handleToggle} onUpdate={handleUpdateItem} onDelete={handleDeleteItem} />
            ))}
          </div>
        )}
      </div>

      <ListPicker
        lists={lists}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={handleCreateList}
        onRename={handleRenameList}
        onDelete={handleDeleteList}
        isMobile={isMobile}
        mobileOpen={pickerOpen}
        onMobileClose={() => setPickerOpen(false)}
      />
    </div>
  );
}
