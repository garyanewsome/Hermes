const REQUEST_TIMEOUT_MS = 15000;

// Thin wrapper around fetch so every API call reacts the same way to a
// 401 (session cookie missing or expired) — dispatching an event App.jsx
// listens for to drop back to the login screen, instead of each call site
// having to check for it individually.
//
// Also times out and retries once. Without this, a stale connection —
// browser-cached keep-alive left over from a long-idle tab, or the pod
// mid-restart during a deploy — just hangs forever with zero recovery
// short of a manual page refresh (reported live: "every page... if idle
// too long or sometimes on a restart it just seems stuck"). A timed-out
// attempt is essentially always a dead connection, not a slow server, so
// one retry on a fresh connection is the right response, not an error.
async function apiFetch(url, opts, _attempt = 1) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...opts, signal: controller.signal });
    if (res.status === 401) {
      window.dispatchEvent(new Event('hermes:unauthorized'));
    }
    return res;
  } catch (err) {
    if (err.name === 'AbortError' && _attempt === 1) {
      return apiFetch(url, opts, 2);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// login/logout/checkAuth deliberately don't go through apiFetch — a wrong
// password legitimately 401s and shouldn't fire the same
// "session expired, show login" event apiFetch dispatches for everything
// else. Same timeout+retry-once protection though: checkAuth in particular
// runs on every page load before anything else, so a hung connection here
// would otherwise show the "still checking" blank screen forever — the
// exact "every page... on idle or a restart it just seems stuck" report
// this fix addresses.
async function fetchWithTimeout(url, opts, _attempt = 1) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } catch (err) {
    if (err.name === 'AbortError' && _attempt === 1) {
      return fetchWithTimeout(url, opts, 2);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function login(password) {
  const res = await fetchWithTimeout('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  return res.ok;
}

export async function logout() {
  await fetchWithTimeout('/logout', { method: 'POST' });
}

export async function checkAuth() {
  const res = await fetchWithTimeout('/auth/check');
  return res.ok;
}

export async function getModels() {
  const res = await apiFetch('/models');
  const data = await res.json();
  return data.models;
}

export async function listConversations() {
  const res = await apiFetch('/conversations');
  const data = await res.json();
  return data.conversations;
}

export async function getConversation(id) {
  const res = await apiFetch('/conversations/' + id);
  if (!res.ok) return null;
  return res.json();
}

export async function renameConversation(id, title) {
  await apiFetch('/conversations/' + id, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id) {
  await apiFetch('/conversations/' + id, { method: 'DELETE' });
}

export async function deleteMessage(conversationId, messageId) {
  await apiFetch(`/conversations/${conversationId}/messages/${messageId}`, { method: 'DELETE' });
}

// resendMessage isn't here — like /chat, it's a streaming response, so
// ChatView.jsx calls it directly via fetch+reader rather than through this
// file's JSON-returning apiFetch wrapper.

export async function listTasks(status = 'open') {
  const res = await apiFetch('/tasks?status=' + status);
  const data = await res.json();
  return data.tasks;
}

export async function createTask({ title, quadrant, dueDate, notes }) {
  const res = await apiFetch('/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, quadrant, due_date: dueDate || null, notes: notes || null }),
  });
  return res.json();
}

export async function updateTask(id, updates) {
  await apiFetch(`/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function completeTask(id) {
  await apiFetch(`/tasks/${id}/complete`, { method: 'PATCH' });
}

export async function reopenTask(id) {
  await apiFetch(`/tasks/${id}/reopen`, { method: 'PATCH' });
}

export async function deleteTask(id) {
  await apiFetch(`/tasks/${id}`, { method: 'DELETE' });
}

export async function listHabits() {
  const res = await apiFetch('/habits');
  const data = await res.json();
  return data.habits;
}

export async function logHabit(name) {
  const res = await apiFetch('/habits/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return res.json();
}

export async function setHabitDay(habitId, date, logged) {
  await apiFetch(`/habits/${habitId}/log`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, logged }),
  });
}

export async function deleteHabit(habitId) {
  await apiFetch(`/habits/${habitId}`, { method: 'DELETE' });
}

export async function listTodoLists() {
  const res = await apiFetch('/todo-lists');
  const data = await res.json();
  return data.lists;
}

export async function createTodoList(name) {
  const res = await apiFetch('/todo-lists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return res.json();
}

export async function updateTodoList(listId, updates) {
  await apiFetch(`/todo-lists/${listId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function deleteTodoList(listId) {
  await apiFetch(`/todo-lists/${listId}`, { method: 'DELETE' });
}

export async function listTodoItems(listId) {
  const res = await apiFetch(`/todo-lists/${listId}/items`);
  const data = await res.json();
  return data.items;
}

export async function createTodoItem(listId, text) {
  const res = await apiFetch(`/todo-lists/${listId}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return res.json();
}

export async function updateTodoItem(itemId, updates) {
  await apiFetch(`/todo-items/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function deleteTodoItem(itemId) {
  await apiFetch(`/todo-items/${itemId}`, { method: 'DELETE' });
}

export async function listNotes() {
  const res = await apiFetch('/notes');
  const data = await res.json();
  return data.notes;
}

export async function createNote() {
  const res = await apiFetch('/notes', { method: 'POST' });
  return res.json();
}

export async function updateNote(noteId, content) {
  await apiFetch(`/notes/${noteId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
}

export async function deleteNote(noteId) {
  await apiFetch(`/notes/${noteId}`, { method: 'DELETE' });
}

export async function listSketches() {
  const res = await apiFetch('/sketches');
  const data = await res.json();
  return data.sketches;
}

export async function createSketch(width, height) {
  const res = await apiFetch('/sketches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ width, height }),
  });
  return res.json();
}

export async function updateSketch(sketchId, updates) {
  await apiFetch(`/sketches/${sketchId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function deleteSketch(sketchId) {
  await apiFetch(`/sketches/${sketchId}`, { method: 'DELETE' });
}
