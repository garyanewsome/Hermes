import { useEffect, useMemo, useState } from 'react';
import { addDays, parseISODate, toISODate } from '../lib/dates.js';
import { getHabitHistory, setHabitDay } from '../api.js';

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function ChevronIcon({ dir }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ transform: dir === 'left' ? 'none' : 'rotate(180deg)' }}>
      <path d="M8.5 2.5L4 7l4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Same counting rule as the server's habit_streak: consecutive logged days
// back from today, or from yesterday when today isn't logged yet.
function currentStreak(dates, today) {
  let cursor = dates.has(today) ? today : addDays(today, -1);
  let n = 0;
  while (dates.has(cursor)) {
    n += 1;
    cursor = addDays(cursor, -1);
  }
  return n;
}

function longestStreak(dates) {
  const sorted = [...dates].sort();
  let best = 0;
  let run = 0;
  let prev = null;
  for (const d of sorted) {
    run = prev && addDays(prev, 1) === d ? run + 1 : 1;
    if (run > best) best = run;
    prev = d;
  }
  return best;
}

function Stat({ label, value }) {
  return (
    <div style={{ flex: 1, background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 10, padding: '8px 6px', textAlign: 'center' }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent)' }}>{value}</div>
      <div style={{ fontSize: 11.5, color: 'var(--text-dim)', marginTop: 2 }}>{label}</div>
    </div>
  );
}

// A month-grid history for one habit. Logged days are filled in; tapping a
// past day (or today) logs/unlogs it, the same edit the 7-day dots allow but
// reaching back as far as you like.
export default function HabitCalendarPopover({ habit, onClose, onChanged }) {
  const [history, setHistory] = useState(null); // {today, dates: Set}
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState(null); // {y, m}

  useEffect(() => {
    let cancelled = false;
    getHabitHistory(habit.id)
      .then((h) => {
        if (cancelled) return;
        setHistory({ today: h.today, dates: new Set(h.dates) });
        const t = parseISODate(h.today);
        setView({ y: t.getFullYear(), m: t.getMonth() });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [habit.id]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const stats = useMemo(() => {
    if (!history || !view) return null;
    const { dates, today } = history;
    const prefix = `${view.y}-${String(view.m + 1).padStart(2, '0')}-`;
    let inMonth = 0;
    for (const d of dates) if (d.startsWith(prefix)) inMonth += 1;
    return { inMonth, streak: currentStreak(dates, today), best: longestStreak(dates), total: dates.size };
  }, [history, view]);

  function shiftMonth(delta) {
    setView(({ y, m }) => {
      const d = new Date(y, m + delta, 1);
      return { y: d.getFullYear(), m: d.getMonth() };
    });
  }

  async function toggle(iso) {
    const was = history.dates.has(iso);
    setHistory((prev) => {
      const dates = new Set(prev.dates);
      if (was) dates.delete(iso);
      else dates.add(iso);
      return { ...prev, dates };
    });
    try {
      await setHabitDay(habit.id, iso, !was);
    } catch (err) {
      console.error('Habit day toggle failed', err);
      // Roll back so the calendar never shows a log that didn't save.
      setHistory((prev) => {
        const dates = new Set(prev.dates);
        if (was) dates.add(iso);
        else dates.delete(iso);
        return { ...prev, dates };
      });
      return;
    }
    onChanged?.();
  }

  const ready = history && view;
  const todayDate = ready ? parseISODate(history.today) : null;
  const atCurrentMonth = ready && view.y === todayDate.getFullYear() && view.m === todayDate.getMonth();
  const lead = ready ? new Date(view.y, view.m, 1).getDay() : 0;
  const cells = ready ? Array.from({ length: 42 }, (_, i) => new Date(view.y, view.m, 1 - lead + i)) : [];

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60, cursor: 'default' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`${habit.name} history`}
        style={{
          width: 360,
          maxWidth: '94vw',
          maxHeight: '92vh',
          overflowY: 'auto',
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
        <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--accent)', textShadow: '0 0 10px var(--accent-glow)', overflowWrap: 'anywhere' }}>{habit.name}</div>

        {failed && <div style={{ fontSize: 14, color: '#ff6b6b' }}>Couldn't load the history. Try again in a moment.</div>}
        {!ready && !failed && <div style={{ fontSize: 14, color: 'var(--text-faint)', padding: '24px 0', textAlign: 'center' }}>Loading…</div>}

        {ready && (
          <>
            <div style={{ display: 'flex', gap: 8 }}>
              <Stat label="Month" value={stats.inMonth} />
              <Stat label="Streak" value={stats.streak} />
              <Stat label="Best" value={stats.best} />
              <Stat label="Total" value={stats.total} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button type="button" onClick={() => shiftMonth(-1)} aria-label="Previous month" className="dp-nav">
                <ChevronIcon dir="left" />
              </button>
              <div style={{ flex: 1, textAlign: 'center', fontSize: 16, fontWeight: 600 }}>
                {MONTH_NAMES[view.m]} {view.y}
              </div>
              <button type="button" onClick={() => shiftMonth(1)} aria-label="Next month" className="dp-nav" disabled={atCurrentMonth} style={{ opacity: atCurrentMonth ? 0.3 : 1 }}>
                <ChevronIcon dir="right" />
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 3, textAlign: 'center' }}>
              {WEEKDAYS.map((w) => (
                <div key={w} style={{ fontSize: 12, color: 'var(--text-faint)', padding: '4px 0', fontWeight: 600 }}>
                  {w}
                </div>
              ))}
              {cells.map((d) => {
                const iso = toISODate(d);
                const inMonth = d.getMonth() === view.m;
                const logged = history.dates.has(iso);
                const future = iso > history.today;
                const isToday = iso === history.today;
                if (!inMonth) return <div key={iso} />;
                return (
                  <button
                    key={iso}
                    type="button"
                    className="dp-day"
                    disabled={future}
                    aria-label={`${d.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}${logged ? ', logged' : ''}`}
                    aria-pressed={logged}
                    onClick={() => toggle(iso)}
                    style={{
                      height: 40,
                      borderRadius: 10,
                      fontSize: 15,
                      fontWeight: logged ? 700 : 400,
                      background: logged ? 'var(--accent)' : 'transparent',
                      color: logged ? 'var(--accent-text)' : future ? 'var(--text-faint)' : 'var(--text)',
                      boxShadow: logged ? '0 0 8px var(--accent-glow)' : 'none',
                      border: isToday && !logged ? '1.5px solid var(--accent)' : '1.5px solid transparent',
                      padding: 0,
                      opacity: future ? 0.4 : 1,
                      cursor: future ? 'default' : 'pointer',
                    }}
                  >
                    {d.getDate()}
                  </button>
                );
              })}
            </div>

            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>Tap a day to log or unlog it.</div>
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '7px 16px', fontSize: 14 }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
