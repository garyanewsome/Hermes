// Thin wrapper around fetch so every API call reacts the same way to a
// 401 (session cookie missing or expired) — dispatching an event App.jsx
// listens for to drop back to the login screen, instead of each call site
// having to check for it individually.
async function apiFetch(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.dispatchEvent(new Event('hermes:unauthorized'));
  }
  return res;
}

export async function login(password) {
  const res = await fetch('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  return res.ok;
}

export async function logout() {
  await fetch('/logout', { method: 'POST' });
}

export async function checkAuth() {
  const res = await fetch('/auth/check');
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

export async function renameTodoList(listId, name) {
  await apiFetch(`/todo-lists/${listId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
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

export async function setTodoItemDone(itemId, done) {
  await apiFetch(`/todo-items/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ done }),
  });
}

export async function deleteTodoItem(itemId) {
  await apiFetch(`/todo-items/${itemId}`, { method: 'DELETE' });
}
