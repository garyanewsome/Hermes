import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { listNotes, createNote, updateNote, deleteNote } from '../api.js';

const SAVE_DEBOUNCE_MS = 600;

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

function noteTitle(content) {
  const firstLine = (content || '').split('\n').find((line) => line.trim());
  return firstLine ? firstLine.trim() : 'Untitled note';
}

function notePreview(content) {
  const lines = (content || '').split('\n').map((l) => l.trim()).filter(Boolean);
  return lines.slice(1).join(' ');
}

function ConfirmDeleteNote({ onCancel, onConfirm }) {
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
          width: 320,
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
        <div style={{ fontSize: 14, color: 'var(--text)' }}>Delete this note? This can't be undone.</div>
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

function NoteList({ notes, activeId, onSelect, onCreate, onDelete, isMobile, mobileOpen, onMobileClose }) {
  const [search, setSearch] = useState('');
  const [confirmingDeleteId, setConfirmingDeleteId] = useState(null);

  if (isMobile && !mobileOpen) return null;

  const filtered = search.trim()
    ? notes.filter((n) => (n.content || '').toLowerCase().includes(search.trim().toLowerCase()))
    : notes;

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
                width: 'min(300px, 85vw)',
                background: 'var(--panel)',
                borderLeft: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
                zIndex: 41,
                paddingTop: 'env(safe-area-inset-top)',
              }
            : {
                width: 260,
                flexShrink: 0,
                background: 'var(--panel)',
                borderLeft: '1px solid var(--border)',
                display: 'flex',
                flexDirection: 'column',
              }
        }
      >
        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button
            onClick={async () => {
              const note = await onCreate();
              onSelect(note.id);
              if (isMobile) onMobileClose();
            }}
            style={{
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
            + New note
          </button>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search notes..."
            style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '7px 10px', fontSize: 13 }}
          />
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {filtered.length === 0 && (
            <div style={{ padding: '10px', fontSize: 12, color: 'var(--text-faint)' }}>
              {notes.length === 0 ? 'No notes yet.' : 'No matches.'}
            </div>
          )}
          {filtered.map((note) => (
            <div
              key={note.id}
              onClick={() => {
                onSelect(note.id);
                if (isMobile) onMobileClose();
              }}
              style={{
                padding: '10px 10px',
                borderRadius: 8,
                cursor: 'pointer',
                marginBottom: 2,
                background: note.id === activeId ? 'rgba(255,255,255,0.06)' : 'transparent',
                boxShadow: note.id === activeId ? 'inset 2px 0 0 var(--accent)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <div
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 13.5,
                    fontWeight: 600,
                    color: note.id === activeId ? 'var(--text)' : '#c7c8cc',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    fontStyle: noteTitle(note.content) === 'Untitled note' ? 'italic' : 'normal',
                  }}
                >
                  {noteTitle(note.content)}
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmingDeleteId(note.id);
                  }}
                  aria-label="Delete note"
                  title="Delete note"
                  style={{ flexShrink: 0, width: 16, height: 16, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
              {notePreview(note.content) && (
                <div style={{ fontSize: 12, color: 'var(--text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {notePreview(note.content)}
                </div>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>{timeAgo(note.updated_at)}</div>
            </div>
          ))}
        </div>
      </div>

      {confirmingDeleteId != null && (
        <ConfirmDeleteNote
          onCancel={() => setConfirmingDeleteId(null)}
          onConfirm={() => {
            onDelete(confirmingDeleteId);
            setConfirmingDeleteId(null);
          }}
        />
      )}
    </>
  );
}

export default function NotesView({ onOpenDrawer }) {
  const [notes, setNotes] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [draft, setDraft] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const isMobile = useIsMobile();
  const saveTimerRef = useRef(null);

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    const fetched = await listNotes();
    setNotes(fetched);
    setActiveId((current) => {
      if (current != null && fetched.some((n) => n.id === current)) return current;
      return fetched[0]?.id ?? null;
    });
  }

  useEffect(() => {
    const note = notes.find((n) => n.id === activeId);
    setDraft(note ? note.content : '');
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  function flushSave(id, content) {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (id == null) return;
    updateNote(id, content);
    setNotes((prev) => {
      const updated = prev.map((n) => (n.id === id ? { ...n, content, updated_at: new Date().toISOString() } : n));
      return [...updated].sort((a, b) => (a.id === id ? -1 : b.id === id ? 1 : 0));
    });
  }

  function handleSelect(id) {
    flushSave(activeId, draft);
    setActiveId(id);
  }

  function handleChange(e) {
    const content = e.target.value;
    setDraft(content);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => flushSave(activeId, content), SAVE_DEBOUNCE_MS);
  }

  async function handleCreate() {
    flushSave(activeId, draft);
    const note = await createNote();
    setNotes((prev) => [note, ...prev]);
    return note;
  }

  async function handleDelete(id) {
    if (saveTimerRef.current && id === activeId) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    setNotes((prev) => prev.filter((n) => n.id !== id));
    if (activeId === id) setActiveId(null);
    await deleteNote(id);
  }

  const activeNote = notes.find((n) => n.id === activeId);

  return (
    <div style={{ flex: 1, display: 'flex', minWidth: 0 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar title="Notes" subtitle={activeNote ? timeAgo(activeNote.updated_at) : undefined} onOpenDrawer={onOpenDrawer}>
          {isMobile && (
            <button
              onClick={() => setPickerOpen(true)}
              aria-label="Open notes list"
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
                <rect x="2" y="2" width="12" height="12" rx="2" stroke="var(--accent)" strokeWidth="1.4" />
                <path d="M4.5 5.5h7M4.5 8h7M4.5 10.5h4" stroke="var(--accent)" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </TopBar>

        {!activeNote ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13, padding: 24, textAlign: 'center' }}>
            {notes.length === 0 ? 'No notes yet — create one to get started.' : 'Pick a note.'}
          </div>
        ) : (
          <textarea
            value={draft}
            onChange={handleChange}
            placeholder="Start typing..."
            style={{
              flex: 1,
              background: 'var(--bg)',
              border: 'none',
              color: 'var(--accent)',
              padding: isMobile ? 16 : 28,
              fontSize: 15,
              lineHeight: 1.6,
              resize: 'none',
              fontFamily: 'inherit',
              outline: 'none',
            }}
          />
        )}
      </div>

      <NoteList
        notes={notes}
        activeId={activeId}
        onSelect={handleSelect}
        onCreate={handleCreate}
        onDelete={handleDelete}
        isMobile={isMobile}
        mobileOpen={pickerOpen}
        onMobileClose={() => setPickerOpen(false)}
      />
    </div>
  );
}
