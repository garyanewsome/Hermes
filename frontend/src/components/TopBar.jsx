export default function TopBar({ title, subtitle, onOpenDrawer, children }) {
  return (
    <div
      style={{
        height: 56,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '0 20px',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <button
        onClick={onOpenDrawer}
        aria-label="Open menu"
        style={{
          width: 40,
          height: 40,
          borderRadius: 8,
          background: 'transparent',
          border: '1px solid var(--accent-glow)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path d="M2 4.5H16M2 9H16M2 13.5H16" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      <div
        style={{
          fontSize: 18,
          fontWeight: 600,
          color: 'var(--accent)',
          letterSpacing: '0.02em',
          textShadow: '0 0 12px var(--accent-glow)',
        }}
      >
        {title}
      </div>
      {subtitle && <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{subtitle}</div>}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>{children}</div>
    </div>
  );
}
