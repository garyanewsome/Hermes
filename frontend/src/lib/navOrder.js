import { useEffect, useState } from 'react';
import { getNavOrder, saveNavOrder } from '../api.js';

// The menu order lives on the server. A copy is kept in this browser so the
// menu is already right after a refresh, instead of drawing the default order
// and then shifting once the request comes back.
const CACHE_KEY = 'naradi:navOrder';
const CHANGED = 'naradi:nav-order';

function readCache() {
  try {
    const saved = JSON.parse(localStorage.getItem(CACHE_KEY));
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

let latest = null; // survives even when storage is blocked

function publish(order) {
  latest = order;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(order));
  } catch {
    // Private browsing: the order still applies until the page is reloaded.
  }
  window.dispatchEvent(new Event(CHANGED));
}

// Saves run one after another, so quick moves can't land out of order.
let saving = Promise.resolve();
let changes = 0;

function refresh() {
  const seen = changes;
  return saving.then(getNavOrder).then((order) => {
    // A move made while this was in flight is newer than the answer.
    if (seen === changes) publish(order);
  });
}

export function setNavOrder(order) {
  changes += 1;
  publish(order);
  const result = saving.then(() => saveNavOrder(order));
  saving = result.catch(() => {});
  return result;
}

// [order, loadFailed]. Fetches again whenever refreshKey changes.
export function useNavOrder(refreshKey) {
  const [order, setOrder] = useState(() => latest ?? readCache());
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const onChange = () => setOrder(latest);
    window.addEventListener(CHANGED, onChange);
    return () => window.removeEventListener(CHANGED, onChange);
  }, []);

  useEffect(() => {
    // If this fails the last known order stays, and the menu still works.
    refresh().then(
      () => setFailed(false),
      () => setFailed(true)
    );
  }, [refreshKey]);

  return [order, failed];
}
