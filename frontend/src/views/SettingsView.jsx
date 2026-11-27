import { useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { ITEMS, arrange } from '../components/NavDrawer.jsx';
import SortableList from '../components/SortableList.jsx';
import { setNavOrder, useNavOrder } from '../lib/navOrder.js';
import { card, dim, outline } from './workoutStyles.js';

function MenuOrder({ active }) {
  const [order, loadFailed] = useNavOrder(active);
  const [saveError, setSaveError] = useState('');
  const items = arrange(ITEMS.filter((item) => !item.pinned), order);
  const error = saveError || (loadFailed && 'Couldn’t reach Naradi; this may not be the latest order.');

  function save(next) {
    setSaveError('');
    setNavOrder(next).catch(() => setSaveError('Couldn’t save the order.'));
  }

  return (
    <section style={{ ...card, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Menu order</h2>
      <div style={dim}>Drag by the handle. Today stays at the top; Settings and System at the bottom. Saved for all your devices.</div>
      {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
      <SortableList
        items={items}
        onReorder={(next) => save(next.map((item) => item.key))}
        renderRow={(item) => (
          <>
            {item.icon('#c7c8cc')}
            <span style={{ fontSize: 14, marginLeft: 4 }}>{item.label}</span>
          </>
        )}
      />
      {order.length > 0 && (
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
