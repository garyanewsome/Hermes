import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { ITEMS, arrange } from '../components/NavDrawer.jsx';
import { getNavOrder, saveNavOrder } from '../api.js';
import { card, dim, outline } from './workoutStyles.js';

function MoveButton({ label, disabled, onClick, down }) {
  return (
    <button type="button" aria-label={label} disabled={disabled} onClick={onClick} style={{ ...outline, width: 40, height: 36, padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: disabled ? 0.3 : 1 }}>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" style={{ transform: down ? 'rotate(180deg)' : 'none' }}>
        <path d="M2.5 9L7 4.5 11.5 9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

function MenuOrder({ active }) {
  const [order, setOrder] = useState(null);
  const [error, setError] = useState('');
  // Saves run one after another, so quick taps can't land out of order.
  const saving = useRef(Promise.resolve());

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    saving.current
      .then(getNavOrder)
      .then((next) => current && (setOrder(next), setError('')))
      .catch(() => current && setError('Couldn’t load the order.'));
    return () => {
      current = false;
    };
  }, [active]);

  function save(next) {
    setOrder(next);
    setError('');
    saving.current = saving.current.then(() => saveNavOrder(next)).catch(() => setError('Couldn’t save the order.'));
  }

  // Not shown until loaded, so a tap can't overwrite the saved order with
  // the default one.
  const items = order && arrange(ITEMS.filter((item) => !item.pinned), order);

  function move(index, by) {
    const keys = items.map((item) => item.key);
    [keys[index], keys[index + by]] = [keys[index + by], keys[index]];
    save(keys);
  }

  return (
    <section style={{ ...card, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Menu order</h2>
      <div style={dim}>Today stays at the top; Settings and System at the bottom. Saved for all your devices.</div>
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      {!items && !error && <div style={dim}>Loading…</div>}
      {items?.map((item, index) => (
        <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
          {item.icon('#c7c8cc')}
          <span style={{ marginRight: 'auto', marginLeft: 4 }}>{item.label}</span>
          <MoveButton label={`Move ${item.label} up`} disabled={index === 0} onClick={() => move(index, -1)} />
          <MoveButton label={`Move ${item.label} down`} disabled={index === items.length - 1} onClick={() => move(index, 1)} down />
        </div>
      ))}
      {order?.length > 0 && (
        <button type="button" onClick={() => save([])} style={{ ...outline, alignSelf: 'flex-start', marginTop: 4 }}>
          Reset to default
        </button>
      )}
    </section>
  );
}

export default function SettingsView({ onOpenDrawer, active }) {
  const isMobile = useIsMobile();
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Settings" onOpenDrawer={onOpenDrawer} />
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: isMobile ? 14 : 24 }}>
        <div style={{ maxWidth: 480, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <MenuOrder active={active} />
        </div>
      </div>
    </div>
  );
}
