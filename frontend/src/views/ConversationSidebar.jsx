import { useEffect, useState } from 'react';
import { deleteConversation, renameConversation } from '../api.js';

export default function ConversationSidebar({ conversations, currentId, onSelect, onNewChat, onChanged }) {
  const [menu, setMenu] = useState(null); // { x, y, conv }
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState('');

  useEffect(() => {
    const hide = () => setMenu(null);
    document.addEventListener('click', hide);
    document.addEventListener('scroll', hide, true);
    return () => {
      document.removeEventListener('click', hide);
      document.removeEventListener('scroll', hide, true);
    };
  }, []);

  async function commitRename(conv) {
    const title = renameValue.trim();
    setRenamingId(null);
    if (title && title !== conv.title) {
      await renameConversation(conv.id, title);
      onChanged();
    }
  }

  async function handleDelete(conv) {
    if (!confirm("Delete this conversation? This can't be undone.")) return;
    await deleteConversation(conv.id);
    onChanged();
  }

  return (
    <div
      style={{
        width: 240,
        flexShrink: 0,
        background: 'var(--panel)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <button
        onClick={onNewChat}
        style={{
          margin: 12,
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
        + New chat
      </button>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
        {conversations.map((conv) => (
          <div key={conv.id}>
            {renamingId === conv.id ? (
              <input
                autoFocus
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onBlur={() => commitRename(conv)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { e.preventDefault(); commitRename(conv); }
                  if (e.key === 'Escape') { e.preventDefault(); setRenamingId(null); }
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                  border: '1px solid var(--accent)',
                  borderRadius: 5,
                  padding: '2px 6px',
                  fontSize: 13,
                  fontFamily: 'inherit',
                  outline: 'none',
                  margin: '0 0 2px',
                }}
              />
            ) : (
              <div
                onClick={() => onSelect(conv.id)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu({ x: e.clientX, y: e.clientY, conv });
                }}
                style={{
                  padding: '9px 10px',
                  borderRadius: 8,
                  fontSize: 13,
                  color: conv.id === currentId ? 'var(--text)' : 'var(--text-dim)',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  marginBottom: 2,
                  background: conv.id === currentId ? 'rgba(255,255,255,0.06)' : 'transparent',
                  boxShadow: conv.id === currentId ? 'inset 2px 0 0 var(--accent)' : 'none',
                }}
              >
                {conv.title}
              </div>
            )}
          </div>
        ))}
      </div>

      {menu && (
        <div
          style={{
            position: 'fixed',
            left: menu.x,
            top: menu.y,
            background: 'var(--panel)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: 4,
            minWidth: 120,
            boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            zIndex: 100,
          }}
        >
          <div
            onClick={() => {
              setRenamingId(menu.conv.id);
              setRenameValue(menu.conv.title);
              setMenu(null);
            }}
            style={{ padding: '7px 12px', borderRadius: 5, fontSize: 13, cursor: 'pointer', color: 'var(--text)' }}
          >
            Rename
          </div>
          <div
            onClick={() => {
              handleDelete(menu.conv);
              setMenu(null);
            }}
            style={{ padding: '7px 12px', borderRadius: 5, fontSize: 13, cursor: 'pointer', color: '#ff6b6b' }}
          >
            Delete
          </div>
        </div>
      )}
    </div>
  );
}
