import { useState } from 'react';
import NavDrawer from './components/NavDrawer.jsx';
import ChatView from './views/ChatView.jsx';
import TasksView from './views/TasksView.jsx';
import HabitsView from './views/HabitsView.jsx';

export default function App() {
  const [view, setView] = useState('chat');
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div data-view={view} style={{ height: '100%', display: 'flex', background: 'var(--bg)', color: 'var(--text)' }}>
      {view === 'chat' && <ChatView onOpenDrawer={() => setDrawerOpen(true)} />}
      {view === 'tasks' && <TasksView onOpenDrawer={() => setDrawerOpen(true)} />}
      {view === 'habits' && <HabitsView onOpenDrawer={() => setDrawerOpen(true)} />}

      <NavDrawer open={drawerOpen} activeView={view} onNavigate={setView} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
