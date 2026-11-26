import { useEffect, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { getTrends } from '../api.js';
import { Bars, DayGrid, shortDate } from '../components/Charts.jsx';
import { addDays } from '../lib/dates.js';
import { dim, number, outline, solid } from './workoutStyles.js';

const RANGES = [
  [4, '4 weeks'],
  [13, '3 months'],
  [52, 'Year'],
];

// Each chart is one series, colored like the page it comes from.
const SERIES = [
  { key: 'tasks', title: 'Board tasks finished', color: '#3bffa0', one: 'task', many: 'tasks' },
  { key: 'todos', title: 'Todos checked off', color: '#b46bff', one: 'todo', many: 'todos' },
  { key: 'habits', title: 'Habit check-ins', color: '#ff4fc0', one: 'check-in', many: 'check-ins' },
  { key: 'chores', title: 'Chores done', color: '#8c9eff', one: 'chore', many: 'chores' },
  { key: 'gym_days', title: 'Gym days', color: '#ff5c5c', one: 'gym day', many: 'gym days' },
  { key: 'activity_minutes', title: 'Activity minutes', color: '#ff5c5c', one: 'minute', many: 'minutes' },
];

const count = (value, one, many) => `${number(value)} ${value === 1 ? one : many}`;

// A habit's last year, with how often it was done lately.
function HabitYear({ habit, grid, today }) {
  const done = new Set(habit.dates);
  const recent = habit.dates.filter((d) => d > addDays(today, -30) && d <= today).length;
  return (
    <div style={{ '--accent': '#ff4fc0' }}>
      <DayGrid
        title={`${habit.name} · ${recent} of the last 30 days`}
        legend={false}
        start={grid.start}
        today={today}
        weeks={grid.weeks}
        days={habit.dates.map((date) => ({ date, sets: 1, activities: 0 }))}
        describe={(day) => (day && done.has(day.date) ? 'done' : 'not logged')}
      />
    </div>
  );
}

export default function TrendsView({ onOpenDrawer, active }) {
  const [weeks, setWeeks] = useState(13);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const isMobile = useIsMobile();

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    getTrends(weeks)
      .then((next) => current && (setData({ ...next, range: weeks }), setError('')))
      .catch(() => current && setError('Couldn’t load trends.'));
    return () => {
      current = false;
    };
  }, [active, weeks]);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="Trends" onOpenDrawer={onOpenDrawer} />
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: isMobile ? 14 : 24 }}>
        <div style={{ maxWidth: 1240, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {RANGES.map(([value, text]) => (
              <button key={value} type="button" onClick={() => setWeeks(value)} aria-pressed={weeks === value} style={{ ...(weeks === value ? solid : outline), padding: '5px 12px', fontSize: 12 }}>
                {text}
              </button>
            ))}
          </div>
          {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
          {!data && !error && <div style={dim}>Loading…</div>}
          {data && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))', gap: 12 }}>
                {SERIES.map((series) => (
                  <div key={`${series.key}-${data.range}`} style={{ '--accent': series.color, minWidth: 0 }}>
                    <Bars
                      title={series.title}
                      valueHeading="Total"
                      points={data.weeks.map((week) => ({
                        key: week.start,
                        label: `Week of ${shortDate(week.start)}`,
                        value: week[series.key],
                        detail: count(week[series.key], series.one, series.many),
                      }))}
                    />
                  </div>
                ))}
              </div>
              <div style={dim}>
                The latest week is still in progress.
                {data.todo_history_since
                  ? ` Todo history starts ${shortDate(data.todo_history_since)}.`
                  : ' Todo history starts with your next check-off.'}
              </div>
              {data.habits.map((habit) => (
                <HabitYear key={habit.id} habit={habit} grid={data.habit_grid} today={data.today} />
              ))}
              {data.habits.length === 0 && <div style={dim}>No habits yet.</div>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
