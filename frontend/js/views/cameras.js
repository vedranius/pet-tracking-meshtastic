import { api } from "../api.js";
import { toast } from "../toast.js";
import { openModal, confirmDialog } from "../util.js";
import { t } from "../i18n.js";

export async function mountCameras(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header">
        <h2>📹 ${t("nav.cameras")}</h2>
        <button class="btn btn-primary btn-sm" id="add-camera">+ ${t("cameras.add")}</button>
      </div>
      <p class="muted" style="font-size:13px;margin-top:-6px">${t("cameras.hint")}</p>
      <div id="camera-list"></div>
    </div>
  `;

  const listEl = document.getElementById("camera-list");
  const players = [];

  container.querySelector("#add-camera").addEventListener("click", () => openCameraModal());

  let cameras = [];

  async function loadCameras() {
    try {
      cameras = await api.get("/api/cameras");
    } catch (err) {
      listEl.innerHTML = `<div class="list-empty">${t("cameras.fetch_failed", { error: err.message })}</div>`;
      return;
    }
    renderList();
  }

  function renderList() {
    for (const hls of players.splice(0)) {
      try { hls.destroy(); } catch { /* noop */ }
    }
    if (!cameras.length) {
      listEl.innerHTML = `<div class="list-empty">${t("cameras.none")}</div>`;
      return;
    }
    listEl.innerHTML = cameras.map((c) => `
      <div class="card camera-card" data-cam="${c.id}">
        <div class="card-row">
          <h3 style="margin:0">${escapeHtml(c.name)}</h3>
          <span class="badge badge-mut" data-status="${c.id}">${t("cameras.stopped")}</span>
        </div>
        <div class="camera-video-wrap">
          <video data-video="${c.id}" playsinline muted controls></video>
          <button class="btn btn-primary" data-start="${c.id}">▶️ ${t("cameras.start")}</button>
        </div>
        ${c.ptz ? `<div class="ptz-panel" data-ptz-panel="${c.id}">${t("common.loading")}</div>` : ""}
        <div class="card-row" style="margin-top:10px">
          <button class="btn btn-sm" data-edit="${c.id}">${t("common.edit")}</button>
          <button class="btn btn-sm btn-danger" data-del="${c.id}">${t("common.delete")}</button>
        </div>
      </div>
    `).join("");

    for (const cam of cameras) {
      listEl.querySelector(`[data-start="${cam.id}"]`).addEventListener("click", () => startCamera(cam));
      listEl.querySelector(`[data-edit="${cam.id}"]`).addEventListener("click", () => editCamera(cam.id));
      listEl.querySelector(`[data-del="${cam.id}"]`).addEventListener("click", async () => {
        if (!confirmDialog(t("cameras.confirm_delete", { name: cam.name }))) return;
        await api.del(`/api/cameras/${cam.id}`);
        await loadCameras();
        toast(t("cameras.deleted"), "success");
      });
      if (cam.ptz) mountPtz(cam);
    }
  }

  async function editCamera(id) {
    // the list endpoint doesn't return rtsp_url/credentials — fetch the full
    // record lazily only when the user actually opens the edit form.
    let full;
    try {
      full = await api.get(`/api/cameras/${id}/full`);
    } catch {
      full = cameras.find((c) => c.id === id);
    }
    openCameraModal(full);
  }

  function openCameraModal(cam) {
    openModal({
      title: cam ? t("cameras.edit") : t("cameras.add"),
      bodyHtml: `
        <label>${t("cameras.name")} <input name="name" required value="${cam ? escapeHtml(cam.name) : ""}" placeholder="${t("cameras.name_placeholder")}"></label>
        <label>${t("cameras.rtsp_url")} <input name="rtsp_url" required value="${cam ? escapeHtml(cam.rtsp_url || "") : ""}" placeholder="rtsp://user:pass@192.168.1.50:554/stream1"></label>
        <div class="switch-row">
          <span>${t("cameras.is_ptz")}</span>
          <label class="switch"><input type="checkbox" name="is_ptz" id="cam-is-ptz" ${cam && cam.is_ptz ? "checked" : ""}><span class="slider"></span></label>
        </div>
        <div id="ptz-fields" ${cam && cam.is_ptz ? "" : "hidden"}>
          <label>${t("cameras.ptz_host")} <input name="ptz_host" value="${cam && cam.ptz_host ? escapeHtml(cam.ptz_host) : ""}" placeholder="192.168.1.50"></label>
          <label>${t("cameras.ptz_user")} <input name="ptz_user" value="${cam && cam.ptz_user ? escapeHtml(cam.ptz_user) : ""}"></label>
          <label>${t("cameras.ptz_password")} <input type="password" name="ptz_password" value="${cam && cam.ptz_password ? escapeHtml(cam.ptz_password) : ""}"></label>
        </div>
      `,
      onMount: (form) => {
        const ptzToggle = form.querySelector("#cam-is-ptz");
        const ptzFields = form.querySelector("#ptz-fields");
        ptzToggle.addEventListener("change", () => { ptzFields.hidden = !ptzToggle.checked; });
      },
      onSubmit: async (fd) => {
        const isPtz = fd.get("is_ptz") === "on";
        const payload = {
          name: fd.get("name"),
          rtsp_url: fd.get("rtsp_url"),
          is_ptz: isPtz,
          ptz_host: isPtz ? fd.get("ptz_host") || null : null,
          ptz_user: isPtz ? fd.get("ptz_user") || null : null,
          ptz_password: isPtz ? fd.get("ptz_password") || null : null,
        };
        if (cam) await api.put(`/api/cameras/${cam.id}`, payload);
        else await api.post("/api/cameras", payload);
        await loadCameras();
        toast(t("cameras.saved"), "success");
      },
    });
  }

  function setStatus(camId, text, cls) {
    const badge = listEl.querySelector(`[data-status="${camId}"]`);
    if (badge) {
      badge.textContent = text;
      badge.className = `badge ${cls}`;
    }
  }

  function startCamera(cam) {
    const video = listEl.querySelector(`[data-video="${cam.id}"]`);
    const startBtn = listEl.querySelector(`[data-start="${cam.id}"]`);
    const src = `/api/cameras/${cam.id}/hls/index.m3u8`;
    startBtn.disabled = true;
    startBtn.textContent = t("cameras.connecting");
    setStatus(cam.id, t("cameras.connecting"), "badge-warn");

    let hls = null;
    if (window.Hls && window.Hls.isSupported()) {
      hls = new window.Hls({ liveDurationInfinity: true, maxLiveSyncPlaybackRate: 1.5 });
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {});
        setStatus(cam.id, t("cameras.live"), "badge-ok");
        startBtn.hidden = true;
      });
      hls.on(window.Hls.Events.ERROR, (_evt, data) => {
        if (!data.fatal) return;
        setStatus(cam.id, t("cameras.error"), "badge-err");
        toast(t("cameras.stream_failed", { name: cam.name }), "error");
        startBtn.hidden = false;
        startBtn.disabled = false;
        startBtn.textContent = `▶️ ${t("cameras.start")}`;
        hls.destroy();
      });
      hls.loadSource(src);
      hls.attachMedia(video);
      players.push(hls);
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      video.addEventListener("loadedmetadata", () => {
        video.play().catch(() => {});
        setStatus(cam.id, t("cameras.live"), "badge-ok");
        startBtn.hidden = true;
      }, { once: true });
      video.addEventListener("error", () => {
        setStatus(cam.id, t("cameras.error"), "badge-err");
        toast(t("cameras.stream_failed", { name: cam.name }), "error");
        startBtn.hidden = false;
        startBtn.disabled = false;
        startBtn.textContent = `▶️ ${t("cameras.start")}`;
      }, { once: true });
    } else {
      toast(t("cameras.unsupported_browser"), "error");
      startBtn.disabled = false;
      startBtn.textContent = `▶️ ${t("cameras.start")}`;
    }
  }

  async function mountPtz(cam) {
    const panel = listEl.querySelector(`[data-ptz-panel="${cam.id}"]`);
    let cfg;
    try {
      cfg = await api.get(`/api/cameras/${cam.id}/ptz`);
    } catch (err) {
      panel.innerHTML = `<div class="error-text">${t("cameras.ptz_fetch_failed", { error: err.message })}</div>`;
      return;
    }
    renderPtz(cam, panel, cfg);
  }

  function renderPtz(cam, panel, cfg) {
    panel.innerHTML = `
      <div class="ptz-pad">
        <span></span>
        <button class="btn btn-sm" data-dir="up" title="${t("cameras.up")}">⬆️</button>
        <span></span>
        <button class="btn btn-sm" data-dir="left" title="${t("cameras.left")}">⬅️</button>
        <span class="ptz-pad-center">🎥</span>
        <button class="btn btn-sm" data-dir="right" title="${t("cameras.right")}">➡️</button>
        <span></span>
        <button class="btn btn-sm" data-dir="down" title="${t("cameras.down")}">⬇️</button>
        <span></span>
      </div>

      <div class="ptz-presets" data-presets></div>

      <form class="ptz-save-form" data-save-form>
        <input type="text" name="name" placeholder="${t("cameras.preset_name_placeholder")}" required maxlength="40">
        <button type="submit" class="btn btn-sm">💾 ${t("cameras.save_position")}</button>
      </form>

      <label class="ptz-idle-label">
        ${t("cameras.idle_return")}
        <input type="number" min="1" data-idle-input value="${cfg.idle_minutes ?? ""}" placeholder="${t("cameras.idle_return_placeholder")}">
      </label>
    `;

    // Press-and-hold: the motor needs sustained ContinuousMove to actually
    // overcome its own static friction, a single short pulse just gets
    // acknowledged by the camera without visibly moving it. move-stop fires
    // on every plausible "let go" signal (up/cancel/leave/lost-capture) —
    // better to stop a beat early than leave the motor running.
    panel.querySelectorAll("[data-dir]").forEach((btn) => {
      let active = false;

      const start = async (e) => {
        e.preventDefault();
        if (active) return;
        active = true;
        btn.classList.add("ptz-pressed");
        if (btn.setPointerCapture && e.pointerId != null) {
          try { btn.setPointerCapture(e.pointerId); } catch { /* noop */ }
        }
        try {
          await api.post(`/api/cameras/${cam.id}/ptz/move-start`, { direction: btn.dataset.dir });
        } catch (err) {
          toast(err.message, "error");
          active = false;
          btn.classList.remove("ptz-pressed");
        }
      };

      const stop = async () => {
        if (!active) return;
        active = false;
        btn.classList.remove("ptz-pressed");
        try {
          await api.post(`/api/cameras/${cam.id}/ptz/move-stop`, {});
        } catch (err) {
          toast(err.message, "error");
        }
      };

      btn.addEventListener("pointerdown", start);
      btn.addEventListener("pointerup", stop);
      btn.addEventListener("pointercancel", stop);
      btn.addEventListener("pointerleave", stop);
      btn.addEventListener("lostpointercapture", stop);
      btn.addEventListener("contextmenu", (e) => e.preventDefault());
    });

    panel.querySelector("[data-save-form]").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const submitBtn = e.target.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const preset = await api.post(`/api/cameras/${cam.id}/ptz/presets`, { name: fd.get("name") });
        cfg.presets.push(preset);
        renderPresets(cam, panel, cfg);
        e.target.reset();
        toast(t("cameras.position_saved"), "success");
      } catch (err) {
        toast(err.message, "error");
      } finally {
        submitBtn.disabled = false;
      }
    });

    const idleInput = panel.querySelector("[data-idle-input]");
    idleInput.addEventListener("change", async () => {
      const minutes = idleInput.value ? Number(idleInput.value) : null;
      try {
        await api.put(`/api/cameras/${cam.id}/ptz/idle-return`, { minutes });
        cfg.idle_minutes = minutes;
        toast(t("common.saved"), "success");
      } catch (err) {
        toast(err.message, "error");
      }
    });

    renderPresets(cam, panel, cfg);
  }

  function renderPresets(cam, panel, cfg) {
    const el = panel.querySelector("[data-presets]");
    if (!cfg.presets.length) {
      el.innerHTML = `<div class="muted" style="font-size:12px">${t("cameras.no_presets")}</div>`;
      return;
    }
    el.innerHTML = cfg.presets.map((p) => `
      <div class="ptz-preset-row" data-preset-id="${p.id}">
        <span class="ptz-preset-name">${p.id === cfg.default_preset_id ? "⭐ " : ""}${escapeHtml(p.name)}</span>
        <button class="btn btn-sm" data-goto="${p.id}">${t("cameras.go")}</button>
        <button class="btn btn-sm" data-default="${p.id}" title="${t("cameras.set_default")}">⭐</button>
        <button class="btn btn-sm btn-danger" data-del="${p.id}" title="${t("common.delete")}">🗑</button>
      </div>
    `).join("");

    el.querySelectorAll("[data-goto]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await api.post(`/api/cameras/${cam.id}/ptz/presets/${btn.dataset.goto}/goto`, {});
        } catch (err) {
          toast(err.message, "error");
        } finally {
          btn.disabled = false;
        }
      });
    });
    el.querySelectorAll("[data-default]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const presetId = Number(btn.dataset.default);
        try {
          await api.put(`/api/cameras/${cam.id}/ptz/default`, { preset_id: presetId });
          cfg.default_preset_id = presetId;
          renderPresets(cam, panel, cfg);
          toast(t("cameras.default_set"), "success");
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
    el.querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const presetId = Number(btn.dataset.del);
        if (!confirmDialog(t("cameras.confirm_delete_preset"))) return;
        try {
          await api.del(`/api/cameras/${cam.id}/ptz/presets/${presetId}`);
          cfg.presets = cfg.presets.filter((p) => p.id !== presetId);
          if (cfg.default_preset_id === presetId) cfg.default_preset_id = null;
          renderPresets(cam, panel, cfg);
          toast(t("cameras.preset_deleted"), "success");
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });
  }

  await loadCameras();

  return () => {
    for (const hls of players) {
      try { hls.destroy(); } catch { /* noop */ }
    }
  };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
