export async function getModels() {
  const res = await fetch('/models');
  const data = await res.json();
  return data.models;
}

export async function listConversations() {
  const res = await fetch('/conversations');
  const data = await res.json();
  return data.conversations;
}

export async function getConversation(id) {
  const res = await fetch('/conversations/' + id);
  if (!res.ok) return null;
  return res.json();
}

export async function renameConversation(id, title) {
  await fetch('/conversations/' + id, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id) {
  await fetch('/conversations/' + id, { method: 'DELETE' });
}

export async function listTasks(status = 'open') {
  const res = await fetch('/tasks?status=' + status);
  const data = await res.json();
  return data.tasks;
}

export async function createTask({ title, quadrant, dueDate, notes }) {
  const res = await fetch('/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, quadrant, due_date: dueDate || null, notes: notes || null }),
  });
  return res.json();
}

export async function updateTask(id, updates) {
  await fetch(`/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

export async function completeTask(id) {
  await fetch(`/tasks/${id}/complete`, { method: 'PATCH' });
}

export async function deleteTask(id) {
  await fetch(`/tasks/${id}`, { method: 'DELETE' });
}

export async function listHabits() {
  const res = await fetch('/habits');
  const data = await res.json();
  return data.habits;
}

export async function logHabit(name) {
  const res = await fetch('/habits/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return res.json();
}

export async function setHabitDay(habitId, date, logged) {
  await fetch(`/habits/${habitId}/log`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, logged }),
  });
}
