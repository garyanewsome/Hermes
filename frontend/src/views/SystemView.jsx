import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { getSystem } from '../api.js';

const POLL_INTERVAL_MS = 15000;
const GOOD = '#3bffa0';
const WARN = '#ffb02e';
const BAD = '#ff5d6c';

// ---- formatting -----------------------------------------------------------

function fmtBytes(n) {
  if (n == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

function fmtDuration(seconds) {
  if (seconds == null) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${Math.floor(seconds)}s`;
}

const fmtAge = (seconds) => (seconds == null ? 'never' : seconds < 10 ? 'just now' : `${fmtDuration(seconds)} ago`);

// Rough period of a cron schedule, enough to tell "overdue" from "fine".
function cronPeriodSeconds(schedule) {
  const [min = '*', hour = '*', dom = '*', , dow = '*'] = (schedule || '').split(/\s+/);
  if (min.startsWith('*/')) return Number(min.slice(2)) * 60 || 3600;
  if (min === '*') return 60;
  if (hour.startsWith('*/')) return Number(hour.slice(2)) * 3600 || 3600;
  if (hour === '*') return 3600;
  if (dom === '*' && dow === '*') return 86400;
  return 7 * 86400;
}

// ---- derived health -------------------------------------------------------

function findIssues(data) {
  const issues = [];
  const { agent, agent_error: agentError, probes = [] } = data;
  if (!agent) {
    issues.push({ level: 'bad', text: `Can't reach the host status service${agentError ? ` (${agentError})` : ''}` });
  } else {
    const { host, disks = [], gpu, docker, services = [], k3s, backups } = agent;
    if (host?.reboot_required) issues.push({ level: 'warn', text: 'The server needs a reboot' });
    for (const d of disks) {
      const pct = (d.used / d.total) * 100;
      if (pct >= 90) issues.push({ level: 'bad', text: `${d.mount} is ${Math.round(pct)}% full` });
      else if (pct >= 80) issues.push({ level: 'warn', text: `${d.mount} is ${Math.round(pct)}% full` });
    }
    if (host?.memory?.total && host.memory.available / host.memory.total < 0.1) {
      issues.push({ level: 'warn', text: 'Memory is nearly full' });
    }
    const cpuTemp = host?.temperatures?.find((t) => t.chip === 'k10temp')?.c;
    if (cpuTemp >= 85) issues.push({ level: 'warn', text: `CPU is hot (${Math.round(cpuTemp)}°C)` });
    if (gpu?.error) issues.push({ level: 'warn', text: `GPU: ${gpu.error}` });
    else if (gpu?.temperature_c >= 85) issues.push({ level: 'warn', text: `GPU is hot (${Math.round(gpu.temperature_c)}°C)` });
    for (const s of services) {
      if (s.state !== 'active') issues.push({ level: 'bad', text: `Service ${s.name} is ${s.state}` });
    }
    for (const c of docker?.containers || []) {
      if (c.state !== 'running') issues.push({ level: 'bad', text: `Container ${c.name} is ${c.state}` });
      else if (c.unhealthy) issues.push({ level: 'bad', text: `Container ${c.name} is unhealthy` });
    }
    for (const p of k3s?.pods || []) {
      if (!p.ok) issues.push({ level: 'bad', text: `Pod ${p.name} is ${p.reason || p.phase}` });
    }
    for (const j of k3s?.cronjobs || []) {
      if (j.suspended) continue;
      const limit = cronPeriodSeconds(j.schedule) * 2.5;
      if (j.last_success_age_seconds == null && j.last_schedule_age_seconds != null) {
        issues.push({ level: 'warn', text: `Scheduled job ${j.name} has never succeeded` });
      } else if (j.last_success_age_seconds != null && j.last_success_age_seconds > limit) {
        issues.push({ level: 'warn', text: `Scheduled job ${j.name} last succeeded ${fmtAge(j.last_success_age_seconds)}` });
      }
    }
    if (backups?.error) issues.push({ level: 'warn', text: 'Backup folder can’t be read' });
    else if (backups && !backups.latest) issues.push({ level: 'warn', text: 'No database backups found' });
    else if (backups?.latest?.age_seconds > 36 * 3600) {
      issues.push({ level: 'warn', text: `Last database backup was ${fmtAge(backups.latest.age_seconds)}` });
    }
  }
  for (const p of probes) {
    if (!p.ok) issues.push({ level: 'bad', text: `${p.name} isn’t answering` });
  }
  return issues;
}

// ---- small pieces ---------------------------------------------------------

function Dot({ color }) {
  return <span style={{ width: 9, height: 9, borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}`, flexShrink: 0, display: 'inline-block' }} />;
}

function Bar({ pct, color }) {
  return (
    <div style={{ height: 8, borderRadius: 4, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
      <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', background: color, borderRadius: 4, boxShadow: `0 0 8px ${color}` }} />
    </div>
  );
}

const barColor = (pct) => (pct >= 90 ? BAD : pct >= 80 ? WARN : 'var(--accent)');

function Card({ title, desktop, children, note }) {
  return (
    <section
      style={{
        background: 'var(--panel)',
        border: '1px solid var(--border)',
        borderRadius: 14,
        padding: desktop ? '18px 18px 14px' : '14px 14px 10px',
        boxShadow: desktop ? 'inset 0 2px 0 0 var(--accent), 0 0 24px -12px var(--accent)' : undefined,
        breakInside: desktop ? 'avoid' : undefined,
        marginBottom: desktop ? 18 : undefined,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <div style={{ fontSize: desktop ? 14 : 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent)' }}>{title}</div>
        {note && <div style={{ marginLeft: 'auto', fontSize: 12.5, color: 'var(--text-faint)' }}>{note}</div>}
      </div>
      {children}
    </section>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text)', marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 1 }}>{sub}</div>}
    </div>
  );
}

function Meter({ label, pct, right }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 14 }}>
        <span style={{ color: 'var(--text)' }}>{label}</span>
        <span style={{ color: 'var(--text-dim)', textAlign: 'right' }}>{right}</span>
      </div>
      <Bar pct={pct} color={barColor(pct)} />
    </div>
  );
}

function Row({ left, right, sub, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: '1px solid var(--border)', minWidth: 0 }}>
      <Dot color={color} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14.5, color: 'var(--text)', overflowWrap: 'anywhere' }}>{left}</div>
        {sub && <div style={{ fontSize: 12.5, color: 'var(--text-faint)', overflowWrap: 'anywhere' }}>{sub}</div>}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-dim)', textAlign: 'right', flexShrink: 0 }}>{right}</div>
    </div>
  );
}

function Muted({ children }) {
  return <div style={{ fontSize: 13.5, color: 'var(--text-faint)' }}>{children}</div>;
}

// ---- cards ----------------------------------------------------------------

function OverviewCard({ agent, desktop }) {
  const { host } = agent;
  const mem = host.memory;
  const memUsed = mem.total - mem.available;
  const memPct = (memUsed / mem.total) * 100;
  const cpuTemp = host.temperatures.find((t) => t.chip === 'k10temp')?.c;
  const nvmeTemp = Math.max(...host.temperatures.filter((t) => t.chip === 'nvme' && t.label === 'Composite').map((t) => t.c), -Infinity);
  return (
    <Card title="Server" desktop={desktop} note={host.hostname}>
      {host.reboot_required && (
        <div style={{ fontSize: 13.5, fontWeight: 600, color: WARN, border: `1px solid ${WARN}`, borderRadius: 8, padding: '6px 10px' }}>Reboot required</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }}>
        <Stat label="Uptime" value={fmtDuration(host.uptime_seconds)} sub={host.kernel} />
        <Stat label="Load" value={host.load[0].toFixed(2)} sub={`${host.load[1].toFixed(2)} · ${host.load[2].toFixed(2)} · ${host.cpu_count} cores`} />
        <Stat label="CPU temp" value={cpuTemp != null ? `${Math.round(cpuTemp)}°C` : '—'} />
        <Stat label="Disk temp" value={Number.isFinite(nvmeTemp) ? `${Math.round(nvmeTemp)}°C` : '—'} />
      </div>
      <Meter label="CPU" pct={host.cpu_percent} right={`${Math.round(host.cpu_percent)}%`} />
      <Meter label="Memory" pct={memPct} right={`${fmtBytes(memUsed)} of ${fmtBytes(mem.total)}`} />
      {mem.swap_total > 0 && <Meter label="Swap" pct={((mem.swap_total - mem.swap_free) / mem.swap_total) * 100} right={`${fmtBytes(mem.swap_total - mem.swap_free)} of ${fmtBytes(mem.swap_total)}`} />}
      <Muted>{host.os}</Muted>
    </Card>
  );
}

function StorageCard({ agent, desktop }) {
  const { disks, storage } = agent;
  const entries = storage?.entries || [];
  const largest = entries[0]?.bytes || 1;
  const shown = entries.filter((e) => e.bytes >= 50 * 1024 * 1024).slice(0, 8);
  const rest = entries.length - shown.length;
  return (
    <Card title="Storage" desktop={desktop}>
      {disks.map((d) => {
        const pct = (d.used / d.total) * 100;
        return <Meter key={d.mount} label={d.mount} pct={pct} right={`${fmtBytes(d.used)} of ${fmtBytes(d.total)} · ${fmtBytes(d.available)} free`} />;
      })}
      {storage && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>In {storage.root}</div>
          {entries.length === 0 ? (
            <Muted>Measuring…</Muted>
          ) : (
            <>
              {shown.map((e) => (
                <div key={e.name} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5 }}>
                    <span style={{ color: 'var(--text)', overflowWrap: 'anywhere' }}>
                      {e.name}
                      {storage.partial?.includes(e.name) && <span style={{ color: 'var(--text-faint)' }}> (partial)</span>}
                    </span>
                    <span style={{ color: 'var(--text-dim)', flexShrink: 0, marginLeft: 8 }}>{fmtBytes(e.bytes)}</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)' }}>
                    <div style={{ width: `${(e.bytes / largest) * 100}%`, height: '100%', background: 'var(--accent)', borderRadius: 2, opacity: 0.75 }} />
                  </div>
                </div>
              ))}
              {rest > 0 && <Muted>+ {rest} smaller folder{rest === 1 ? '' : 's'} (under 50 MB each)</Muted>}
              {storage.updated_at && <Muted>Folder sizes refresh every 10 minutes.</Muted>}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

function GpuCard({ agent, ollamaLoaded, desktop }) {
  const gpu = agent.gpu;
  return (
    <Card title="GPU" desktop={desktop} note={gpu?.name}>
      {gpu?.error ? (
        <div style={{ fontSize: 14, color: WARN }}>{gpu.error}</div>
      ) : (
        <>
          <Meter label="VRAM" pct={(gpu.memory_used / gpu.memory_total) * 100} right={`${fmtBytes(gpu.memory_used)} of ${fmtBytes(gpu.memory_total)}`} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14 }}>
            <Stat label="Busy" value={`${Math.round(gpu.utilization_percent ?? 0)}%`} />
            <Stat label="Temp" value={gpu.temperature_c != null ? `${Math.round(gpu.temperature_c)}°C` : '—'} />
            <Stat label="Power" value={gpu.power_watts != null ? `${Math.round(gpu.power_watts)} W` : '—'} />
          </div>
          <Muted>Driver {gpu.driver}</Muted>
        </>
      )}
      <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Loaded in Ollama</div>
      {ollamaLoaded.length === 0 ? (
        <Muted>No model loaded — the GPU is free.</Muted>
      ) : (
        ollamaLoaded.map((m) => (
          <div key={m.name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, gap: 8 }}>
            <span style={{ color: 'var(--text)', overflowWrap: 'anywhere' }}>{m.name}</span>
            <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>{fmtBytes(m.size_vram)} in VRAM</span>
          </div>
        ))
      )}
    </Card>
  );
}

function ServicesCard({ agent, probes, desktop }) {
  return (
    <Card title="Services" desktop={desktop}>
      <div>
        {(agent?.services || []).map((s) => (
          <Row key={s.name} left={s.name} color={s.state === 'active' ? GOOD : BAD} right={s.state === 'active' ? `up ${fmtDuration(s.since_seconds)}` : s.state} sub={s.restarts > 0 ? `${s.restarts} restart${s.restarts === 1 ? '' : 's'}` : undefined} />
        ))}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>Answering?</div>
      <div>
        {probes.map((p) => (
          <Row key={p.name} left={p.name} color={p.ok ? GOOD : BAD} right={p.ok ? `${p.ms} ms` : p.detail} />
        ))}
      </div>
    </Card>
  );
}

function ContainersCard({ agent, desktop }) {
  const docker = agent.docker;
  const k3s = agent.k3s;
  return (
    <Card title="Containers" desktop={desktop}>
      <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Docker</div>
      {docker?.error ? (
        <Muted>{docker.error}</Muted>
      ) : docker?.containers?.length ? (
        <div>
          {docker.containers.map((c) => (
            <Row
              key={c.name}
              left={c.name}
              sub={c.image}
              color={c.state === 'running' && !c.unhealthy ? GOOD : BAD}
              right={c.status}
            />
          ))}
        </div>
      ) : (
        <Muted>No containers.</Muted>
      )}

      <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 4 }}>K3s pods</div>
      {k3s?.error ? (
        <Muted>Pod view needs a one-time setup: {k3s.error}.</Muted>
      ) : k3s?.pods?.length ? (
        <div>
          {k3s.pods.map((p) => (
            <Row
              key={`${p.namespace}/${p.name}`}
              left={p.name}
              sub={`${p.namespace}${p.reason ? ` · ${p.reason}` : ''}${p.restarts ? ` · ${p.restarts} restarts` : ''}`}
              color={p.ok ? GOOD : BAD}
              right={`${p.phase} ${p.ready} · ${fmtDuration(p.age_seconds)}`}
            />
          ))}
        </div>
      ) : (
        <Muted>No pods.</Muted>
      )}

      {k3s?.cronjobs?.length > 0 && (
        <>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 4 }}>Scheduled jobs</div>
          <div>
            {k3s.cronjobs.map((j) => {
              const limit = cronPeriodSeconds(j.schedule) * 2.5;
              const stale = !j.suspended && (j.last_success_age_seconds == null ? j.last_schedule_age_seconds != null : j.last_success_age_seconds > limit);
              return (
                <Row
                  key={`${j.namespace}/${j.name}`}
                  left={j.name}
                  sub={j.schedule}
                  color={j.suspended ? 'var(--text-faint)' : stale ? WARN : GOOD}
                  right={j.suspended ? 'suspended' : `ok ${fmtAge(j.last_success_age_seconds)}`}
                />
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
}

function BackupsCard({ agent, desktop }) {
  const b = agent.backups;
  const age = b?.latest?.age_seconds;
  const color = b?.error || !b?.latest ? WARN : age > 36 * 3600 ? WARN : GOOD;
  return (
    <Card title="Backups" desktop={desktop}>
      {b?.error ? (
        <Muted>{b.error}</Muted>
      ) : !b?.latest ? (
        <Muted>No backups found in {b?.dir}.</Muted>
      ) : (
        <Row left="Planner database" sub={b.latest.name} color={color} right={`${fmtAge(age)} · ${fmtBytes(b.latest.bytes)}`} />
      )}
      {b?.count > 0 && <Muted>{b.count} backups kept.</Muted>}
    </Card>
  );
}

// ---- page -----------------------------------------------------------------

export default function SystemView({ onOpenDrawer, active }) {
  const isMobile = useIsMobile();
  const [data, setData] = useState(null);
  const [fetchError, setFetchError] = useState(false);
  const [loadedAt, setLoadedAt] = useState(null);
  const inFlight = useRef(false);

  async function refresh() {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      setData(await getSystem());
      setFetchError(false);
      setLoadedAt(Date.now());
    } catch {
      setFetchError(true);
    } finally {
      inFlight.current = false;
    }
  }

  // Views stay mounted, so only poll (and only fetch) while this one is showing.
  useEffect(() => {
    if (!active) return undefined;
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    window.addEventListener('hermes:wake', refresh);
    return () => {
      clearInterval(interval);
      window.removeEventListener('hermes:wake', refresh);
    };
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  const issues = data ? findIssues(data) : [];
  const worst = issues.some((i) => i.level === 'bad') ? BAD : issues.length ? WARN : GOOD;
  const summary = !data ? '' : issues.length === 0 ? 'All systems normal' : `${issues.length} thing${issues.length === 1 ? '' : 's'} need${issues.length === 1 ? 's' : ''} attention`;
  const desktop = !isMobile;
  const pad = isMobile ? 14 : 24;
  const agent = data?.agent;

  const pill = data && (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: isMobile ? 14 : 16, fontWeight: 600, color: worst, textShadow: `0 0 10px ${worst}` }}>
      <Dot color={worst} />
      {summary}
    </div>
  );

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <TopBar title="System" onOpenDrawer={onOpenDrawer}>
        {pill}
      </TopBar>

      <div style={{ flex: 1, overflowY: 'auto', padding: `${pad}px ${pad}px calc(${pad}px + env(safe-area-inset-bottom))` }}>
        <div style={{ maxWidth: isMobile ? 720 : 1240, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: isMobile ? 14 : 18 }}>
          {!data && <Muted>{fetchError ? 'Couldn’t load system status.' : 'Loading…'}</Muted>}

          {fetchError && data && (
            <div style={{ fontSize: 13.5, color: WARN }}>Couldn’t refresh just now — showing the last reading{loadedAt ? ` from ${fmtAge((Date.now() - loadedAt) / 1000)}` : ''}.</div>
          )}

          {issues.length > 0 && (
            <section style={{ background: 'var(--panel)', border: `1px solid ${worst}`, borderRadius: 14, padding: 14, boxShadow: `0 0 20px -10px ${worst}` }}>
              <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: worst, marginBottom: 6 }}>Needs attention</div>
              {issues.map((i, idx) => (
                <div key={idx} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 0', fontSize: 14.5, color: 'var(--text)' }}>
                  <Dot color={i.level === 'bad' ? BAD : WARN} />
                  {i.text}
                </div>
              ))}
            </section>
          )}

          {data && (
            <div style={desktop ? { columnWidth: 320, columnGap: 18 } : { display: 'flex', flexDirection: 'column', gap: 14 }}>
              {agent ? (
                <>
                  <OverviewCard agent={agent} desktop={desktop} />
                  <StorageCard agent={agent} desktop={desktop} />
                  <GpuCard agent={agent} ollamaLoaded={data.ollama_loaded} desktop={desktop} />
                </>
              ) : (
                <Card title="Server" desktop={desktop}>
                  <Muted>No host details: the status service on the homelab isn’t answering, so only the checks below are available.</Muted>
                </Card>
              )}
              <ServicesCard agent={agent} probes={data.probes} desktop={desktop} />
              {agent && <ContainersCard agent={agent} desktop={desktop} />}
              {agent && <BackupsCard agent={agent} desktop={desktop} />}
            </div>
          )}

          {data && loadedAt && <Muted>Updated {fmtAge((Date.now() - loadedAt) / 1000)} · refreshes every 15 seconds while this page is open.</Muted>}
        </div>
      </div>
    </div>
  );
}
