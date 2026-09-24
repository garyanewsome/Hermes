import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import ConversationSidebar from './ConversationSidebar.jsx';
import { deleteMessage, getConversation, getModels, listConversations, uploadAttachment } from '../api.js';
import { renderMarkdown } from '../lib/markdown.js';
import useIsMobile from '../hooks/useIsMobile.js';

function TrashIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2.5 3.5h7M4.5 3.5V2.5a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1M4 3.5l.4 6a1 1 0 0 0 1 .9h1.2a1 1 0 0 0 1-.9l.4-6" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M8.3 1.7l2 2L4 10H2v-2l6.3-6.3z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M9.8 5.5A3.8 3.8 0 1 1 8.6 2.9M9.8 1.7v2.6H7.2" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M3 1.5h5l3 3v8a.5.5 0 0 1-.5.5h-7a.5.5 0 0 1-.5-.5v-10a.5.5 0 0 1 .5-.5z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
      <path d="M8 1.5v3h3" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    </svg>
  );
}

function AttachIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M11 5.5l-4.8 4.8a2 2 0 1 1-2.8-2.8l5.3-5.3a3.2 3.2 0 1 1 4.5 4.5l-5.4 5.4a1.2 1.2 0 0 1-1.7-1.7l4.6-4.6" stroke="var(--accent)" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MsgActionButton({ onClick, label, children }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="msg-action-btn"
      style={{ color: 'var(--text-dim)' }}
    >
      {children}
    </button>
  );
}

const LAST_CONVERSATION_KEY = 'hermes:lastConversationId';

