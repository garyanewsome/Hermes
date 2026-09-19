import { useEffect, useRef, useState } from 'react';
import TopBar from '../components/TopBar.jsx';
import useIsMobile from '../hooks/useIsMobile.js';
import { listSketches, createSketch, updateSketch, deleteSketch } from '../api.js';

const SAVE_DEBOUNCE_MS = 800;
const CANVAS_W = 1000;
const CANVAS_H = 1400;
const COLORS = ['#111111', '#e03131', '#2f6fed', '#2f9e44', '#f08c00'];
const WIDTHS = [
  { label: 'Thin', value: 3 },
  { label: 'Medium', value: 7 },
  { label: 'Thick', value: 14 },
];
const ERASER_WIDTH = 32;

// Effective on-canvas width for a point: pressure (0-1, 0.5 for a mouse
// with no real pressure) tapers the stroke rather than always drawing at
// full width — a flat pressure still reads fine, it just doesn't taper.
function widthAt(baseWidth, pressure) {
  return Math.max(1, baseWidth * (0.35 + 0.65 * (pressure ?? 0.5)));
}

function drawStroke(ctx, stroke) {
  const color = stroke.tool === 'erase' ? '#ffffff' : stroke.color;
  const points = stroke.points;
  if (points.length === 0) return;
  if (points.length === 1) {
    const p = points[0];
    ctx.beginPath();
    ctx.fillStyle = color;
    ctx.arc(p.x, p.y, widthAt(stroke.width, p.pressure) / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    ctx.lineWidth = widthAt(stroke.width, (a.pressure + b.pressure) / 2);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }
}

function renderStrokes(canvas, strokes) {
  const ctx = canvas.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (const stroke of strokes) drawStroke(ctx, stroke);
}

// Erasing is just drawing in white rather than true alpha compositing —
// the canvas is always opaque white anyway, and it means export (SVG in
// particular) needs no special masking logic: an erase stroke is exactly
// like a color stroke, just white.
function strokesToSvg(strokes, width, height) {
  const parts = [`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">`];
  parts.push(`<rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"/>`);
  for (const stroke of strokes) {
    const color = stroke.tool === 'erase' ? '#ffffff' : stroke.color;
    if (stroke.points.length === 1) {
      const p = stroke.points[0];
      parts.push(`<circle cx="${p.x}" cy="${p.y}" r="${widthAt(stroke.width, p.pressure) / 2}" fill="${color}"/>`);
      continue;
    }
    const avgPressure = stroke.points.reduce((s, p) => s + (p.pressure ?? 0.5), 0) / stroke.points.length;
    const w = widthAt(stroke.width, avgPressure);
    const pointsAttr = stroke.points.map((p) => `${p.x},${p.y}`).join(' ');
    parts.push(
      `<polyline points="${pointsAttr}" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`
    );
  }
  parts.push('</svg>');
  return parts.join('');
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function timeAgo(isoString) {
  if (!isoString) return '';
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function Thumbnail({ sketch }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = sketch.width;
    canvas.height = sketch.height;
    renderStrokes(canvas, sketch.strokes);
  }, [sketch]);
  return <canvas ref={canvasRef} style={{ width: 56, height: (56 * sketch.height) / sketch.width, borderRadius: 4, border: '1px solid var(--border)', flexShrink: 0 }} />;
}

function ConfirmDeleteSketch({ onCancel, onConfirm }) {
  return (
    <div onClick={onCancel} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); onConfirm(); }}
        style={{ width: 320, maxWidth: '90vw', background: 'var(--bg)', border: '1px solid var(--accent)', boxShadow: '0 0 20px var(--accent-glow)', borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        <div style={{ fontSize: 14, color: 'var(--text)' }}>Delete this sketch? This can't be undone.</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={onCancel} style={{ background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '7px 14px', fontSize: 13 }}>Cancel</button>
          <button type="submit" autoFocus style={{ background: '#ff6b6b', border: 'none', color: '#2b0808', borderRadius: 8, padding: '7px 14px', fontSize: 13, fontWeight: 600 }}>Delete</button>
        </div>
      </form>
    </div>
  );
}

function ConfirmClear({ onCancel, onConfirm }) {
  return (
    <div onClick={onCancel} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); onConfirm(); }}
        style={{ width: 320, maxWidth: '90vw', background: 'var(--bg)', border: '1px solid var(--accent)', boxShadow: '0 0 20px var(--accent-glow)', borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}
      >
        <div style={{ fontSize: 14, color: 'var(--text)' }}>Clear the whole canvas? This can't be undone.</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={onCancel} style={{ background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)', borderRadius: 8, padding: '7px 14px', fontSize: 13 }}>Cancel</button>
          <button type="submit" autoFocus style={{ background: '#ff6b6b', border: 'none', color: '#2b0808', borderRadius: 8, padding: '7px 14px', fontSize: 13, fontWeight: 600 }}>Clear</button>
        </div>
      </form>
    </div>
  );
}

