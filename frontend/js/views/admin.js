import { api } from "../api.js";
import { onWSMessage } from "../ws.js";
import { timeAgo, confirmDialog, openModal } from "../util.js";
import { toast } from "../toast.js";
import { t, onLocaleChange } from "../i18n.js";

const DEFAULT_CENTER = [45.1, 15.2];

function fmtDistance(m) {
  if (m == null) return "–";
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

export async function mountAdmin(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header">
        <h2>🛡️ ${t("admin.title")}</h2>
        <button class="btn btn-primary btn-sm" id="add-user">+ ${t("admin.add_user")}</button>
      </div>
      <p class="muted" style="font-size:13px;margin-top:-8px">${t("admin.hint")}</p>
      <div id="admin-map" style="height:340px;border-radius:14px;overflow:hidden;border:1px solid var(--border);margin-bottom:14px"></div>
      <div id="admin-users"></div>
    </div>
  `;

  container.querySelector("#add-user").addEventListener("click", () => openAddUserModal());

  const map = L.map("admin-map").setView(DEFAULT_CENTER, 7);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);
  const layer = L.layerGroup().addTo(map);

  let overview = null;

  function petIcon(color) {
    return L.divIcon({
      className: "", html: `<div class="marker-label" style="border-color:${color}">🐾</div>`,
      iconSize: [30, 30], iconAnchor: [15, 15],
    });
  }
  function personIcon() {
    return L.divIcon({
      className: "", html: `<div class="marker-label" style="border-color:#3363c9">🧑</div>`,
      iconSize: [30, 30], iconAnchor: [15, 15],
    });
  }

  function renderMap() {
    layer.clearLayers();
    const pts = [];
    if (overview.admin_location) {
      const { lat, lon } = overview.admin_location;
      L.marker([lat, lon], { icon: personIcon() }).bindTooltip(t("admin.you")).addTo(layer);
      pts.push([lat, lon]);
    }
    for (const row of overview.users) {
      if (row.device_location) {
        const { lat, lon } = row.device_location;
        L.marker([lat, lon], { icon: personIcon() }).bindTooltip(row.user.username).addTo(layer);
        pts.push([lat, lon]);
      }
      for (const tr of row.trackers) {
        if (tr.last_lat == null) continue;
        L.marker([tr.last_lat, tr.last_lon], { icon: petIcon(tr.color) })
          .bindTooltip(`${tr.name} (${row.user.username})`)
          .addTo(layer);
        pts.push([tr.last_lat, tr.last_lon]);
      }
    }
    if (pts.length) map.fitBounds(pts, { maxZoom: 15, padding: [40, 40] });
  }

  function avatarHtml(user) {
    return user.has_avatar
      ? `<img src="/api/users/${user.id}/avatar" alt="" style="width:40px;height:40px;border-radius:50%;object-fit:cover">`
      : `<div style="width:40px;height:40px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:18px">🧑</div>`;
  }

  function renderUsers() {
    const el = document.getElementById("admin-users");
    if (!overview.users.length) {
      el.innerHTML = `<div class="list-empty">${t("admin.no_users")}</div>`;
      return;
    }
    el.innerHTML = overview.users.map((row) => `
      <div class="card">
        <div class="card-row">
          <div style="display:flex;gap:10px;align-items:center">
            ${avatarHtml(row.user)}
            <div>
              <div class="card-title">${escapeHtml(row.user.username)} ${row.user.role === "admin" ? `<span class="badge badge-mut">${t("admin.admin_badge")}</span>` : ""}</div>
              <div class="muted" style="font-size:13px">
                ${row.device_location
                  ? `📍 ${t("admin.phone_last_seen")} ${timeAgo(row.device_location.ts)} · ${t("admin.distance_from_you")}: ${fmtDistance(row.distance_from_admin_m)}`
                  : t("admin.no_phone_location")}
              </div>
              ${row.user.bio ? `<div class="muted" style="font-size:12px;margin-top:2px">${escapeHtml(row.user.bio)}</div>` : ""}
            </div>
          </div>
        </div>
        ${row.trackers.length ? `
          <div class="admin-pet-list">
            ${row.trackers.map((tr) => `
              <div class="admin-pet-row">
                <span class="tracker-dot" style="background:${tr.color}"></span>
                <span>${escapeHtml(tr.name)}</span>
                <span class="muted" style="font-size:12px">
                  ${tr.last_position_at ? timeAgo(tr.last_position_at) : t("admin.no_position_yet")}
                  ${tr.distance_from_owner_m != null ? ` · ${fmtDistance(tr.distance_from_owner_m)} ${t("admin.from_owner")}` : ""}
                  ${tr.photo_count ? ` · 📷 ${tr.photo_count}` : ""}
                </span>
              </div>
            `).join("")}
          </div>
        ` : `<div class="muted" style="font-size:13px;margin-top:6px">${t("admin.no_pets")}</div>`}
        <div class="card-row" style="margin-top:10px">
          <button class="btn btn-sm" data-role="${row.user.id}" data-current-role="${row.user.role}">
            ${row.user.role === "admin" ? t("admin.demote") : t("admin.promote")}
          </button>
          <button class="btn btn-sm" data-reset-pw="${row.user.id}">${t("admin.reset_password")}</button>
          ${row.user.role !== "admin" ? `<button class="btn btn-sm btn-danger" data-del-user="${row.user.id}">${t("admin.delete_user")}</button>` : ""}
        </div>
      </div>
    `).join("");

    el.querySelectorAll("[data-del-user]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirmDialog(t("admin.confirm_delete_user"))) return;
        try {
          await api.del(`/api/admin/users/${btn.dataset.delUser}`);
          toast(t("admin.user_deleted"), "success");
          await load();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });

    el.querySelectorAll("[data-role]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const newRole = btn.dataset.currentRole === "admin" ? "user" : "admin";
        try {
          await api.put(`/api/admin/users/${btn.dataset.role}/role`, { role: newRole });
          toast(t("admin.role_changed"), "success");
          await load();
        } catch (err) {
          toast(err.message, "error");
        }
      });
    });

    el.querySelectorAll("[data-reset-pw]").forEach((btn) => {
      btn.addEventListener("click", () => openResetPasswordModal(btn.dataset.resetPw));
    });
  }

  function openAddUserModal() {
    openModal({
      title: t("admin.add_user"),
      bodyHtml: `
        <label>${t("login.username")} <input name="username" required minlength="3"></label>
        <label>${t("login.password")} <input type="password" name="password" required minlength="6"></label>
        <div class="switch-row">
          <span>${t("admin.admin_badge")}</span>
          <label class="switch"><input type="checkbox" name="is_admin"><span class="slider"></span></label>
        </div>
      `,
      onSubmit: async (fd) => {
        const created = await api.post("/api/admin/users", {
          username: fd.get("username"), password: fd.get("password"),
        });
        if (fd.get("is_admin") === "on" && created.role !== "admin") {
          await api.put(`/api/admin/users/${created.id}/role`, { role: "admin" });
        }
        toast(t("admin.user_created"), "success");
        await load();
      },
    });
  }

  function openResetPasswordModal(userId) {
    openModal({
      title: t("admin.reset_password"),
      bodyHtml: `<label>${t("settings.new_password")} <input type="password" name="password" required minlength="6"></label>`,
      onSubmit: async (fd) => {
        await api.put(`/api/admin/users/${userId}/password`, { password: fd.get("password") });
        toast(t("admin.password_reset_done"), "success");
      },
    });
  }

  async function load() {
    overview = await api.get("/api/admin/overview");
    renderMap();
    renderUsers();
  }

  const unsubWs = onWSMessage((msg) => {
    if (msg.type === "device_location" || msg.type === "position") load();
  });
  const unsubLocale = onLocaleChange(() => { renderMap(); renderUsers(); });

  await load();
  setTimeout(() => map.invalidateSize(), 50);

  return () => { unsubWs(); unsubLocale(); map.remove(); };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
