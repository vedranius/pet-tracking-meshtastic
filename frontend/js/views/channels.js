import { api } from "../api.js";
import { state, subscribe, refreshChannels, ownedTrackers } from "../state.js";
import { openModal, confirmDialog, el } from "../util.js";
import { toast } from "../toast.js";
import { t, onLocaleChange } from "../i18n.js";

export async function mountChannels(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header">
        <h2>🔑 ${t("nav.channels")}</h2>
        <button class="btn btn-primary btn-sm" id="add-channel">+ ${t("channels.new")}</button>
      </div>
      <p class="muted" style="margin-top:-8px">${t("channels.hint")}</p>
      <div id="channel-list"></div>
    </div>
  `;

  container.querySelector("#add-channel").addEventListener("click", () => openChannelModal());

  function render() {
    const listEl = document.getElementById("channel-list");
    if (!listEl) return;
    if (!state.channels.length) {
      listEl.innerHTML = `<div class="list-empty">${t("channels.none")}</div>`;
      return;
    }
    listEl.innerHTML = "";
    for (const ch of state.channels) {
      const card = el(`
        <div class="card">
          <div class="card-row">
            <div>
              <div class="card-title">${escapeHtml(ch.name)} ${ch.is_primary ? `<span class="badge badge-mut">${t("channels.primary")}</span>` : ""}</div>
              <div class="muted" style="font-size:13px">${t("channels.slot")} ${ch.device_index} · precision ${ch.position_precision}${ch.position_precision === 0 ? ` (${t("channels.no_public_location")})` : ""}</div>
            </div>
          </div>
          ${ch.psk_base64 ? `
          <div class="psk-field" style="margin-top:8px">
            <code data-psk-hidden>••••••••••••••••••••••••</code>
            <button class="btn btn-sm" data-reveal>👁</button>
            <button class="btn btn-sm" data-copy>${t("common.copy")}</button>
          </div>` : ""}
          <div class="card-row" style="margin-top:10px">
            <button class="btn btn-sm" data-edit>${t("common.edit")}</button>
            <button class="btn btn-sm" data-push>📡 ${t("channels.push")}</button>
            <button class="btn btn-sm btn-danger" data-del>${t("common.delete")}</button>
          </div>
        </div>
      `);
      const pskCode = card.querySelector("[data-psk-hidden]");
      card.querySelector("[data-reveal]")?.addEventListener("click", () => {
        pskCode.textContent = pskCode.textContent.startsWith("•") ? ch.psk_base64 : "••••••••••••••••••••••••";
      });
      card.querySelector("[data-copy]")?.addEventListener("click", async () => {
        await navigator.clipboard.writeText(ch.psk_base64);
        toast(t("channels.psk_copied"), "success");
      });
      card.querySelector("[data-edit]").addEventListener("click", () => openChannelModal(ch));
      card.querySelector("[data-push]").addEventListener("click", () => openPushModal(ch));
      card.querySelector("[data-del]").addEventListener("click", async () => {
        if (!confirmDialog(t("channels.confirm_delete", { name: ch.name }))) return;
        await api.del(`/api/channels/${ch.id}`);
        await refreshChannels();
        toast(t("channels.deleted"), "success");
      });
      listEl.appendChild(card);
    }
  }

  function openChannelModal(ch) {
    openModal({
      title: ch ? t("channels.edit") : t("channels.new"),
      bodyHtml: `
        <label>${t("channels.name")} <input name="name" required value="${ch ? escapeHtml(ch.name) : ""}" placeholder="${t("channels.name_placeholder")}"></label>
        <div class="grid-2">
          <label>${t("channels.device_slot")} <input type="number" name="device_index" min="0" max="7" value="${ch ? ch.device_index : 1}"></label>
          <label>Position precision <input type="number" name="position_precision" min="0" max="32" value="${ch ? ch.position_precision : 32}"></label>
        </div>
        <label>${t("channels.psk")} <input name="psk_base64" value="${ch && ch.psk_base64 ? escapeHtml(ch.psk_base64) : ""}" placeholder="${t("channels.psk_placeholder")}"></label>
        <div class="switch-row">
          <span>${t("channels.is_primary")}</span>
          <label class="switch"><input type="checkbox" name="is_primary" ${ch && ch.is_primary ? "checked" : ""}><span class="slider"></span></label>
        </div>
        <label>${t("channels.notes")} <input name="notes" value="${ch && ch.notes ? escapeHtml(ch.notes) : ""}"></label>
      `,
      onSubmit: async (fd) => {
        const payload = {
          name: fd.get("name"),
          device_index: Number(fd.get("device_index")),
          position_precision: Number(fd.get("position_precision")),
          psk_base64: fd.get("psk_base64") || null,
          is_primary: fd.get("is_primary") === "on",
          notes: fd.get("notes") || null,
        };
        if (ch) await api.put(`/api/channels/${ch.id}`, payload);
        else await api.post("/api/channels", payload);
        await refreshChannels();
        toast(t("channels.saved"), "success");
      },
    });
  }

  function openPushModal(ch) {
    const gwItems = state.gateways.map((g) =>
      `<label><input type="checkbox" name="target" value="gateway:${g.id}"> 📡 ${escapeHtml(g.name)} (${t("channels.gateway")})</label>`
    ).join("");
    const trItems = ownedTrackers().filter((tr) => tr.node_id).map((tr) =>
      `<label><input type="checkbox" name="target" value="${escapeHtml(tr.node_id)}"> 🐾 ${escapeHtml(tr.name)}</label>`
    ).join("");

    openModal({
      title: t("channels.push_title", { name: ch.name }),
      submitLabel: t("channels.send"),
      bodyHtml: `
        <p class="muted" style="margin-top:0">${t("channels.push_hint")}</p>
        <div class="checklist">${gwItems}${trItems || ""}</div>
      `,
      onSubmit: async (fd) => {
        const targets = fd.getAll("target");
        if (!targets.length) { toast(t("channels.pick_one_device"), "error"); return false; }
        try {
          const res = await api.post(`/api/channels/${ch.id}/push`, { targets, primary: ch.is_primary });
          const failed = Object.entries(res.results).filter(([, v]) => v !== "ok");
          if (failed.length) toast(t("channels.push_partial", { targets: failed.map(([k]) => k).join(", ") }), "error");
          else toast(t("channels.push_success"), "success");
        } catch (e) {
          toast(e.message, "error");
          return false;
        }
      },
    });
  }

  const unsub = subscribe(render);
  const unsubLocale = onLocaleChange(render);
  render();
  return () => { unsub(); unsubLocale(); };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