function SketchList({ sketches, activeId, onSelect, onCreate, onDelete, isMobile, mobileOpen, onMobileClose }) {
  const [confirmingDeleteId, setConfirmingDeleteId] = useState(null);

  if (isMobile && !mobileOpen) return null;

  return (
    <>
      {isMobile && <div onClick={onMobileClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 40 }} />}
      <div
        style={
          isMobile
            ? { position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(300px, 85vw)', background: 'var(--panel)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', zIndex: 41, paddingTop: 'env(safe-area-inset-top)' }
            : { width: 260, flexShrink: 0, background: 'var(--panel)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column' }
        }
      >
        <div style={{ padding: 12 }}>
          <button
            onClick={async () => {
              const sketch = await onCreate();
              onSelect(sketch.id);
              if (isMobile) onMobileClose();
            }}
            style={{ width: '100%', padding: '9px 12px', background: 'var(--accent)', color: 'var(--accent-text)', border: 'none', borderRadius: 8, fontSize: 13.5, textAlign: 'left', boxShadow: '0 0 14px var(--accent-glow)' }}
          >
            + New sketch
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {sketches.length === 0 && <div style={{ padding: 10, fontSize: 12, color: 'var(--text-faint)' }}>No sketches yet.</div>}
          {sketches.map((s) => (
            <div
              key={s.id}
              onClick={() => { onSelect(s.id); if (isMobile) onMobileClose(); }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: 8,
                borderRadius: 8,
                cursor: 'pointer',
                marginBottom: 4,
                background: s.id === activeId ? 'rgba(255,255,255,0.06)' : 'transparent',
                boxShadow: s.id === activeId ? 'inset 2px 0 0 var(--accent)' : 'none',
              }}
            >
              <Thumbnail sketch={s} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: s.id === activeId ? 'var(--text)' : '#c7c8cc', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {s.title || 'Untitled sketch'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{timeAgo(s.updated_at)}</div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(s.id); }}
                aria-label="Delete sketch"
                title="Delete sketch"
                style={{ flexShrink: 0, width: 18, height: 18, background: 'transparent', border: 'none', color: 'var(--text-faint)', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                  <path d="M2.5 3.5H11.5M5.5 3.5V2.2C5.5 1.9 5.7 1.7 6 1.7H8C8.3 1.7 8.5 1.9 8.5 2.2V3.5M5.8 6V10M8.2 6V10M3.3 3.5L3.8 11.3C3.8 11.7 4.2 12 4.6 12H9.4C9.8 12 10.2 11.7 10.2 11.3L10.7 3.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </div>
      {confirmingDeleteId != null && (
        <ConfirmDeleteSketch onCancel={() => setConfirmingDeleteId(null)} onConfirm={() => { onDelete(confirmingDeleteId); setConfirmingDeleteId(null); }} />
      )}
    </>
  );
}

export default function SketchView({ onOpenDrawer }) {
  const [sketches, setSketches] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [strokes, setStrokes] = useState([]);
  const [redoStack, setRedoStack] = useState([]);
  const [color, setColor] = useState(COLORS[0]);
  const [penWidth, setPenWidth] = useState(WIDTHS[1].value);
  const [erasing, setErasing] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const isMobile = useIsMobile();

  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const currentStrokeRef = useRef(null);
  const saveTimerRef = useRef(null);
  const activeIdRef = useRef(null);
  const strokesRef = useRef([]);

  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);
  useEffect(() => { strokesRef.current = strokes; }, [strokes]);

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    const fetched = await listSketches();
    setSketches(fetched);
    setActiveId((current) => {
      if (current != null && fetched.some((s) => s.id === current)) return current;
      return fetched[0]?.id ?? null;
    });
  }

  useEffect(() => {
    const sketch = sketches.find((s) => s.id === activeId);
    setStrokes(sketch ? sketch.strokes : []);
    setRedoStack([]);
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeSketch = sketches.find((s) => s.id === activeId);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !activeSketch) return;
    canvas.width = activeSketch.width;
    canvas.height = activeSketch.height;
    renderStrokes(canvas, strokes);
  }, [strokes, activeSketch]);

  function flushSave(id, currentStrokes) {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    if (id == null) return;
    updateSketch(id, { strokes: currentStrokes });
    setSketches((prev) => {
      const updated = prev.map((s) => (s.id === id ? { ...s, strokes: currentStrokes, updated_at: new Date().toISOString() } : s));
      return [...updated].sort((a, b) => (a.id === id ? -1 : b.id === id ? 1 : 0));
    });
  }

  function scheduleSave() {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => flushSave(activeIdRef.current, strokesRef.current), SAVE_DEBOUNCE_MS);
  }

  function handleSelect(id) {
    flushSave(activeId, strokes);
    setActiveId(id);
  }

  async function handleCreate() {
    flushSave(activeId, strokes);
    const sketch = await createSketch(CANVAS_W, CANVAS_H);
    setSketches((prev) => [sketch, ...prev]);
    return sketch;
  }

  async function handleDelete(id) {
    if (saveTimerRef.current && id === activeId) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    setSketches((prev) => prev.filter((s) => s.id !== id));
    if (activeId === id) setActiveId(null);
    await deleteSketch(id);
  }

  function canvasPoint(e) {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
      pressure: e.pressure > 0 ? e.pressure : 0.5,
    };
  }

  function handlePointerDown(e) {
    if (!activeSketch) return;
    try {
      e.target.setPointerCapture(e.pointerId);
    } catch {
      // Capture is a nice-to-have (keeps the stroke going if the pointer
      // slides off the canvas while still down) — a failure here shouldn't
      // stop the stroke from being recorded at all.
    }
    const point = canvasPoint(e);
    currentStrokeRef.current = {
      tool: erasing ? 'erase' : 'pen',
      color,
      width: erasing ? ERASER_WIDTH : penWidth,
      points: [point],
    };
  }

  function handlePointerMove(e) {
    const stroke = currentStrokeRef.current;
    if (!stroke) return;
    const point = canvasPoint(e);
    const ctx = canvasRef.current.getContext('2d');
    const prev = stroke.points[stroke.points.length - 1];
    stroke.points.push(point);
    // Draw just the new segment for live feedback instead of a full
    // redraw on every move — a full redraw on each pointermove visibly
    // lags once a sketch has more than a few strokes on it.
    ctx.strokeStyle = stroke.tool === 'erase' ? '#ffffff' : stroke.color;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = widthAt(stroke.width, (prev.pressure + point.pressure) / 2);
    ctx.beginPath();
    ctx.moveTo(prev.x, prev.y);
    ctx.lineTo(point.x, point.y);
    ctx.stroke();
  }

  function handlePointerUp() {
    const stroke = currentStrokeRef.current;
    if (!stroke) return;
    currentStrokeRef.current = null;
    setStrokes((prev) => {
      const next = [...prev, stroke];
      strokesRef.current = next;
      return next;
    });
    setRedoStack([]);
    scheduleSave();
  }

  function handleUndo() {
    if (strokes.length === 0) return;
    const next = strokes.slice(0, -1);
    setRedoStack((prev) => [strokes[strokes.length - 1], ...prev]);
    setStrokes(next);
    strokesRef.current = next;
    scheduleSave();
  }

  function handleRedo() {
    if (redoStack.length === 0) return;
    const [restored, ...rest] = redoStack;
    const next = [...strokes, restored];
    setRedoStack(rest);
    setStrokes(next);
    strokesRef.current = next;
    scheduleSave();
  }

  function handleClear() {
    setConfirmingClear(false);
    setStrokes([]);
    strokesRef.current = [];
    setRedoStack([]);
    scheduleSave();
  }

  function handleExportPng() {
    if (!canvasRef.current) return;
    canvasRef.current.toBlob((blob) => downloadBlob(blob, `${activeSketch?.title || 'sketch'}.png`), 'image/png');
  }

  function handleExportSvg() {
    if (!activeSketch) return;
    const svg = strokesToSvg(strokes, activeSketch.width, activeSketch.height);
    downloadBlob(new Blob([svg], { type: 'image/svg+xml' }), `${activeSketch.title || 'sketch'}.svg`);
  }

  return (
    <div style={{ flex: 1, display: 'flex', minWidth: 0 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar title="Sketch" onOpenDrawer={onOpenDrawer}>
          {isMobile && (
            <button
              onClick={() => setPickerOpen(true)}
              aria-label="Open sketches list"
              style={{ marginLeft: 'auto', width: 34, height: 34, flexShrink: 0, borderRadius: 8, background: 'transparent', border: '1px solid var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <rect x="2" y="2" width="5" height="5" rx="1" stroke="var(--accent)" strokeWidth="1.3" />
                <rect x="9" y="2" width="5" height="5" rx="1" stroke="var(--accent)" strokeWidth="1.3" />
                <rect x="2" y="9" width="5" height="5" rx="1" stroke="var(--accent)" strokeWidth="1.3" />
                <rect x="9" y="9" width="5" height="5" rx="1" stroke="var(--accent)" strokeWidth="1.3" />
              </svg>
            </button>
          )}
        </TopBar>

        {!activeSketch ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-faint)', fontSize: 13, padding: 24, textAlign: 'center' }}>
            {sketches.length === 0 ? 'No sketches yet — create one to get started.' : 'Pick a sketch.'}
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: isMobile ? '8px 12px' : '10px 20px', borderBottom: '1px solid var(--border)' }}>
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() => { setColor(c); setErasing(false); }}
                  aria-label={`Color ${c}`}
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: '50%',
                    background: c,
                    border: !erasing && color === c ? '2px solid var(--accent)' : '2px solid transparent',
                    boxShadow: !erasing && color === c ? '0 0 6px var(--accent-glow)' : 'none',
                    padding: 0,
                  }}
                />
              ))}
              <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border)' }} />
              {WIDTHS.map((w) => (
                <button
                  key={w.value}
                  onClick={() => { setPenWidth(w.value); setErasing(false); }}
                  style={{
                    padding: '4px 10px',
                    fontSize: 12,
                    borderRadius: 6,
                    background: !erasing && penWidth === w.value ? 'var(--accent-wash)' : 'transparent',
                    border: `1px solid ${!erasing && penWidth === w.value ? 'var(--accent)' : 'var(--border-strong)'}`,
                    color: !erasing && penWidth === w.value ? 'var(--text)' : 'var(--text-dim)',
                  }}
                >
                  {w.label}
                </button>
              ))}
              <button
                onClick={() => setErasing((v) => !v)}
                style={{
                  padding: '4px 10px',
                  fontSize: 12,
                  borderRadius: 6,
                  background: erasing ? 'var(--accent-wash)' : 'transparent',
                  border: `1px solid ${erasing ? 'var(--accent)' : 'var(--border-strong)'}`,
                  color: erasing ? 'var(--text)' : 'var(--text-dim)',
                }}
              >
                Eraser
              </button>
              <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--border)' }} />
              <button onClick={handleUndo} disabled={strokes.length === 0} aria-label="Undo" title="Undo" style={{ width: 28, height: 28, background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 6, color: strokes.length === 0 ? 'var(--text-faint)' : 'var(--text-dim)' }}>
                ↶
              </button>
              <button onClick={handleRedo} disabled={redoStack.length === 0} aria-label="Redo" title="Redo" style={{ width: 28, height: 28, background: 'transparent', border: '1px solid var(--border-strong)', borderRadius: 6, color: redoStack.length === 0 ? 'var(--text-faint)' : 'var(--text-dim)' }}>
                ↷
              </button>
              <button onClick={() => setConfirmingClear(true)} style={{ padding: '4px 10px', fontSize: 12, borderRadius: 6, background: 'transparent', border: '1px solid var(--border-strong)', color: 'var(--text-dim)' }}>
                Clear
              </button>
              <div style={{ marginLeft: isMobile ? 0 : 'auto', display: 'flex', gap: 8 }}>
                <button onClick={handleExportPng} style={{ padding: '4px 10px', fontSize: 12, borderRadius: 6, background: 'transparent', border: '1px solid var(--accent-glow)', color: 'var(--accent)' }}>
                  Export PNG
                </button>
                <button onClick={handleExportSvg} style={{ padding: '4px 10px', fontSize: 12, borderRadius: 6, background: 'transparent', border: '1px solid var(--accent-glow)', color: 'var(--accent)' }}>
                  Export SVG
                </button>
              </div>
            </div>

            <div ref={containerRef} style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12, overflow: 'auto' }}>
              <canvas
                ref={canvasRef}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                style={{
                  width: '100%',
                  height: 'auto',
                  maxWidth: `min(100%, calc((100vh - 160px) * ${CANVAS_W / CANVAS_H}))`,
                  aspectRatio: `${CANVAS_W} / ${CANVAS_H}`,
                  touchAction: 'none',
                  borderRadius: 8,
                  boxShadow: '0 0 0 1px var(--border)',
                  background: '#ffffff',
                }}
              />
            </div>
          </>
        )}
      </div>

      <SketchList
        sketches={sketches}
        activeId={activeId}
        onSelect={handleSelect}
        onCreate={handleCreate}
        onDelete={handleDelete}
        isMobile={isMobile}
        mobileOpen={pickerOpen}
        onMobileClose={() => setPickerOpen(false)}
      />

      {confirmingClear && <ConfirmClear onCancel={() => setConfirmingClear(false)} onConfirm={handleClear} />}
    </div>
  );
}
