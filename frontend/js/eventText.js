// Mirrors backend/app/services/mesh_manager.py's _EVENT_TEMPLATES /
// render_event_text — Event.message is stored as a "::"-delimited template
// id + args so it can be rendered in whichever language the *viewer* has
// selected right now, not baked in at the moment the event happened.
// Keep this in sync with the backend templates.
import { t } from "./i18n.js";

const KEY_BY_TYPE = {
  low_battery: "event.low_battery",
  geofence_enter: "event.geofence_enter",
  geofence_exit: "event.geofence_exit",
  geofence_exit_update: "event.geofence_exit_update",
  offline: "event.offline",
  ring_sent: "event.ring_sent",
};

export function renderEventText(type, message) {
  const parts = String(message ?? "").split("::");
  const key = KEY_BY_TYPE[type];
  if (!key) return message;
  switch (type) {
    case "low_battery":
      return t(key, { name: parts[1], battery: parts[2] });
    case "geofence_enter":
      return t(key, { name: parts[1], fence: parts[2] });
    case "geofence_exit":
    case "geofence_exit_update":
      return t(key, { name: parts[1], fence: parts[2], lat: parts[3], lon: parts[4] });
    case "offline":
      return t(key, { name: parts[1], minutes: parts[2] });
    case "ring_sent":
      return t(key, { name: parts[1] });
    default:
      return message;
  }
}
