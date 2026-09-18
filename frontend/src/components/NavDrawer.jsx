const ITEMS = [
  {
    key: 'chat',
    label: 'Chat',
    icon: (color) => (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M2 3h12v8H6l-3 3v-3H2z" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    key: 'tasks',
    label: 'Tasks',
    icon: (color) => (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="2" width="5" height="5" stroke={color} strokeWidth="1.4" />
        <rect x="9" y="2" width="5" height="5" stroke={color} strokeWidth="1.4" />
        <rect x="2" y="9" width="5" height="5" stroke={color} strokeWidth="1.4" />
        <rect x="9" y="9" width="5" height="5" stroke={color} strokeWidth="1.4" />
      </svg>
    ),
  },
  {
    key: 'habits',
    label: 'Habits',
    icon: (color) => (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path
          d="M8 1c1 2.5-1 3.2-1 5.2A2.8 2.8 0 0 0 8 12a2.6 2.6 0 0 0 1.6-4.7c1.4 1 1.9 2.2 1.4 3.7A4 4 0 0 1 4 9.5C4 6.7 6.5 5.5 8 1z"
          stroke={color}
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

export default function NavDrawer({ open, activeView, onNavigate, onClose }) {
  if (!open) return null;
  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 40 }} />
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          bottom: 0,
          width: 'min(280px, 85vw)',
          background: 'var(--panel)',
          borderRight: '1px solid var(--border)',
          padding: 'max(20px, env(safe-area-inset-top)) 0 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          zIndex: 41,
        }}
      >
        <div style={{ padding: '0 20px 16px', fontSize: 12, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Views
        </div>
        {ITEMS.map((item) => {
          const active = item.key === activeView;
          const color = active ? 'var(--accent)' : '#c7c8cc';
          return (
            <button
              key={item.key}
              onClick={() => {
                onNavigate(item.key);
                onClose();
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 20px',
                background: active ? 'var(--accent-wash)' : 'transparent',
                borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
                borderTop: 'none',
                borderRight: 'none',
                borderBottom: 'none',
                color,
                fontSize: 14,
                fontWeight: active ? 600 : 400,
                textAlign: 'left',
              }}
            >
              {item.icon(color)}
              {item.label}
            </button>
          );
        })}
      </div>
    </>
  );
}
