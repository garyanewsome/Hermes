import { useEffect, useState } from 'react';
import NavDrawer from './components/NavDrawer.jsx';
import LoginScreen from './components/LoginScreen.jsx';
import ChatView from './views/ChatView.jsx';
import TasksView from './views/TasksView.jsx';
import HabitsView from './views/HabitsView.jsx';
import TodoView from './views/TodoView.jsx';
import NotesView from './views/NotesView.jsx';
import SketchView from './views/SketchView.jsx';
import { checkAuth, pingHealth } from './api.js';

const VIEWS = ['chat', 'tasks', 'todo', 'notes', 'habits', 'sketch'];
const LAST_VIEW_KEY = 'hermes:lastView';

function initialView() {
  try {
    const saved = localStorage.getItem(LAST_VIEW_KEY);
    if (VIEWS.includes(saved)) return saved;
  } catch {
    // Private-browsing / storage-blocked — fine, just default to chat.
  }
  return 'chat';
}

export default function App() {
  // "resume where we left off" — a refresh always dropped you back on
  // chat with nothing selected, regardless of which view you were
  // actually on. Persisted per-browser (localStorage, not React state
  // alone), so it survives a full reload, not just navigation within
  // the same load.
  const [view, setViewState] = useState(initialView);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Lifted out of TodoView (which stays mounted always, per the comment
  // below) so the nav drawer can show it too — the point is exactly to
  // notice something's due while looking at a *different* view, not just
  // when already on Todo.
  const [todoAttention, setTodoAttention] = useState({ dueToday: 0, overdue: 0 });

  function setView(next) {
    setViewState(next);
    try {
      localStorage.setItem(LAST_VIEW_KEY, next);
    } catch {
      // Non-fatal if storage isn't available.
    }
  }
  // null = still checking, so we don't flash the login screen on a normal
  // page load before the /auth/check round trip lands.
  const [authenticated, setAuthenticated] = useState(null);

  useEffect(() => {
    // .catch, not just .then: checkAuth still throws if both the request
    // and its one retry fail (see api.js) — without this, that becomes an
    // unhandled rejection and `authenticated` never leaves null, leaving
    // the app on the blank "still checking" screen forever with no way
    // out but a manual refresh. Falling to the login screen at least gives
    // something clickable; a real network problem will show up there too
    // when login's own request fails the same way.
    checkAuth().then(setAuthenticated).catch(() => setAuthenticated(false));
    // Any API call anywhere in the app can hit this if the session cookie
    // expires mid-use — drop back to the login screen instead of leaving
    // views stuck silently failing every request.
    const onUnauthorized = () => setAuthenticated(false);
    window.addEventListener('hermes:unauthorized', onUnauthorized);
    return () => window.removeEventListener('hermes:unauthorized', onUnauthorized);
  }, []);

  useEffect(() => {
    // Coming back to the tab after being idle/backgrounded: every view that
    // polls wakes at once and its first requests go out on connections the
    // network may have silently dropped. Send one cheap, short-timeout
    // request first to burn any dead connection, then tell the views to
    // refresh right away rather than waiting out their own interval.
    let hiddenAt = null;
    const wake = () => {
      pingHealth().then(() => window.dispatchEvent(new Event('hermes:wake')));
    };
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAt = Date.now();
        return;
      }
      const wasIdle = hiddenAt !== null && Date.now() - hiddenAt > 30000;
      hiddenAt = null;
      if (wasIdle) wake();
    };
    const onPageShow = (e) => {
      if (e.persisted) wake();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pageshow', onPageShow);
    window.addEventListener('online', wake);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pageshow', onPageShow);
      window.removeEventListener('online', wake);
    };
  }, []);

  if (authenticated === null) {
    return <div style={{ height: '100%', background: 'var(--bg)' }} />;
  }

  if (!authenticated) {
    return <LoginScreen onSuccess={() => setAuthenticated(true)} />;
  }

  return (
    <div data-view={view} style={{ height: '100%', display: 'flex', background: 'var(--bg)', color: 'var(--text)' }}>
      {/* All three views stay mounted always — conditionally rendering them
          (view === 'chat' && <ChatView/>) unmounts whichever one you leave,
          destroying its local state (which conversation was open and its
          messages, loaded tasks, ...). display:none removes it from layout
          with zero visual/interaction footprint but keeps the component
          (and its state) alive; display:contents on the active one makes
          this wrapper invisible to the outer flex layout, so the view's own
          flex:1 root behaves exactly as if it were a direct child. */}
      <div style={{ display: view === 'chat' ? 'contents' : 'none' }}>
        <ChatView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>
      <div style={{ display: view === 'tasks' ? 'contents' : 'none' }}>
        <TasksView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>
      <div style={{ display: view === 'habits' ? 'contents' : 'none' }}>
        <HabitsView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>
      <div style={{ display: view === 'todo' ? 'contents' : 'none' }}>
        <TodoView onOpenDrawer={() => setDrawerOpen(true)} onAttentionChange={setTodoAttention} />
      </div>
      <div style={{ display: view === 'notes' ? 'contents' : 'none' }}>
        <NotesView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>
      <div style={{ display: view === 'sketch' ? 'contents' : 'none' }}>
        <SketchView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>

      <NavDrawer open={drawerOpen} activeView={view} onNavigate={setView} onClose={() => setDrawerOpen(false)} todoAttention={todoAttention} />
    </div>
  );
}
