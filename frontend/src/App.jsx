import { useEffect, useState } from 'react';
import NavDrawer from './components/NavDrawer.jsx';
import LoginScreen from './components/LoginScreen.jsx';
import ChatView from './views/ChatView.jsx';
import TasksView from './views/TasksView.jsx';
import HabitsView from './views/HabitsView.jsx';
import TodoView from './views/TodoView.jsx';
import NotesView from './views/NotesView.jsx';
import { checkAuth } from './api.js';

export default function App() {
  const [view, setView] = useState('chat');
  const [drawerOpen, setDrawerOpen] = useState(false);
  // null = still checking, so we don't flash the login screen on a normal
  // page load before the /auth/check round trip lands.
  const [authenticated, setAuthenticated] = useState(null);

  useEffect(() => {
    checkAuth().then(setAuthenticated);
    // Any API call anywhere in the app can hit this if the session cookie
    // expires mid-use — drop back to the login screen instead of leaving
    // views stuck silently failing every request.
    const onUnauthorized = () => setAuthenticated(false);
    window.addEventListener('hermes:unauthorized', onUnauthorized);
    return () => window.removeEventListener('hermes:unauthorized', onUnauthorized);
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
        <TodoView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>
      <div style={{ display: view === 'notes' ? 'contents' : 'none' }}>
        <NotesView onOpenDrawer={() => setDrawerOpen(true)} />
      </div>

      <NavDrawer open={drawerOpen} activeView={view} onNavigate={setView} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
