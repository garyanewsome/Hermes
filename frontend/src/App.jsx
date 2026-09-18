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

      <NavDrawer open={drawerOpen} activeView={view} onNavigate={setView} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
