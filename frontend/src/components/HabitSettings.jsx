import { dim } from '../views/workoutStyles.js';

const field = { background: 'var(--panel-2)', border: '1px solid var(--border-strong)', color: 'var(--text)', borderRadius: 8, padding: '8px 10px', fontSize: 16, width: '100%', minWidth: 0 };

// The unit, add-or-replace and streak choices, for new and existing habits.
export default function HabitSettings({ value, onChange }) {
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <>
      <label style={{ ...dim, display: 'flex', flexDirection: 'column', gap: 4 }}>
        Unit (leave empty for a simple check-off)
        <input value={value.unit} onChange={(e) => set({ unit: e.target.value })} maxLength={20} list="habit-units" placeholder="minutes" style={field} />
        <datalist id="habit-units">
          {['minutes', 'pages', 'lbs', 'miles', 'reps'].map((unit) => <option key={unit} value={unit} />)}
        </datalist>
      </label>
      {value.unit.trim() && (
        <label style={{ ...dim, display: 'flex', flexDirection: 'column', gap: 4 }}>
          A second entry on the same day
          <select value={value.add_up ? 'add' : 'replace'} onChange={(e) => set({ add_up: e.target.value === 'add' })} style={field}>
            <option value="add">Adds to it (time, pages)</option>
            <option value="replace">Replaces it (weight)</option>
          </select>
        </label>
      )}
      <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={value.hide_streak} onChange={(e) => set({ hide_streak: e.target.checked })} style={{ width: 18, height: 18, accentColor: 'var(--accent)' }} />
        Hide the streak
      </label>
    </>
  );
}
