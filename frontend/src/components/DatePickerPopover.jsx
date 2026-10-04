import { useEffect, useState } from 'react';
import { addDays, parseISODate, toISODate, todayISO } from '../lib/dates.js';

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function ChevronIcon({ dir }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ transform: dir === 'left' ? 'none' : 'rotate(180deg)' }}>
      <path d="M8.5 2.5L4 7l4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// A calendar in a centered modal (same pattern as the recurrence and
// delete-confirm popovers) instead of the browser's own <input type="date">.
// The native control committed its change event as soon as *any* segment
// of an already-filled date was edited — typing a new month into an
// existing date fired onChange with the old day still attached, which
// closed the picker before the day could be entered. Here nothing commits
// until you actually pick a day (or a quick-pick chip).
export default function DatePickerPopover({ value, onPick, onClear, onClose }) {
  const selected = parseISODate(value);
  const today = todayISO();
  const anchor = selected || parseISODate(today);
  const [view, setView] = useState({ y: anchor.getFullYear(), m: anchor.getMonth() });

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function shiftMonth(delta) {
    setView(({ y, m }) => {
      const d = new Date(y, m + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() };
    });
  }

  const lead = new Date(view.y, view.m, 1).getDay();
  const cells = Array.from({ length: 42 }, (_, i) => new Date(view.y, view.m, 1 - lead + i));

  const chips = [
    { label: 'Today', iso: today },
    { label: 'Tomorrow', iso: addDays(today, 1) },
    { label: 'Next week', iso: addDays(today, 7) },
  ];

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, cursor: 'default' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Pick a due date"
        style={{
          width: 340,
          maxWidth: '94vw',
          background: 'var(--bg)',
          border: '1px solid var(--accent)',
          boxShadow: '0 0 20px var(--accent-glow)',
          borderRadius: 14,
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          color: 'var(--text)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button type="button" onClick={() => shiftMonth(-1)} aria-label="Previous month" className="dp-nav">
            <ChevronIcon dir="left" />
          </button>
          <div style={{ flex: 1, textAlign: 'center', fontSize: 16, fontWeight: 600 }}>
            {MONTH_NAMES[view.m]} {view.y}
          </div>
          <button type="button" onClick={() => shiftMonth(1)} aria-label="Next month" className="dp-nav">
            <ChevronIcon dir="right" />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, textAlign: 'center' }}>
          {WEEKDAYS.map((w) => (
            <div key={w} style={{ fontSize: 12, color: 'var(--text-faint)', padding: '4px 0', fontWeight: 600 }}>
              {w}
            </div>
          ))}
          {cells.map((d) => {
            const iso = toISODate(d);
            const inMonth = d.getMonth() === view.m;
            const isSelected = iso === value;
            const isToday = iso === today;
            return (
              <button
                key={iso}
                type="button"
                className="dp-day"
                aria-label={d.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                aria-pressed={isSelected}
                onClick={() => onPick(iso)}
                style={{
                  height: 40,
                  borderRadius: 10,
                  fontSize: 15,
                  fontWeight: isSelected ? 700 : 400,
                  background: isSelected ? 'var(--accent)' : 'transparent',
                  color: isSelected ? 'var(--accent-text)' : inMonth ? 'var(--text)' : 'var(--text-faint)',
                  border: isToday && !isSelected ? '1.5px solid var(--accent)' : '1.5px solid transparent',
                  padding: 0,
                  opacity: inMonth || isSelected ? 1 : 0.55,
                }}
              >
                {d.getDate()}
              </button>
            );
          })}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {chips.map((c) => (
            <button
              key={c.label}
              type="button"
              className="dp-chip"
              onClick={() => onPick(c.iso)}
              style={{ background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 999, padding: '7px 14px', fontSize: 13.5 }}
            >
              {c.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          {value ? (
            <button type="button" onClick={onClear} style={{ background: 'transparent', border: 'none', color: '#ff6b6b', fontSize: 14, padding: '7px 4px' }}>
              Clear date
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '7px 16px', fontSize: 14 }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
