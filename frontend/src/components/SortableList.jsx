import { useEffect, useRef, useState } from 'react';
import { outline } from '../views/workoutStyles.js';

const GAP = 6;
const ROW = 46;

function moved(list, from, to) {
  const next = [...list];
  next.splice(to, 0, ...next.splice(from, 1));
  return next;
}

// A drag-to-reorder list that works with a mouse or a finger (HTML5 drag and
// drop doesn't fire on touch). Drag by the handle; with a keyboard, focus a
// handle and use the up and down arrows. Rows stay put in the page while
// dragging and are only shifted visually until release.
export default function SortableList({ items, renderRow, onReorder }) {
  const [drag, setDrag] = useState(null); // { from, to, offset }
  const stop = useRef(null);

  useEffect(() => () => stop.current?.(), []);

  function start(event, from) {
    if (event.button !== 0 || stop.current) return;
    event.preventDefault();
    const startY = event.clientY;
    let current = { from, to: from, offset: 0 };
    setDrag(current);

    const move = (e) => {
      if (e.pointerId !== event.pointerId) return;
      const offset = e.clientY - startY;
      const to = Math.max(0, Math.min(items.length - 1, from + Math.round(offset / (ROW + GAP))));
      current = { from, to, offset };
      setDrag(current);
    };
    const finish = (e) => {
      if (e.pointerId !== event.pointerId) return;
      stop.current();
      // A cancelled pointer (the system took over the gesture) changes nothing.
      if (e.type === 'pointerup' && current.to !== from) onReorder(moved(items, from, current.to));
    };
    stop.current = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      stop.current = null;
      setDrag(null);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
  }

  function onKeyDown(event, index) {
    const by = { ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (!by) return;
    event.preventDefault();
    const to = index + by;
    if (to < 0 || to >= items.length) return;
    const handle = event.currentTarget;
    onReorder(moved(items, index, to));
    // Moving the row in the page drops focus; put it back.
    requestAnimationFrame(() => handle.focus());
  }

  function shift(index) {
    if (!drag) return 0;
    const { from, to, offset } = drag;
    if (index === from) return offset;
    if (index > from && index <= to) return -(ROW + GAP);
    if (index < from && index >= to) return ROW + GAP;
    return 0;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: GAP }}>
      {items.map((item, index) => {
        const dragging = drag?.from === index;
        return (
          <div
            key={item.key}
            style={{
              height: ROW,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '0 4px 0 10px',
              borderRadius: 8,
              border: `1px solid ${dragging ? 'var(--accent)' : 'var(--border)'}`,
              background: dragging ? 'var(--panel-2)' : 'var(--panel)',
              boxShadow: dragging ? '0 4px 16px rgba(0,0,0,0.5)' : 'none',
              transform: `translateY(${shift(index)}px)`,
              transition: drag && !dragging ? 'transform 120ms' : 'none',
              position: 'relative',
              zIndex: dragging ? 1 : 0,
              userSelect: 'none',
            }}
          >
            {renderRow(item)}
            <button
              type="button"
              onPointerDown={(e) => start(e, index)}
              onKeyDown={(e) => onKeyDown(e, index)}
              aria-label={`Move ${item.label}: drag, or use the up and down arrow keys`}
              title="Drag to move"
              style={{
                ...outline,
                marginLeft: 'auto',
                width: 44,
                height: 38,
                padding: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: dragging ? 'grabbing' : 'grab',
                // Lets a finger drag the handle instead of scrolling the page.
                touchAction: 'none',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M2.5 5h11M2.5 8h11M2.5 11h11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}
