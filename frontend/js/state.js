import { api } from "./api.js";

export const state = {
  gateways: [],
  channels: [],
  trackers: [],
  user: null,
  listeners: new Set(),
};

export function subscribe(fn) {
  state.listeners.add(fn);
  return () => state.listeners.delete(fn);
}

function notify() {
  for (const fn of state.listeners) fn(state);
}

export function currentUser() {
  return state.user;
}

export function setCurrentUser(user) {
  state.user = user;
  renderCurrentUserBadge(user);
}

// Kept here (rather than in app.js) so any code that updates the account
// (login, or a profile edit in Settings) can just call setCurrentUser again
// and have the topbar reflect it, without an import cycle back into app.js.
function renderCurrentUserBadge(user) {
  const nameEl = document.getElementById("current-user-name");
  const avatarEl = document.getElementById("current-user-avatar");
  if (!nameEl || !avatarEl) return;
  if (!user) {
    nameEl.textContent = "";
    avatarEl.innerHTML = "🧑";
    return;
  }
  nameEl.textContent = user.username;
  avatarEl.innerHTML = user.has_avatar
    ? `<img src="/api/users/${user.id}/avatar?v=${Date.now()}" alt="">`
    : "🧑";
}

export async function refreshGateways() {
  state.gateways = await api.get("/api/gateways");
  notify();
  return state.gateways;
}

export async function refreshChannels() {
  state.channels = await api.get("/api/channels");
  notify();
  return state.channels;
}

export async function refreshTrackers() {
  state.trackers = await api.get("/api/trackers");
  notify();
  return state.trackers;
}

export async function refreshAll() {
  await Promise.all([refreshGateways(), refreshChannels(), refreshTrackers()]);
}

export function trackerById(id) {
  return state.trackers.find((t) => t.id === id);
}

// Trackers this account owns outright — excludes pets shared with them as a
// caretaker, since those only grant read access (see backend/app/services/
// access.py): editing, deleting, radio config, and geofence management all
// stay owner-only, so pages offering those actions should use this instead
// of the full state.trackers list.
export function ownedTrackers() {
  return state.trackers.filter((t) => t.is_owner !== false);
}

export function channelById(id) {
  return state.channels.find((c) => c.id === id);
}

export function gatewayById(id) {
  return state.gateways.find((g) => g.id === id);
}
