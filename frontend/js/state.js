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

export function channelById(id) {
  return state.channels.find((c) => c.id === id);
}

export function gatewayById(id) {
  return state.gateways.find((g) => g.id === id);
}
