import { api } from "../api.js";
import { state, subscribe, refreshGateways, refreshTrackers, channelById, ownedTrackers } from "../state.js";
import { openModal, confirmDialog, timeAgo, el } from "../util.js";
import { toast } from "../toast.js";
import { goToView } from "../app.js";
import { t, onLocaleChange } from "../i18n.js";

function statusLabel(status) {
  return {
    connected: [t("devices.status_connected"), "badge-ok"],
    disconnected: [t("devices.status_disconnected"), "badge-warn"],
    error: [t("devices.status_error"), "badge-err"],
    unknown: [t("devices.status_unknown"), "badge-mut"],
  }[status] || [t("devices.status_unknown"), "badge-mut"];
}

export async function mountDevices(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header">
        <h2>📡 ${t("nav.devices")}</h2>
        <button class="btn btn-sm" id="goto-channels">🔑 ${t("nav.channels")} →</button>
      </div>

      <div class="card-row" style="margin-bottom:8px">
        <h3 style="margin:0">${t("devices.gateways")}</h3>
        <button class="btn btn-primary btn-sm" id="add-gateway">+ ${t("common.add")}</button>
      </div>
      <div id="gateway-list"></div>

      <div class="card-row" style="margin:22px 0 8px">
        <h3 style="margin:0">${t("devices.pets")}</h3>
        <button class="btn btn-primary btn-sm" id="add-tracker">+ ${t("common.add")}</button>
      </div>
      <div id="tracker-list"></div>
    </div>
  `;

  container.querySelector("#goto-channels").addEventListener("click", () => goToView("channels"));
  container.querySelector("#add-gateway").addEventListener("click", () => openGatewayModal());
  container.querySelector("#add-tracker").addEventListener("click", () => openTrackerModal());

  function renderGateways() {
    const listEl = document.getElementById("gateway-list");
    if (!listEl) return;
    if (!state.gateways.length) {
      listEl.innerHTML = `<div class="list-empty">${t("devices.no_gateways")}</div>`;
      return;
    }
    listEl.innerHTML = "";
    for (const gw of state.gateways) {
      const [label, cls] = statusLabel(gw.status);
      const card = el(`
        <div class="card">
          <div class="card-row">
            <div>
              <div class="card-title">${escapeHtml(gw.name)}</div>
              <div class="muted" style="font-size:13px">${escapeHtml(gw.ip_address)} · ${t("devices.last_seen")} ${timeAgo(gw.last_seen)}</div>
              ${gw.last_error ? `<div class="error-text">${escapeHtml(gw.last_error)}</div>` : ""}
            </div>
            <span class="badge ${cls}">${label}</span>
          </div>
          <div class="card-row" style="margin-top:10px">
            <button class="btn btn-sm" data-edit>${t("common.edit")}</button>
            <button class="btn btn-sm btn-danger" data-del>${t("common.delete")}</button>
          </div>
        </div>
      `);
      card.querySelector("[data-edit]").addEventListener("click", () => openGatewayModal(gw));
      card.querySelector("[data-del]").addEventListener("click", async () => {
        if (!confirmDialog(t("devices.confirm_delete_gateway", { name: gw.name }))) return;
        await api.del(`/api/gateways/${gw.id}`);
        await refreshGateways();
        toast(t("devices.gateway_deleted"), "success");
      });
      listEl.appendChild(card);
    }
  }

  function renderTrackers() {
    const listEl = document.getElementById("tracker-list");
    if (!listEl) return;
    const trackers = ownedTrackers();
    if (!trackers.length) {
      listEl.innerHTML = `<div class="list-empty">${t("devices.no_pets")}</div>`;
      return;
    }
    listEl.innerHTML = "";
    for (const tr of trackers) {
      const ch = tr.channel_id ? channelById(tr.channel_id) : null;
      const card = el(`
        <div class="card">
          <div class="card-row">
            <div style="display:flex;align-items:center;gap:10px">
              <span class="tracker-dot" style="background:${tr.color}"></span>
              <div>
                <div class="card-title">${escapeHtml(tr.name)}</div>
                <div class="muted" style="font-size:13px">${tr.node_id ? escapeHtml(tr.node_id) : t("devices.no_node_assigned")} · ${t("devices.channel")}: ${ch ? escapeHtml(ch.name) : "–"}</div>
              </div>
            </div>
            <span class="badge ${tr.active ? "badge-ok" : "badge-mut"}">${tr.active ? t("devices.active") : t("devices.paused")}</span>
          </div>
          <div class="muted" style="font-size:13px;margin-top:6px">
            🔋 ${tr.last_battery != null ? tr.last_battery + "%" : "–"} · ${t("devices.last_fix")} ${timeAgo(tr.last_position_at)}
          </div>
          <div class="card-row" style="margin-top:10px">
            <button class="btn btn-sm" data-radio ${tr.node_id ? "" : "disabled"}>📡 ${t("devices.radio_settings")}</button>
            <button class="btn btn-sm" data-edit>${t("common.edit")}</button>
            <button class="btn btn-sm btn-danger" data-del>${t("common.delete")}</button>
          </div>
        </div>
      `);
      card.querySelector("[data-edit]").addEventListener("click", () => openTrackerModal(tr));
      card.querySelector("[data-radio]").addEventListener("click", () => openRadioConfigModal(tr));
      card.querySelector("[data-del]").addEventListener("click", async () => {
        if (!confirmDialog(t("devices.confirm_delete_pet", { name: tr.name }))) return;
        await api.del(`/api/trackers/${tr.id}`);
        await refreshTrackers();
        toast(t("devices.pet_deleted"), "success");
      });
      listEl.appendChild(card);
    }
  }

  function openRadioConfigModal(tr) {
    const { form } = openModal({
      title: t("devices.radio_settings_title", { name: tr.name }),
      submitLabel: t("common.close"),
      bodyHtml: `
        <p class="muted" style="font-size:13px;margin-top:-6px">${t("devices.radio_settings_hint")}</p>

        <div class="card" style="padding:12px;margin-bottom:10px">
          <h4 style="margin:0 0 8px">📍 ${t("devices.gps_interval")}</h4>
          <div class="grid-2">
            <label>${t("devices.gps_update")} (s) <input type="number" name="gps_update_interval" min="10" value="30"></label>
            <label>${t("devices.broadcast")} (s) <input type="number" name="broadcast_secs" min="30" value="900"></label>
            <label>${t("devices.smart_min_distance")} (m) <input type="number" name="smart_min_distance" min="0" value="30"></label>
            <label>${t("devices.smart_min_interval")} (s) <input type="number" name="smart_min_interval" min="0" value="30"></label>
          </div>
          <button type="button" class="btn btn-sm" data-push="gps" style="margin-top:8px">${t("devices.send_gps_settings")}</button>
        </div>

        <div class="card" style="padding:12px;margin-bottom:10px">
          <h4 style="margin:0 0 8px">🔋 ${t("devices.power_saving")}</h4>
          <div class="switch-row">
            <span>${t("devices.power_saving_mode")}</span>
            <label class="switch"><input type="checkbox" name="is_power_saving"><span class="slider"></span></label>
          </div>
          <label>${t("devices.light_sleep")} (s) <input type="number" name="ls_secs" min="10" value="300"></label>
          <button type="button" class="btn btn-sm" data-push="power" style="margin-top:8px">${t("devices.send_power_settings")}</button>
        </div>

        <div class="card" style="padding:12px">
          <h4 style="margin:0 0 8px">🔊 ${t("devices.buzzer")}</h4>
          <label>${t("devices.buzzer_mode")}
            <select name="buzzer_mode">
              <option value="0">${t("devices.buzzer_all")}</option>
              <option value="2">${t("devices.buzzer_notifications_only")}</option>
              <option value="3">${t("devices.buzzer_system_only")}</option>
              <option value="4">${t("devices.buzzer_dm_only")}</option>
              <option value="1">${t("devices.buzzer_off")}</option>
            </select>
          </label>
          <button type="button" class="btn btn-sm" data-push="buzzer" style="margin-top:8px">${t("devices.send_buzzer_settings")}</button>
        </div>
      `,
      onMount: (form) => {
        const push = async (btn, endpoint, payload) => {
          const label = btn.textContent;
          btn.disabled = true;
          btn.textContent = t("devices.sending");
          try {
            await api.post(`/api/trackers/${tr.id}/${endpoint}`, payload);
            toast(t("devices.settings_sent"), "success");
          } catch (err) {
            toast(err.message, "error");
          } finally {
            btn.disabled = false;
            btn.textContent = label;
          }
        };
        form.querySelector('[data-push="gps"]').addEventListener("click", (e) => push(e.target, "push-position-config", {
          gps_update_interval: Number(form.gps_update_interval.value),
          broadcast_secs: Number(form.broadcast_secs.value),
          smart_min_distance: Number(form.smart_min_distance.value),
          smart_min_interval: Number(form.smart_min_interval.value),
        }));
        form.querySelector('[data-push="power"]').addEventListener("click", (e) => push(e.target, "push-power-config", {
          is_power_saving: form.is_power_saving.checked,
          ls_secs: Number(form.ls_secs.value),
        }));
        form.querySelector('[data-push="buzzer"]').addEventListener("click", (e) => push(e.target, "push-buzzer-config", {
          buzzer_mode: Number(form.buzzer_mode.value),
        }));
      },
      onSubmit: async () => true,
    });
  }

  function openGatewayModal(gw) {
    openModal({
      title: gw ? t("devices.edit_gateway") : t("devices.add_gateway"),
      bodyHtml: `
        <label>${t("devices.name")} <input name="name" required value="${gw ? escapeHtml(gw.name) : ""}" placeholder="${t("devices.gateway_name_placeholder")}"></label>
        <label>${t("devices.ip_address")} <input name="ip_address" required value="${gw ? escapeHtml(gw.ip_address) : ""}" placeholder="192.168.1.50"></label>
        <div class="switch-row">
          <span>${t("devices.enabled")}</span>
          <label class="switch"><input type="checkbox" name="enabled" ${!gw || gw.enabled ? "checked" : ""}><span class="slider"></span></label>
        </div>
        <div class="switch-row">
          <span>${t("devices.admin_capable")}</span>
          <label class="switch"><input type="checkbox" name="is_admin_capable" ${!gw || gw.is_admin_capable ? "checked" : ""}><span class="slider"></span></label>
        </div>
      `,
      onSubmit: async (fd) => {
        const payload = {
          name: fd.get("name"),
          ip_address: fd.get("ip_address"),
          enabled: fd.get("enabled") === "on",
          is_admin_capable: fd.get("is_admin_capable") === "on",
        };
        if (gw) await api.put(`/api/gateways/${gw.id}`, payload);
        else await api.post("/api/gateways", payload);
        await refreshGateways();
        toast(t("devices.gateway_saved"), "success");
      },
    });
  }

  async function openTrackerModal(tr) {
    const gwOptions = state.gateways.map((g) => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join("");
    const chOptions = `<option value="">— ${t("devices.no_channel")} —</option>` + state.channels.map((c) =>
      `<option value="${c.id}" ${tr && tr.channel_id === c.id ? "selected" : ""}>${escapeHtml(c.name)}</option>`
    ).join("");
    const speciesOptions = ["dog", "cat", "other"].map((s) =>
      `<option value="${s}" ${tr && tr.species === s ? "selected" : ""}>${t(`devices.species_${s}`)}</option>`
    ).join("");

    const { form } = openModal({
      title: tr ? t("devices.edit_pet") : t("devices.add_pet"),
      bodyHtml: `
        ${!tr ? `
        <label>${t("devices.discover_via_gateway")}
          <select id="discover-gateway">${gwOptions}</select>
        </label>
        <label>${t("devices.known_nodes")}
          <select id="discover-node"><option value="">— ${t("devices.pick_or_enter_below")} —</option></select>
        </label>
        ` : ""}
        <label>${t("devices.pet_name")} <input name="name" required value="${tr ? escapeHtml(tr.name) : ""}" placeholder="${t("devices.pet_name_placeholder")}"></label>
        <label>${t("devices.species")} <select name="species">${speciesOptions}</select></label>
        <label>${t("devices.node_id")} <input name="node_id" value="${tr && tr.node_id ? escapeHtml(tr.node_id) : ""}" placeholder="!a1b2c3d4 (${t("devices.node_id_optional")})"></label>
        <label>${t("devices.map_color")} <input type="color" name="color" value="${tr ? tr.color : "#2f7d5f"}"></label>
        <label>${t("devices.channel")} <select name="channel_id">${chOptions}</select></label>
        <div class="grid-2">
          <label>${t("devices.battery_alert_threshold")} (%) <input type="number" name="battery_alert_threshold" min="0" max="100" value="${tr ? tr.battery_alert_threshold : 20}"></label>
          <label>${t("devices.offline_alert_minutes")} <input type="number" name="offline_alert_minutes" min="5" value="${tr ? tr.offline_alert_minutes : 60}"></label>
        </div>
        <div class="switch-row">
          <span>${t("devices.active")}</span>
          <label class="switch"><input type="checkbox" name="active" ${!tr || tr.active ? "checked" : ""}><span class="slider"></span></label>
        </div>
        ${tr ? `
        <label>${t("devices.photos")}</label>
        <div class="photo-grid" id="pet-photo-grid"></div>
        <label class="btn btn-sm" style="margin:0 0 8px">${t("devices.add_photo")}
          <input type="file" id="pet-photo-input" accept="image/*" hidden>
        </label>
        ` : `<p class="muted" style="font-size:12px">${t("devices.photos_after_save")}</p>`}
      `,
      onSubmit: async (fd) => {
        const payload = {
          node_id: fd.get("node_id") || null,
          name: fd.get("name"),
          species: fd.get("species"),
          color: fd.get("color"),
          channel_id: fd.get("channel_id") ? Number(fd.get("channel_id")) : null,
          battery_alert_threshold: Number(fd.get("battery_alert_threshold")),
          offline_alert_minutes: Number(fd.get("offline_alert_minutes")),
          active: fd.get("active") === "on",
        };
        if (tr) await api.put(`/api/trackers/${tr.id}`, payload);
        else await api.post("/api/trackers", payload);
        await refreshTrackers();
        toast(t("devices.pet_saved"), "success");
      },
    });

    if (!tr) {
      const gwSelect = form.querySelector("#discover-gateway");
      const nodeSelect = form.querySelector("#discover-node");
      const nodeIdInput = form.querySelector('[name="node_id"]');
      const nameInput = form.querySelector('[name="name"]');

      async function loadNodes() {
        nodeSelect.innerHTML = `<option value="">${t("common.loading")}</option>`;
        try {
          const nodes = await api.get(`/api/gateways/${gwSelect.value}/nodes`);
          nodeSelect.innerHTML = `<option value="">— ${t("devices.pick_or_enter_below")} —</option>` +
            nodes.filter((n) => n.node_id).map((n) =>
              `<option value="${n.node_id}" data-name="${escapeHtml(n.long_name || n.short_name || "")}">${escapeHtml(n.long_name || n.short_name || n.node_id)} (${n.node_id})</option>`
            ).join("");
        } catch {
          nodeSelect.innerHTML = `<option value="">${t("devices.discover_failed")}</option>`;
        }
      }
      if (gwSelect.options.length) loadNodes();
      gwSelect.addEventListener("change", loadNodes);
      nodeSelect.addEventListener("change", () => {
        if (!nodeSelect.value) return;
        nodeIdInput.value = nodeSelect.value;
        const opt = nodeSelect.selectedOptions[0];
        if (opt && opt.dataset.name && !nameInput.value) nameInput.value = opt.dataset.name;
      });
    } else {
      wirePetPhotos(tr, form);
    }
  }

  async function wirePetPhotos(tr, form) {
    const grid = form.querySelector("#pet-photo-grid");
    const input = form.querySelector("#pet-photo-input");

    async function renderPhotos() {
      let photos = [];
      try {
        photos = await api.get(`/api/trackers/${tr.id}/photos`);
      } catch { /* ignore */ }
      grid.innerHTML = photos.map((p) => `
        <div class="photo-thumb" data-photo="${p.id}">
          <img src="/api/trackers/${tr.id}/photos/${p.id}/file" alt="">
          <button type="button" class="photo-del" data-del-photo="${p.id}">✕</button>
        </div>
      `).join("") || `<div class="muted" style="font-size:12px">${t("devices.no_photos")}</div>`;
      grid.querySelectorAll("[data-del-photo]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await api.del(`/api/trackers/${tr.id}/photos/${btn.dataset.delPhoto}`);
            await renderPhotos();
          } catch (err) {
            toast(err.message, "error");
          }
        });
      });
    }

    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        await api.postFile(`/api/trackers/${tr.id}/photos`, fd);
        await renderPhotos();
      } catch (err) {
        toast(err.message, "error");
      } finally {
        input.value = "";
      }
    });

    await renderPhotos();
  }

  const unsub = subscribe(() => { renderGateways(); renderTrackers(); });
  const unsubLocale = onLocaleChange(() => { renderGateways(); renderTrackers(); });
  renderGateways();
  renderTrackers();
  return () => { unsub(); unsubLocale(); };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
