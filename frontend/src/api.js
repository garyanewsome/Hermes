const REQUEST_TIMEOUT_MS = 15000;
// Reads are idempotent and answered in milliseconds, so a read that hasn't
// come back in a few seconds is a dead pooled connection (a phone's NAT or a
// sleeping laptop dropped it silently), not a slow server — waiting the full
// 15s before retrying on a fresh connection was most of the "lag coming back
// from idle." Writes keep the long first attempt: retrying a write that the
// server actually did receive risks applying it twice.
const READ_FIRST_ATTEMPT_TIMEOUT_MS = 4000;

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
  const isRead = !opts || !opts.method || opts.method === 'GET';
  const timeoutMs = isRead && _attempt === 1 ? READ_FIRST_ATTEMPT_TIMEOUT_MS : REQUEST_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
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

export async function uploadAttachment(file) {
  // No Content-Type header set here on purpose — the browser fills in
  // the multipart boundary itself when the body is a FormData, and
  // apiFetch already just spreads whatever opts it's given.
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiFetch('/uploads', { method: 'POST', body: formData });
  if (!res.ok) throw new Error('Upload failed: ' + res.status);
  return res.json();
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
  // Returns the real resulting item — a recurring item's "mark done" can
  // turn into "reset to open, due_date advanced" server-side, so callers
  // need the actual outcome, not just an ack.
  const res = await apiFetch(`/todo-items/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  return res.json();
}

export async function deleteTodoItem(itemId) {
  await apiFetch(`/todo-items/${itemId}`, { method: 'DELETE' });
}

// Open items from every list that are overdue, due today, or due tomorrow —
// the data behind the Today and Tomorrow views.
export async function getTodoAgenda() {
  const res = await apiFetch('/todo-items/agenda');
  return res.json();
}

// Moves a recurring item on to its next occurrence without marking this one
// done. Returns the updated item (its due date is now the next occurrence).
export async function skipTodoItem(itemId) {
  const res = await apiFetch(`/todo-items/${itemId}/skip`, { method: 'POST' });
  if (!res.ok) throw new Error(`Skip failed (${res.status})`);
  return res.json();
}

export async function getWeather() {
  const res = await apiFetch('/weather');
  if (!res.ok) throw new Error(`Weather failed (${res.status})`);
  return res.json();
}

export async function searchWeatherLocations(q) {
  const res = await apiFetch(`/weather/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error(`Search failed (${res.status})`);
  return (await res.json()).results;
}

export async function setWeatherLocation({ name, latitude, longitude }) {
  const res = await apiFetch('/weather/location', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, latitude, longitude }),
  });
  if (!res.ok) throw new Error(`Save failed (${res.status})`);
  return res.json();
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

// `ids` is every note id in its new top-to-bottom order.
export async function reorderNotes(ids) {
  const res = await apiFetch('/notes/order', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) throw new Error(`Reorder failed (${res.status})`);
}

// keepalive lets the request outlive the page — used when flushing a pending
// edit as the tab is being hidden or closed, where a normal fetch can be
// cancelled with the last few typed words still unsent.
export async function updateNote(noteId, content, { keepalive = false } = {}) {
  await apiFetch(`/notes/${noteId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
    keepalive,
  });
}

// A throwaway request to /health with a short timeout, sent when the tab
// wakes from idle: if the pooled connections went stale, this one burns the
// dead connection quickly (and fails fast) so the real requests that follow
// get a fresh one instead of each hanging on its own dead socket.
export async function pingHealth() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3000);
  try {
    await fetch('/health', { signal: controller.signal, cache: 'no-store' });
  } catch {
    // Timed out or offline — the follow-up requests have their own retry.
  } finally {
    clearTimeout(timer);
  }
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
