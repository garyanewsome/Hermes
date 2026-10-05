import { useEffect, useLayoutEffect, useRef, useState } from 'react';
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
                width: 290,
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
                padding: '12px 12px',
                borderRadius: 10,
                cursor: 'pointer',
                marginBottom: 3,
                background: note.id === activeId ? 'rgba(255,255,255,0.06)' : 'transparent',
                boxShadow: note.id === activeId ? 'inset 2px 0 0 var(--accent)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <div
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 16.5,
                    fontWeight: 600,
                    color: note.id === activeId ? 'var(--text)' : '#d6d7db',
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
                  style={{ flexShrink: 0, width: 24, height: 24, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                >
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
              {notePreview(note.content) && (
                <div style={{ fontSize: 13.5, color: 'var(--text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 2 }}>
                  {notePreview(note.content)}
                </div>
              )}
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 3 }}>{timeAgo(note.updated_at)}</div>
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

// A note is still one string whose first line is its title (the list, search
// and saving all rely on that) — this just edits it as two fields so the
// title can be styled larger, which a single <textarea> can't do for one line.
function splitNote(content) {
  const i = content.indexOf('\n');
  return i === -1
    ? { title: content, body: '', hasBody: false }
    : { title: content.slice(0, i), body: content.slice(i + 1), hasBody: true };
}

function NoteEditor({ noteId, value, onChange, isMobile }) {
  const titleRef = useRef(null);
  const bodyRef = useRef(null);
  // Where to put the caret once the state change from a key press (Enter,
  // Backspace at the join) has rendered — focus can't move until the new
  // text is actually in the fields.
  const pendingCaret = useRef(null);
  const { title, body, hasBody } = splitNote(value);
  const join = (t, b) => (b === '' ? t : `${t}\n${b}`);

  // Keep the title field exactly as tall as its text (it wraps if long).
  function fitTitle() {
    const el = titleRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }
  useLayoutEffect(fitTitle, [title, isMobile, noteId]);
  useEffect(() => {
    window.addEventListener('resize', fitTitle);
    return () => window.removeEventListener('resize', fitTitle);
  }, []);

  function applyCaret(field, pos) {
    const el = field === 'title' ? titleRef.current : bodyRef.current;
    if (el) {
      el.focus();
      el.setSelectionRange(pos, pos);
    }
  }
  useLayoutEffect(() => {
    const p = pendingCaret.current;
    if (!p) return;
    pendingCaret.current = null;
    applyCaret(p.field, p.pos);
  });

  // Change the content and then put the caret somewhere. When the content
  // genuinely changes, the caret has to wait for the render that puts the new
  // text in the fields (pendingCaret). When it doesn't — an arrow-key hop
  // between the fields, or a Backspace that joins nothing — React won't
  // re-render for an identical value, so a "pending" caret would never be
  // applied and would instead fire on some later unrelated render. Focus
  // right away in that case.
  function commit(newContent, caret) {
    if (newContent === value) {
      applyCaret(caret.field, caret.pos);
      return;
    }
    pendingCaret.current = caret;
    onChange(newContent);
  }

  // A brand-new empty note: start typing straight into the title.
  useEffect(() => {
    if (value === '') titleRef.current?.focus();
  }, [noteId]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleTitleInput(e) {
    const v = e.target.value;
    const nl = v.indexOf('\n');
    if (nl === -1) {
      onChange(hasBody ? `${v}\n${body}` : v);
      return;
    }
    // Multi-line paste into the title: first line stays the title, the rest
    // flows into the body, caret at the end of what was pasted.
    const rest = v.slice(nl + 1);
    commit(`${v.slice(0, nl)}\n${rest}${hasBody ? `\n${body}` : ''}`, { field: 'body', pos: rest.length });
  }

  function handleTitleKeyDown(e) {
    const el = e.target;
    const atEnd = el.selectionStart === title.length && el.selectionEnd === title.length;
    if (e.key === 'Enter') {
      e.preventDefault();
      // Splits the title at the caret; whatever followed it becomes the
      // first line of the body, same as pressing Enter mid-line anywhere.
      const before = title.slice(0, el.selectionStart);
      const after = title.slice(el.selectionEnd);
      commit(`${before}\n${after}${hasBody ? `\n${body}` : ''}`, { field: 'body', pos: 0 });
    } else if (e.key === 'ArrowDown' && atEnd) {
      e.preventDefault();
      applyCaret('body', 0);
    } else if (e.key === 'Delete' && atEnd && hasBody) {
      e.preventDefault();
      commit(title + body, { field: 'title', pos: title.length });
    }
  }

  function handleBodyKeyDown(e) {
    const el = e.target;
    const atStart = el.selectionStart === 0 && el.selectionEnd === 0;
    if (e.key === 'Backspace' && atStart) {
      // Backspace at the very start of the body joins it back onto the title.
      e.preventDefault();
      commit(title + body, { field: 'title', pos: title.length });
    } else if (e.key === 'ArrowUp' && atStart) {
      e.preventDefault();
      applyCaret('title', title.length);
    }
  }

  const sidePad = isMobile ? 16 : 28;
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <textarea
        ref={titleRef}
        rows={1}
        value={title}
        onChange={handleTitleInput}
        onKeyDown={handleTitleKeyDown}
        placeholder="Title"
        aria-label="Note title"
        style={{
          flexShrink: 0,
          maxHeight: '35vh',
          overflowY: 'auto',
          resize: 'none',
          background: 'transparent',
          border: 'none',
          outline: 'none',
          color: 'var(--accent)',
          textShadow: '0 0 14px var(--accent-glow)',
          fontSize: isMobile ? 24 : 28,
          fontWeight: 700,
          lineHeight: 1.25,
          fontFamily: 'inherit',
          padding: `${isMobile ? 18 : 26}px ${sidePad}px 6px`,
        }}
      />
      <textarea
        ref={bodyRef}
        value={body}
        onChange={(e) => onChange(join(title, e.target.value))}
        onKeyDown={handleBodyKeyDown}
        placeholder="Start typing..."
        aria-label="Note body"
        style={{
          flex: 1,
          minHeight: 0,
          resize: 'none',
          background: 'transparent',
          border: 'none',
          outline: 'none',
          color: 'var(--accent)',
          fontSize: isMobile ? 16 : 15,
          lineHeight: 1.6,
          fontFamily: 'inherit',
          padding: `6px ${sidePad}px ${isMobile ? 16 : 28}px`,
        }}
      />
    </div>
  );
}

const POLL_INTERVAL_MS = 20000;

export default function NotesView({ onOpenDrawer }) {
  const [notes, setNotes] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [draft, setDraft] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const isMobile = useIsMobile();
  const saveTimerRef = useRef(null);
  // A ref mirror of activeId — refresh() is called from a setInterval set
  // up once on mount, so its closure would otherwise see activeId frozen
  // at whatever it was on that first render (the classic stale-closure
  // trap for interval callbacks in React), never noticing which note is
  // actually open by the time a later poll fires.
  const activeIdRef = useRef(null);
  activeIdRef.current = activeId;
  // Guards against a poll overwriting what's being typed. The old check
  // ("no save timer pending") ran only AFTER the poll's network round trip,
  // and a save that had already fired but not finished leaves the timer
  // null — so a poll that read the note before that save landed came back
  // with the previous text and replaced the textarea with it, dropping the
  // last few words typed. Now: editSeqRef bumps on every keystroke and on
  // every save start/finish, so any poll that overlapped local activity is
  // thrown away; savesInFlightRef/dirtyRef cover a save still on the wire
  // or one that failed and hasn't been retried.
  const editSeqRef = useRef(0);
  const savesInFlightRef = useRef(0);
  const dirtyRef = useRef(false);
  const typedSeqRef = useRef(0);
  const draftRef = useRef('');
  draftRef.current = draft;

  useEffect(() => {
    refresh();
    // Poll for changes made elsewhere (another device, another tab) —
    // notes jotted down on the phone at the gym used to need a manual
    // page refresh here to show up at all.
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    // Coming back from idle: refresh right away instead of showing whatever
    // was on screen until the next 20s tick.
    window.addEventListener('hermes:wake', refresh);

    // Push out an unsaved edit the moment the tab is hidden or closed —
    // otherwise a refresh/discard inside the 600ms debounce loses it.
    const flushPending = () => {
      if (saveTimerRef.current && activeIdRef.current != null) {
        flushSave(activeIdRef.current, draftRef.current, true);
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flushPending();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', flushPending);
    return () => {
      clearInterval(interval);
      window.removeEventListener('hermes:wake', refresh);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', flushPending);
    };
  }, []);

  async function refresh() {
    const seqAtStart = editSeqRef.current;
    const fetched = await listNotes();
    if (editSeqRef.current !== seqAtStart || savesInFlightRef.current > 0) return;
    setNotes(fetched);

    const currentActiveId = activeIdRef.current;
    const stillExists = currentActiveId != null && fetched.some((n) => n.id === currentActiveId);
    if (!stillExists) {
      setActiveId(fetched[0]?.id ?? null);
    } else if (!saveTimerRef.current && !dirtyRef.current) {
      // Nothing unsaved locally — safe to pick up a remote edit to the note
      // that's currently open.
      const updated = fetched.find((n) => n.id === currentActiveId);
      if (updated && updated.content !== draftRef.current) setDraft(updated.content || '');
    }
  }

  useEffect(() => {
    const note = notes.find((n) => n.id === activeId);
    setDraft(note ? note.content : '');
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  function flushSave(id, content, keepalive = false) {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (id == null) return;
    const typedAt = typedSeqRef.current;
    editSeqRef.current += 1;
    savesInFlightRef.current += 1;
    updateNote(id, content, { keepalive })
      .then(() => {
        // Only "clean" if nothing was typed while this was in flight.
        if (typedSeqRef.current === typedAt) dirtyRef.current = false;
      })
      .catch((err) => {
        // Stay dirty (so polls can't overwrite the unsaved text) and try
        // again shortly instead of silently dropping the edit.
        console.error('Note save failed, will retry', err);
        if (!saveTimerRef.current) saveTimerRef.current = setTimeout(() => flushSave(id, draftRef.current), 3000);
      })
      .finally(() => {
        savesInFlightRef.current -= 1;
        editSeqRef.current += 1;
      });
    setNotes((prev) => {
      const updated = prev.map((n) => (n.id === id ? { ...n, content, updated_at: new Date().toISOString() } : n));
      return [...updated].sort((a, b) => (a.id === id ? -1 : b.id === id ? 1 : 0));
    });
  }

  function handleSelect(id) {
    flushSave(activeId, draft);
    setActiveId(id);
  }

  function handleChange(content) {
    setDraft(content);
    dirtyRef.current = true;
    typedSeqRef.current += 1;
    editSeqRef.current += 1;
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
          <NoteEditor noteId={activeNote.id} value={draft} onChange={handleChange} isMobile={isMobile} />
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