export default function ChatView({ onOpenDrawer }) {
  const [conversations, setConversations] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [messages, setMessages] = useState([]); // { id, role, content, pending }
  const [models, setModels] = useState([]);
  const [model, setModel] = useState('');
  const [think, setThink] = useState(false);
  const [input, setInput] = useState('');
  const [generating, setGenerating] = useState(false);
  const [convSidebarOpen, setConvSidebarOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [attachments, setAttachments] = useState([]); // pending, not-yet-sent: [{path, mime_type, filename}]
  const [uploading, setUploading] = useState(false);
  const isMobile = useIsMobile();

  const abortRef = useRef(null);
  const fileInputRef = useRef(null);
  const messagesRef = useRef(null);
  const currentIdRef = useRef(null);
  currentIdRef.current = currentId;

  useEffect(() => {
    getModels()
      .then((list) => {
        setModels(list);
        if (list.includes('gemma4:12b')) setModel('gemma4:12b');
      })
      .catch(() => setModels([]));

    // Resume the last-open conversation on a fresh page load, rather than
    // always landing on an empty new chat — but only if it still exists
    // (it may have been deleted since, from this device or another).
    // localStorage, not sessionStorage: "resume where we left off" should
    // survive closing the tab entirely, not just a same-tab refresh.
    let savedId = null;
    try {
      savedId = localStorage.getItem(LAST_CONVERSATION_KEY);
    } catch {
      // Private-browsing / storage-blocked — fine, just start fresh.
    }
    listConversations().then((list) => {
      setConversations(list);
      if (savedId && list.some((c) => c.id === savedId)) {
        selectConversation(savedId);
      }
    });
  }, []);

  useEffect(() => {
    try {
      if (currentId) localStorage.setItem(LAST_CONVERSATION_KEY, currentId);
      else localStorage.removeItem(LAST_CONVERSATION_KEY);
    } catch {
      // Same as above — non-fatal if storage isn't available.
    }
  }, [currentId]);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages]);

  async function refreshConversations() {
    setConversations(await listConversations());
  }

  async function selectConversation(id) {
    const data = await getConversation(id);
    if (!data) return;
    setCurrentId(id);
    setMessages(data.messages.map((m) => ({ ...m, pending: false })));
    refreshConversations();
  }

  function newChat() {
    setCurrentId(null);
    setMessages([]);
    refreshConversations();
  }

  // The shared core behind sending a new message, regenerating, and
  // edit-and-resend — all three POST to a streaming ndjson endpoint and
  // want identical handling: stall/abort recovery, incremental token
  // rendering into the last message slot, and final persistence. Assumes
  // the caller already appended a pending assistant placeholder as the
  // last element of `messages` before calling this.
  async function runStream(url, body) {
    setGenerating(true);

    const controller = new AbortController();
    abortRef.current = controller;
    let fullText = '';
    let conversationId = currentIdRef.current;

    // A stalled connection here — no bytes at all, for any reason (a dead
    // keep-alive connection from a long-idle tab, the backend pod
    // mid-restart, a genuinely hung Ollama call) — otherwise hangs
    // forever with "thinking..." on screen and no recovery but a manual
    // refresh, since a streaming response never resolves on its own the
    // way a normal fetch does. Reset on every chunk received, so an
    // actively-streaming (just slow) reply is never cut off.
    const STALL_TIMEOUT_MS = 45000;
    let timedOut = false;
    let stallTimer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, STALL_TIMEOUT_MS);
    function resetStallTimer() {
      clearTimeout(stallTimer);
      stallTimer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, STALL_TIMEOUT_MS);
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      resetStallTimer();
      if (response.status === 401) {
        window.dispatchEvent(new Event('hermes:unauthorized'));
        throw new Error('Not logged in');
      }
      if (!response.ok) throw new Error('Request failed: ' + response.status);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        resetStallTimer();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);

          if (event.type === 'conversation_id') {
            conversationId = event.conversation_id;
            setCurrentId(event.conversation_id);
          } else if (event.type === 'token') {
            fullText += event.content;
            const snapshot = fullText;
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], role: 'assistant', content: snapshot, pending: false };
              return next;
            });
          }
        }
      }

      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], role: 'assistant', content: fullText, pending: false };
        return next;
      });
      refreshConversations();
      // The placeholder in `messages` has no real id (the streaming
      // protocol only ever confirms conversation_id, not per-message
      // ids) — re-fetch from the server so delete/edit/regenerate on
      // this exchange has a real id to target, without needing every
      // reply to carry one through the stream itself.
      if (conversationId) {
        const data = await getConversation(conversationId);
        if (data) setMessages(data.messages.map((m) => ({ ...m, pending: false })));
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        const suffix = timedOut ? '\n\n*(connection stalled — try again)*' : '\n\n*(stopped)*';
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], role: 'assistant', content: fullText + suffix, pending: false };
          return next;
        });
      } else {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], role: 'assistant', content: 'Something went wrong: ' + err.message, pending: false };
          return next;
        });
      }
    } finally {
      clearTimeout(stallTimer);
      setGenerating(false);
      abortRef.current = null;
    }
  }

  async function handleFilesSelected(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = ''; // lets the same file be picked again later
    if (!files.length) return;
    setUploading(true);
    try {
      const uploaded = await Promise.all(files.map(uploadAttachment));
      setAttachments((prev) => [...prev, ...uploaded]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Attachment upload failed: ' + err.message }]);
    } finally {
      setUploading(false);
    }
  }

  function removeAttachment(path) {
    setAttachments((prev) => prev.filter((a) => a.path !== path));
  }

  async function handleSubmit(e) {
    e.preventDefault();

    if (generating) {
      abortRef.current?.abort();
      return;
    }

    const text = input.trim();
    if (!text && attachments.length === 0) return;
    setInput('');
    const sentAttachments = attachments;
    setAttachments([]);

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, attachments: sentAttachments },
      { role: 'assistant', content: 'thinking...', pending: true },
    ]);

    await runStream('/chat', {
      message: text,
      conversation_id: currentId,
      model: model || null,
      think,
      attachments: sentAttachments,
    });
  }

  async function handleDeleteMessage(messageId) {
    setMessages((prev) => prev.filter((m) => m.id !== messageId));
    if (currentId) await deleteMessage(currentId, messageId);
  }

  function startEdit(m) {
    setEditingId(m.id);
    setEditText(m.content);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditText('');
  }

  async function submitEdit(messageId) {
    const text = editText.trim();
    setEditingId(null);
    if (!text || generating) return;

    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === messageId);
      if (idx === -1) return prev;
      return [
        ...prev.slice(0, idx),
        { ...prev[idx], content: text },
        { role: 'assistant', content: 'thinking...', pending: true },
      ];
    });

    await runStream(`/conversations/${currentId}/messages/${messageId}/resend`, {
      content: text,
      model: model || null,
      think,
    });
  }

  async function handleRegenerate(messageId) {
    if (generating) return;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === messageId);
      if (idx === -1) return prev;
      return [...prev.slice(0, idx), { role: 'assistant', content: 'thinking...', pending: true }];
    });

    await runStream(`/conversations/${currentId}/messages/${messageId}/resend`, {
      model: model || null,
      think,
    });
  }

  return (
    <div style={{ flex: 1, display: 'flex', minWidth: 0 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar title="Hermes" onOpenDrawer={onOpenDrawer}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 13, color: 'var(--text-dim)' }}>
            <input type="checkbox" checked={think} onChange={(e) => setThink(e.target.checked)} />
            Thinking
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{ background: 'var(--panel)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 8, padding: '5px 10px', fontSize: 13 }}
          >
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          {isMobile && (
            <button
              onClick={() => setConvSidebarOpen(true)}
              aria-label="Open conversations"
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
                <path d="M2 3h12v8H6l-3 3v-3H2z" stroke="var(--accent)" strokeWidth="1.4" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </TopBar>

        <div ref={messagesRef} style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '14px 12px' : 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {messages.map((m, i) => {
            const isEditing = m.id != null && editingId === m.id;
            return (
              <div
                key={m.id ?? `pending-${i}`}
                className="msg-row"
                style={{ display: 'flex', flexDirection: 'column', maxWidth: isMobile ? '88%' : '70%', alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start' }}
              >
                {m.attachments?.length > 0 && (
                  <div
                    style={{
                      display: 'flex',
                      gap: 6,
                      flexWrap: 'wrap',
                      marginBottom: 6,
                      alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                    }}
                  >
                    {m.attachments.map((a) =>
                      a.kind === 'document' ? (
                        <div
                          key={a.path}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            padding: '6px 10px',
                            borderRadius: 8,
                            border: '1px solid var(--border)',
                            background: 'var(--panel-2)',
                            color: 'var(--text-dim)',
                            fontSize: 12,
                          }}
                        >
                          <DocumentIcon />
                          {a.filename || a.original_filename}
                        </div>
                      ) : (
                        <img
                          key={a.path}
                          src={`/uploads/${a.path}`}
                          alt={a.filename || a.original_filename || 'attachment'}
                          style={{ maxWidth: 200, maxHeight: 200, borderRadius: 10, border: '1px solid var(--border)', display: 'block' }}
                        />
                      )
                    )}
                  </div>
                )}
                {isEditing ? (
                  <textarea
                    autoFocus
                    rows={Math.min(8, Math.max(2, editText.split('\n').length))}
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitEdit(m.id); }
                      if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); }
                    }}
                    style={{
                      padding: '10px 14px',
                      borderRadius: 14,
                      lineHeight: 1.45,
                      fontSize: 14.5,
                      fontFamily: 'inherit',
                      color: 'var(--accent-text)',
                      background: 'var(--accent)',
                      border: '1px solid var(--accent)',
                      resize: 'vertical',
                      boxShadow: '0 0 10px var(--accent-glow)',
                    }}
                  />
                ) : (
                  m.content && (
                    <div
                      className="msg-bubble"
                      style={{
                        padding: '10px 14px',
                        borderRadius: 14,
                        lineHeight: 1.45,
                        fontSize: 14.5,
                        whiteSpace: m.role === 'user' || m.pending ? 'pre-wrap' : 'normal',
                        fontStyle: m.pending ? 'italic' : 'normal',
                        color: m.pending ? 'var(--text-dim)' : m.role === 'user' ? 'var(--accent-text)' : 'var(--text)',
                        background: m.role === 'user' ? 'var(--accent)' : 'var(--panel-2)',
                        border: m.role === 'assistant' ? '1px solid var(--accent)' : 'none',
                        boxShadow: m.role === 'user' || m.role === 'assistant' ? '0 0 10px var(--accent-glow)' : 'none',
                      }}
                      {...(m.role === 'assistant' && !m.pending
                        ? { dangerouslySetInnerHTML: { __html: renderMarkdown(m.content) } }
                        : { children: m.content })}
                    />
                  )
                )}
                {m.id != null && !m.pending && !isEditing && (
                  <div
                    className={`msg-actions${isMobile ? ' always-visible' : ''}`}
                    style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start' }}
                  >
                    {m.role === 'user' && (
                      <MsgActionButton label="Edit and resend" onClick={() => startEdit(m)}>
                        <EditIcon />
                      </MsgActionButton>
                    )}
                    {m.role === 'assistant' && (
                      <MsgActionButton label="Regenerate this response" onClick={() => handleRegenerate(m.id)}>
                        <RetryIcon />
                      </MsgActionButton>
                    )}
                    <MsgActionButton label="Delete message" onClick={() => handleDeleteMessage(m.id)}>
                      <TrashIcon />
                    </MsgActionButton>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div
          style={{
            padding: `${attachments.length ? 12 : 0}px ${isMobile ? 12 : 20}px 0`,
            borderTop: attachments.length ? '1px solid var(--border)' : 'none',
            background: 'var(--panel)',
          }}
        >
          {attachments.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', paddingBottom: 12 }}>
              {attachments.map((a) =>
                a.kind === 'document' ? (
                  <div
                    key={a.path}
                    style={{
                      position: 'relative',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      maxWidth: 160,
                      padding: '6px 22px 6px 10px',
                      borderRadius: 8,
                      border: '1px solid var(--border)',
                      background: 'var(--panel-2)',
                      color: 'var(--text-dim)',
                      fontSize: 12,
                    }}
                  >
                    <DocumentIcon />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.filename}</span>
                    <button
                      type="button"
                      onClick={() => removeAttachment(a.path)}
                      aria-label="Remove attachment"
                      title="Remove attachment"
                      style={{
                        position: 'absolute',
                        top: -6,
                        right: -6,
                        width: 18,
                        height: 18,
                        borderRadius: '50%',
                        background: 'var(--bg)',
                        border: '1px solid var(--border-strong)',
                        color: 'var(--text-dim)',
                        fontSize: 11,
                        padding: 0,
                        lineHeight: 1,
                      }}
                    >
                      ×
                    </button>
                  </div>
                ) : (
                  <div key={a.path} style={{ position: 'relative', width: 56, height: 56, flexShrink: 0 }}>
                    <img
                      src={`/uploads/${a.path}`}
                      alt={a.filename}
                      style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 8, border: '1px solid var(--border)' }}
                    />
                    <button
                      type="button"
                      onClick={() => removeAttachment(a.path)}
                      aria-label="Remove attachment"
                      title="Remove attachment"
                      style={{
                        position: 'absolute',
                        top: -6,
                        right: -6,
                        width: 18,
                        height: 18,
                        borderRadius: '50%',
                        background: 'var(--bg)',
                        border: '1px solid var(--border-strong)',
                        color: 'var(--text-dim)',
                        fontSize: 11,
                        padding: 0,
                        lineHeight: 1,
                      }}
                    >
                      ×
                    </button>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'flex-end',
            padding: `16px ${isMobile ? 12 : 20}px calc(16px + env(safe-area-inset-bottom))`,
            borderTop: attachments.length ? 'none' : '1px solid var(--border)',
            background: 'var(--panel)',
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif,.pdf,.txt,.md,application/pdf,text/plain,text/markdown"
            multiple
            onChange={handleFilesSelected}
            style={{ display: 'none' }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            aria-label="Attach image or document"
            title="Attach image or document"
            style={{
              flexShrink: 0,
              width: 40,
              height: 40,
              borderRadius: 10,
              background: 'transparent',
              border: '1px solid var(--border-strong)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              opacity: uploading ? 0.5 : 1,
            }}
          >
            <AttachIcon />
          </button>
          <textarea
            rows={1}
            value={input}
            placeholder="Ask something..."
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form.requestSubmit();
              }
            }}
            style={{
              flex: 1,
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              color: 'var(--text)',
              borderRadius: 10,
              padding: '10px 14px',
              fontSize: 14.5,
              resize: 'none',
              fontFamily: 'inherit',
            }}
          />
          <button
            type="submit"
            style={{
              background: generating ? '#ff4d4d' : 'var(--accent)',
              color: generating ? 'white' : 'var(--accent-text)',
              border: 'none',
              borderRadius: 10,
              padding: '0 20px',
              fontSize: 14.5,
              boxShadow: generating ? '0 0 14px rgba(255,77,77,0.5)' : '0 0 14px var(--accent-glow)',
            }}
          >
            {generating ? 'Stop' : 'Send'}
          </button>
        </form>
      </div>
      <ConversationSidebar
        conversations={conversations}
        currentId={currentId}
        onSelect={selectConversation}
        onNewChat={newChat}
        onChanged={refreshConversations}
        mobileOpen={convSidebarOpen}
        onMobileClose={() => setConvSidebarOpen(false)}
      />
    </div>
  );
}
