import { useEffect, useState } from 'react';
import { latestRecap, saveRecapToVault, updateRecap } from '../api.js';
import { renderMarkdown } from '../lib/markdown.js';
import { addDays } from '../lib/dates.js';
import { card, dim, outline } from '../views/workoutStyles.js';
import { shortDate } from './Charts.jsx';

// The latest weekly recap on Today: one line until opened.
export default function RecapCard({ active }) {
  const [recap, setRecap] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!active) return undefined;
    const load = () => latestRecap().then(setRecap).catch(() => {});
    load();
    // Picks up Sunday evening's recap on a page left open.
    const timer = setInterval(load, 300000);
    return () => clearInterval(timer);
  }, [active]);

  if (!recap) return null;

  async function run(label, action) {
    setBusy(label);
    setError('');
    try {
      setRecap(await action(recap.week_start));
    } catch (err) {
      setError(err.name === 'TimeoutError' ? 'That took too long. Try again in a minute.' : err.message);
    }
    setBusy('');
  }

  const saved = recap.vault_path && !recap.vault_stale;
  return (
    <section style={card}>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} style={{ width: '100%', display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: 10, background: 'transparent', border: 'none', padding: 0, color: 'var(--text)', textAlign: 'left' }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent)' }}>Weekly recap</span>
        <span style={dim}>
          {shortDate(recap.week_start)} to {shortDate(addDays(recap.week_start, 6))}
        </span>
        <span style={{ ...dim, marginLeft: 'auto' }}>{open ? 'Close' : 'Read'}</span>
      </button>
      {open && (
        <>
          {/* renderMarkdown escapes its input before adding any tags. */}
          <div style={{ fontSize: 14, lineHeight: 1.5, overflowWrap: 'anywhere' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(recap.markdown) }} />
          {error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{error}</div>}
          {recap.vault_error && <div role="alert" style={{ fontSize: 13, color: '#ff6b6b' }}>{recap.vault_error}</div>}
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <button type="button" disabled={!!busy} onClick={() => run('Updating…', updateRecap)} style={outline}>
              {busy === 'Updating…' ? busy : 'Update'}
            </button>
            {!saved && (
              <button type="button" disabled={!!busy} onClick={() => run('Saving…', saveRecapToVault)} style={outline}>
                {busy === 'Saving…' ? busy : recap.vault_path ? 'Save a new copy to vault' : 'Save to vault'}
              </button>
            )}
            {saved && <span style={dim}>In the vault: {recap.vault_path}</span>}
          </div>
        </>
      )}
    </section>
  );
}
