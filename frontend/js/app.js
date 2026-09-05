import { api } from "./api.js";
import { startWS, stopWS, onWSMessage } from "./ws.js";
import { refreshAll, currentUser, setCurrentUser } from "./state.js";
import { toast } from "./toast.js";
import { t, getLocale, setLocale, applyStaticDom } from "./i18n.js";
import { renderEventText } from "./eventText.js";

import { mountDashboard } from "./views/dashboard.js";
import { mountDevices } from "./views/devices.js";
import { mountChannels } from "./views/channels.js";
import { mountGeofences } from "./views/geofences.js";
import { mountAlerts } from "./views/alerts.js";
import { mountCameras } from "./views/cameras.js";
import { mountSettings } from "./views/settings.js";
import { mountAdmin } from "./views/admin.js";

const views = {
  dashboard: mountDashboard,
  devices: mountDevices,
  channels: mountChannels,
  geofences: mountGeofences,
  alerts: mountAlerts,
  cameras: mountCameras,
  settings: mountSettings,
  admin: mountAdmin,
};

const viewRoot = document.getElementById("view-root");
let currentUnmount = null;

async function showView(name) {
  if (name === "admin" && currentUser()?.role !== "admin") name = "dashboard";
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  if (currentUnmount) {
    try { currentUnmount(); } catch { /* noop */ }
    currentUnmount = null;
  }
  viewRoot.innerHTML = "";
  const mount = views[name] || views.dashboard;
  currentUnmount = (await mount(viewRoot)) || null;
  location.hash = name;
}

function wireNav() {
  document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });
}

export function goToView(name) {
  showView(name);
}

function wireLangSwitches() {
  function updateActive() {
    document.querySelectorAll(".lang-switch button").forEach((b) => {
      b.classList.toggle("active", b.dataset.lang === getLocale());
    });
  }
  document.querySelectorAll(".lang-switch button").forEach((b) => {
    b.addEventListener("click", () => {
      setLocale(b.dataset.lang);
      updateActive();
      // keep the account's stored language (used for Telegram text) in sync
      // — only once actually signed in, the login screen has its own switch
      // but no session yet to attach a language preference to.
      if (currentUser()) {
        api.put(`/api/settings/language?language=${b.dataset.lang}`).catch(() => {});
      }
    });
  });
  updateActive();
}

async function bootApp(me) {
  if (!me) me = await api.get("/api/me");
  setCurrentUser(me);
  document.getElementById("nav-admin").hidden = me.role !== "admin";
  document.getElementById("login-screen").hidden = true;
  document.getElementById("app").hidden = false;
  wireNav();
  await refreshAll().catch((e) => toast(e.message, "error"));
  startWS();
  onWSMessage((msg) => {
    if (msg.type === "alert") {
      toast(renderEventText(msg.event_type, msg.message), "error");
    }
  });
  const initial = (location.hash || "#dashboard").slice(1);
  showView(views[initial] ? initial : "dashboard");
}

// Guards against the startup "/api/me" probe clobbering the UI after a
// faster, user-initiated login/logout already resolved (e.g. probe was
// in flight when the user submitted the form).
let authEpoch = 0;

function showLogin(message) {
  document.getElementById("app").hidden = true;
  document.getElementById("login-screen").hidden = false;
  document.getElementById("login-form").hidden = false;
  document.getElementById("register-form").hidden = true;
  stopWS();
  const errBox = document.getElementById("login-error");
  if (message) {
    errBox.textContent = message;
    errBox.hidden = false;
  } else {
    errBox.hidden = true;
  }
}

document.getElementById("show-register").addEventListener("click", () => {
  document.getElementById("login-form").hidden = true;
  document.getElementById("register-form").hidden = false;
});
document.getElementById("show-login").addEventListener("click", () => {
  document.getElementById("register-form").hidden = true;
  document.getElementById("login-form").hidden = false;
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  const epoch = ++authEpoch;
  try {
    await api.post("/api/login", {
      username: form.get("username"),
      password: form.get("password"),
    });
    if (epoch !== authEpoch) return;
    await bootApp();
  } catch (err) {
    if (epoch !== authEpoch) return;
    showLogin(err.message || t("login.failed"));
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const btn = e.target.querySelector('button[type="submit"]');
  const errBox = document.getElementById("register-error");
  btn.disabled = true;
  errBox.hidden = true;
  const epoch = ++authEpoch;
  try {
    await api.post("/api/register", {
      username: form.get("username"),
      password: form.get("password"),
    });
    if (epoch !== authEpoch) return;
    await bootApp();
  } catch (err) {
    if (epoch !== authEpoch) return;
    errBox.textContent = err.message || t("register.failed");
    errBox.hidden = false;
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  authEpoch++;
  await api.post("/api/logout").catch(() => {});
  setCurrentUser(null);
  showLogin();
});

applyStaticDom();
wireLangSwitches();

(async function init() {
  const epoch = authEpoch;
  try {
    const me = await api.get("/api/me");
    if (epoch !== authEpoch) return;
    if (me.authenticated) {
      await bootApp(me);
    } else {
      showLogin();
    }
  } catch {
    if (epoch === authEpoch) showLogin();
  }
})();
