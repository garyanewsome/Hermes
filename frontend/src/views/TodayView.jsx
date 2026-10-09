import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import {
  completeTask,
  getTodoAgenda,
  getWeather,
  listHabits,
  listTasks,
  searchWeatherLocations,
  setHabitDay,
  setWeatherLocation,
  skipTodoItem,
  updateTodoItem,
} from '../api.js';
import { DUE_COLORS, dueTone, formatDue, parseISODate, todayISO } from '../lib/dates.js';
import { QUADRANT_BY_KEY, QUADRANTS } from '../lib/quadrants.js';

const POLL_INTERVAL_MS = 60000;
const TODO_COLOR = '#b46bff';
const BOARD_COLOR = '#3bffa0';
const HABIT_COLOR = '#ff4fc0';

// Other views (which stay mounted) refresh themselves on this.
function announceChange() {
  window.dispatchEvent(new Event('hermes:data-changed'));
}

function WeatherIcon({ kind, size = 30 }) {
  const common = { width: size, height: size, viewBox: '0 0 32 32', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' };
  const cloud = 'M9 22a5 5 0 0 1-.6-9.96A7 7 0 0 1 22 11.5a5.25 5.25 0 0 1-.5 10.5z';
  switch (kind) {
    case 'clear':
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="5.5" />
          <path d="M16 3.5v3M16 25.5v3M3.5 16h3M25.5 16h3M7.2 7.2l2.1 2.1M22.7 22.7l2.1 2.1M7.2 24.8l2.1-2.1M22.7 9.3l2.1-2.1" />
        </svg>
      );
    case 'partly':
      return (
        <svg {...common}>
          <circle cx="12" cy="11" r="4" />
          <path d="M12 3.5v1.6M4.5 11h1.6M6.7 5.7l1.1 1.1M17.3 5.7l-1.1 1.1" />
          <path d="M11 26a4.5 4.5 0 0 1-.4-8.98A6 6 0 0 1 22 18a4.5 4.5 0 0 1-.3 8z" />
        </svg>
      );
    case 'rain':
      return (
        <svg {...common}>
          <path d={cloud} transform="translate(0 -3)" />
          <path d="M11 24.5l-1.2 3M16.5 24.5l-1.2 3M22 24.5l-1.2 3" />
        </svg>
      );
    case 'snow':
      return (
        <svg {...common}>
          <path d={cloud} transform="translate(0 -3)" />
          <path d="M11 25v.01M16 27v.01M21 25v.01M13.5 28.5v.01M18.5 28.5v.01" strokeWidth="2.6" />
        </svg>
      );
    case 'thunder':
      return (
        <svg {...common}>
          <path d={cloud} transform="translate(0 -3)" />
          <path d="M17 20l-3.5 5h4l-2.5 4.5" />
        </svg>
      );
    case 'fog':
      return (
        <svg {...common}>
          <path d="M5 11h22M8 16h18M5 21h22M10 26h14" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <path d={cloud} />
        </svg>
      );
  }
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="2.2" />
      <path d="M8 1.5v1.7M8 12.8v1.7M1.5 8h1.7M12.8 8h1.7M3.4 3.4l1.2 1.2M11.4 11.4l1.2 1.2M3.4 12.6l1.2-1.2M11.4 4.6l1.2-1.2" />
    </svg>
  );
}

function SkipIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 14 14" fill="none">
      <path d="M2.5 3.2v7.6L8 7 2.5 3.2z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
      <path d="M10.5 3v8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function CheckCircle({ checked, color, onClick, label }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={checked}
      style={{
        width: 28,
        height: 28,
        flexShrink: 0,
        borderRadius: '50%',
        border: `2px solid ${color}`,
        background: checked ? color : 'transparent',
        color: 'var(--bg)',
        padding: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {checked && (
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2.5 7.2l3 3L11.5 4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

function Card({ title, color, count, onOpen, children }) {
  return (
    <section style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 14, padding: '14px 14px 6px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6, padding: '0 2px' }}>
        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color }}>{title}</div>
        {count != null && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{count}</div>}
        {onOpen && (
          <button
            type="button"
            onClick={onOpen}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: 'var(--text-dim)', fontSize: 13, padding: '4px 2px' }}
          >
            Open &rarr;
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

function Empty({ children }) {
  return <div style={{ padding: '8px 4px 14px', fontSize: 14, color: 'var(--text-faint)' }}>{children}</div>;
}

function DueTag({ iso }) {
  if (!iso) return null;
  return <span style={{ fontSize: 12.5, fontWeight: 600, color: DUE_COLORS[dueTone(iso)] }}>{formatDue(iso)}</span>;
}

function Row({ left, children, last }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '11px 4px',
        borderTop: '1px solid var(--border)',
        borderBottom: last ? 'none' : undefined,
        minHeight: 52,
      }}
    >
      {left}
      {children}
    </div>
  );
}

function WeatherCard({ weather, error, onEditLocation }) {
  if (!weather) {
    return (
      <section style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 14, padding: 16, color: 'var(--text-faint)', fontSize: 14 }}>
        {error ? 'Weather is unavailable right now.' : 'Loading weather…'}
      </section>
    );
  }
  const { current, days, location } = weather;
  const today = days[0];
  const upcoming = days.slice(1, 4);
  return (
    <section style={{ background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 14, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ color: 'var(--accent)' }}>
          <WeatherIcon kind={current.icon} size={46} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <div style={{ fontSize: 40, fontWeight: 700, lineHeight: 1, color: 'var(--text)' }}>{current.temp}°</div>
            <div style={{ fontSize: 16, color: 'var(--text)' }}>{current.label}</div>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 6 }}>
            Feels {current.feels_like}° · Wind {current.wind_mph} mph
          </div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right', fontSize: 13, color: 'var(--text-dim)', flexShrink: 0 }}>
          <div style={{ color: 'var(--text)', fontSize: 15, fontWeight: 600 }}>
            H {today.high}° · L {today.low}°
          </div>
          <div style={{ marginTop: 4 }}>{today.precip_chance != null ? `${today.precip_chance}% rain` : ''}</div>
        </div>
      </div>

      {upcoming.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${upcoming.length}, minmax(0, 1fr))`, gap: 8, marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
          {upcoming.map((d) => (
            <div key={d.date} style={{ minWidth: 0, fontSize: 13 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text)', fontWeight: 600 }}>
                <span style={{ color: 'var(--text-dim)', display: 'flex' }}>
                  <WeatherIcon kind={d.icon} size={20} />
                </span>
                {parseISODate(d.date).toLocaleDateString(undefined, { weekday: 'short' })}
              </div>
              <div style={{ color: 'var(--text-dim)', whiteSpace: 'nowrap', marginTop: 3 }}>
                {d.high}° / {d.low}°
              </div>
              {d.precip_chance >= 30 && <div style={{ color: 'var(--text-faint)', marginTop: 1 }}>{d.precip_chance}% rain</div>}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 12, fontSize: 12.5, color: 'var(--text-faint)' }}>
        <span>{location.name}</span>
        {weather.stale && <span>· may be out of date</span>}
        <button
          type="button"
          onClick={onEditLocation}
          aria-label="Change weather location"
          title="Change location"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 4, display: 'flex' }}
        >
          <GearIcon />
        </button>
      </div>
    </section>
  );
}

function LocationPopover({ current, onPick, onClose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [failed, setFailed] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Search as you type (debounced); a stale response never overwrites a newer one.
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      setFailed(false);
      return undefined;
    }
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const found = await searchWeatherLocations(query.trim());
        if (seq.current === mine) {
          setResults(found);
          setFailed(false);
        }
      } catch {
        if (seq.current === mine) setFailed(true);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 60 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Weather location"
        style={{
          width: 360,
          maxWidth: '94vw',
          maxHeight: '80vh',
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
        <div style={{ fontSize: 16, fontWeight: 600 }}>Weather location</div>
        <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>Currently {current}. Search by city or zip code.</div>
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. 15650 or Pittsburgh"
          aria-label="Search for a location"
          style={{ background: 'var(--panel)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '10px 12px', fontSize: 16 }}
        />
        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4, minHeight: 0 }}>
          {failed && <div style={{ fontSize: 13, color: '#ff6b6b' }}>Search is unavailable right now.</div>}
          {results && results.length === 0 && <div style={{ fontSize: 13, color: 'var(--text-faint)' }}>No matches.</div>}
          {results?.map((r) => (
            <button
              key={`${r.latitude},${r.longitude}`}
              type="button"
              onClick={() => onPick(r)}
              style={{ textAlign: 'left', background: 'var(--panel)', border: '1px solid var(--border)', color: 'var(--text)', borderRadius: 8, padding: '10px 12px', fontSize: 14.5 }}
            >
              <div>{r.name}</div>
              {r.detail && <div style={{ fontSize: 12.5, color: 'var(--text-faint)', marginTop: 2 }}>{r.detail}</div>}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
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

export default function TodayView({ onOpenDrawer, onNavigate, active }) {
  const isMobile = useIsMobile();
  const [agenda, setAgenda] = useState(null);
  const [tasks, setTasks] = useState(null);
  const [habits, setHabits] = useState(null);
  const [weather, setWeather] = useState(null);
  const [weatherError, setWeatherError] = useState(false);
  const [editingLocation, setEditingLocation] = useState(false);

  // Each source loads on its own, so a slow or failing one (weather is the
  // only call that leaves the house) never holds up the rest of the page.
  async function refreshLocal() {
    const [a, t, h] = await Promise.allSettled([getTodoAgenda(), listTasks('open'), listHabits()]);
    if (a.status === 'fulfilled') setAgenda(a.value);
    if (t.status === 'fulfilled') setTasks(t.value);
    if (h.status === 'fulfilled') setHabits(h.value);
  }

  async function refreshWeather() {
    try {
      setWeather(await getWeather());
      setWeatherError(false);
    } catch {
      setWeatherError(true);
    }
  }

  function refreshAll() {
    refreshLocal();
    refreshWeather();
  }

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshAll, POLL_INTERVAL_MS);
    window.addEventListener('hermes:wake', refreshAll);
    return () => {
      clearInterval(interval);
      window.removeEventListener('hermes:wake', refreshAll);
    };
  }, []);

  // Views stay mounted, so coming back to Today needs its own refresh —
  // things get changed on the other pages in between.
  const wasActive = useRef(active);
  useEffect(() => {
    if (active && !wasActive.current) refreshAll();
    wasActive.current = active;
  }, [active]);

  const today = agenda?.today || todayISO();

  // Todo items: overdue first, then today's (the agenda is already ordered).
  const todoItems = agenda ? [...agenda.overdue, ...agenda.due_today] : null;

  // Board tasks due today or earlier, overdue first, then by quadrant order.
  const quadrantRank = Object.fromEntries(QUADRANTS.map((q, i) => [q.key, i]));
  const boardTasks = tasks
    ? tasks
        .filter((t) => t.due_date && t.due_date <= today)
        .sort((a, b) => (a.due_date < b.due_date ? -1 : a.due_date > b.due_date ? 1 : (quadrantRank[a.quadrant] ?? 9) - (quadrantRank[b.quadrant] ?? 9)))
    : null;

  async function handleTodoDone(item) {
    setAgenda((prev) => prev && { ...prev, overdue: prev.overdue.filter((i) => i.id !== item.id), due_today: prev.due_today.filter((i) => i.id !== item.id) });
    try {
      await updateTodoItem(item.id, { done: true });
    } catch (err) {
      console.error('Complete failed', err);
    }
    await refreshLocal();
    announceChange();
  }

  async function handleTodoSkip(item) {
    setAgenda((prev) => prev && { ...prev, overdue: prev.overdue.filter((i) => i.id !== item.id), due_today: prev.due_today.filter((i) => i.id !== item.id) });
    try {
      await skipTodoItem(item.id);
    } catch (err) {
      console.error('Skip failed', err);
    }
    await refreshLocal();
    announceChange();
  }

  async function handleTaskDone(task) {
    setTasks((prev) => prev && prev.filter((t) => t.id !== task.id));
    try {
      await completeTask(task.id);
    } catch (err) {
      console.error('Complete failed', err);
    }
    await refreshLocal();
    announceChange();
  }

  async function handleHabitToggle(habit) {
    const day = habit.last_7_days[habit.last_7_days.length - 1];
    const next = !day.logged;
    setHabits((prev) =>
      prev.map((h) =>
        h.id === habit.id ? { ...h, last_7_days: h.last_7_days.map((d, i) => (i === h.last_7_days.length - 1 ? { ...d, logged: next } : d)) } : h
      )
    );
    try {
      await setHabitDay(habit.id, day.date, next);
    } catch (err) {
      console.error('Habit toggle failed', err);
    }
    await refreshLocal();
    announceChange();
  }

  async function handlePickLocation(loc) {
    setEditingLocation(false);
    try {
      await setWeatherLocation(loc);
    } catch (err) {
      console.error('Saving location failed', err);
    }
    setWeather(null);
    refreshWeather();
  }

  const habitsDone = habits ? habits.filter((h) => h.last_7_days[h.last_7_days.length - 1]?.logged).length : 0;
  const subtitle = parseISODate(today).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
  const pad = isMobile ? 14 : 24;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Today" subtitle={subtitle} onOpenDrawer={onOpenDrawer}>
        {isMobile && <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>{subtitle}</div>}
      </TopBar>

      <div style={{ flex: 1, overflowY: 'auto', padding: `${pad}px ${pad}px calc(${pad}px + env(safe-area-inset-bottom))` }}>
        <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <WeatherCard weather={weather} error={weatherError} onEditLocation={() => setEditingLocation(true)} />

          <Card title="Todo" color={TODO_COLOR} count={todoItems ? todoItems.length : null} onOpen={() => onNavigate('todo')}>
            {!todoItems ? (
              <Empty>Loading…</Empty>
            ) : todoItems.length === 0 ? (
              <Empty>Nothing due today.</Empty>
            ) : (
              todoItems.map((item) => {
                const recurring = Boolean(item.recurrence_days || item.recurrence_weekdays);
                return (
                  <Row key={item.id} left={<CheckCircle checked={false} color={TODO_COLOR} label={`Mark done: ${item.text}`} onClick={() => handleTodoDone(item)} />}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 16, lineHeight: 1.3, color: 'var(--text)', overflowWrap: 'anywhere' }}>{item.text}</div>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginTop: 2, flexWrap: 'wrap' }}>
                        {item.due_date < today && <DueTag iso={item.due_date} />}
                        <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>{item.list_name}</span>
                      </div>
                    </div>
                    {recurring && (
                      <button
                        type="button"
                        onClick={() => handleTodoSkip(item)}
                        aria-label="Skip this occurrence"
                        title="Skip this occurrence"
                        style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', padding: 8, display: 'flex' }}
                      >
                        <SkipIcon />
                      </button>
                    )}
                  </Row>
                );
              })
            )}
          </Card>

          <Card title="The Board" color={BOARD_COLOR} count={boardTasks ? boardTasks.length : null} onOpen={() => onNavigate('tasks')}>
            {!boardTasks ? (
              <Empty>Loading…</Empty>
            ) : boardTasks.length === 0 ? (
              <Empty>No board tasks due today.</Empty>
            ) : (
              boardTasks.map((task) => {
                const q = QUADRANT_BY_KEY[task.quadrant] || QUADRANTS[0];
                return (
                  <Row key={task.id} left={<CheckCircle checked={false} color={q.color} label={`Complete: ${task.title}`} onClick={() => handleTaskDone(task)} />}>
                    <div style={{ flex: 1, minWidth: 0, borderLeft: `3px solid ${q.color}`, paddingLeft: 10 }}>
                      <div style={{ fontSize: 16, lineHeight: 1.3, color: 'var(--text)', overflowWrap: 'anywhere' }}>{task.title}</div>
                      <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginTop: 2 }}>
                        {task.due_date < today && <DueTag iso={task.due_date} />}
                        <span style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>{q.label}</span>
                      </div>
                    </div>
                  </Row>
                );
              })
            )}
          </Card>

          <Card title="Habits" color={HABIT_COLOR} count={habits ? `${habitsDone}/${habits.length}` : null} onOpen={() => onNavigate('habits')}>
            {!habits ? (
              <Empty>Loading…</Empty>
            ) : habits.length === 0 ? (
              <Empty>No habits yet.</Empty>
            ) : (
              habits.map((habit) => {
                const logged = Boolean(habit.last_7_days[habit.last_7_days.length - 1]?.logged);
                return (
                  <Row key={habit.id} left={<CheckCircle checked={logged} color={HABIT_COLOR} label={`${logged ? 'Unlog' : 'Log'} ${habit.name} today`} onClick={() => handleHabitToggle(habit)} />}>
                    <div style={{ flex: 1, minWidth: 0, fontSize: 16, color: logged ? 'var(--text-dim)' : 'var(--text)', overflowWrap: 'anywhere' }}>{habit.name}</div>
                    {habit.streak > 0 && (
                      <div style={{ fontSize: 12.5, color: 'var(--text-faint)', flexShrink: 0 }}>
                        {habit.streak} day{habit.streak === 1 ? '' : 's'}
                      </div>
                    )}
                  </Row>
                );
              })
            )}
          </Card>
        </div>
      </div>

      {editingLocation && (
        <LocationPopover current={weather?.location?.name || 'Latrobe, PA'} onPick={handlePickLocation} onClose={() => setEditingLocation(false)} />
      )}
    </div>
  );
}
