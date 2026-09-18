import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import ConversationSidebar from './ConversationSidebar.jsx';
import { getConversation, getModels, listConversations } from '../api.js';
import { renderMarkdown } from '../lib/markdown.js';
import useIsMobile from '../hooks/useIsMobile.js';

export default function ChatView({ onOpenDrawer }) {
  const [conversations, setConversations] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [messages, setMessages] = useState([]); // { role, content, pending }
  const [models, setModels] = useState([]);
  const [model, setModel] = useState('');
  const [think, setThink] = useState(false);
  const [input, setInput] = useState('');
  const [generating, setGenerating] = useState(false);
  const [convSidebarOpen, setConvSidebarOpen] = useState(false);
  const isMobile = useIsMobile();

  const abortRef = useRef(null);
  const messagesRef = useRef(null);

  useEffect(() => {
    getModels()
      .then((list) => {
        setModels(list);
        if (list.includes('qwen3:14b')) setModel('qwen3:14b');
      })
      .catch(() => setModels([]));
    refreshConversations();
  }, []);

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

  async function handleSubmit(e) {
    e.preventDefault();

    if (generating) {
      abortRef.current?.abort();
      return;
    }

    const text = input.trim();
    if (!text) return;
    setInput('');
    setGenerating(true);

    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: 'thinking...', pending: true }]);

    const controller = new AbortController();
    abortRef.current = controller;
    let fullText = '';
    let gotFirstToken = false;
    let conversationId = currentId;

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, conversation_id: currentId, model: model || null, think }),
        signal: controller.signal,
      });
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
            gotFirstToken = true;
            fullText += event.content;
            const snapshot = fullText;
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { role: 'assistant', content: snapshot, pending: false };
              return next;
            });
          }
        }
      }

      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: fullText, pending: false };
        return next;
      });
      refreshConversations();
    } catch (err) {
      if (err.name === 'AbortError') {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: fullText + '\n\n*(stopped)*', pending: false };
          return next;
        });
      } else {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: 'assistant', content: 'Something went wrong: ' + err.message, pending: false };
          return next;
        });
      }
    } finally {
      setGenerating(false);
      abortRef.current = null;
    }
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
          {messages.map((m, i) => (
            <div
              key={i}
              className="msg-bubble"
              style={{
                maxWidth: isMobile ? '88%' : '70%',
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
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
          ))}
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            display: 'flex',
            gap: 10,
            padding: `16px ${isMobile ? 12 : 20}px calc(16px + env(safe-area-inset-bottom))`,
            borderTop: '1px solid var(--border)',
            background: 'var(--panel)',
          }}
        >
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
