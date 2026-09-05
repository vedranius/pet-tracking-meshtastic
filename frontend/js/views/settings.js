import { api } from "../api.js";
import { toast } from "../toast.js";
import { t } from "../i18n.js";
import { currentUser, setCurrentUser } from "../state.js";

export async function mountSettings(container) {
  const settings = await api.get("/api/settings").catch(() => ({}));
  const me = currentUser();

  container.innerHTML = `
    <div class="page">
      <div class="page-header"><h2>⚙️ ${t("nav.settings")}</h2></div>

      <div class="card">
        <h3>${t("settings.profile")}</h3>
        <div class="avatar-row">
          <div class="avatar-preview" id="avatar-preview">${me?.has_avatar ? `<img src="/api/users/${me.id}/avatar?v=${Date.now()}" alt="">` : "🧑"}</div>
          <div>
            <div style="font-weight:700">${escapeHtml(me?.username || "")}</div>
            <div class="card-row" style="margin-top:6px">
              <label class="btn btn-sm" style="margin:0">
                ${t("settings.change_photo")}
                <input type="file" id="avatar-input" accept="image/*" hidden>
              </label>
              ${me?.has_avatar ? `<button type="button" class="btn btn-sm btn-danger" id="avatar-remove">${t("common.remove")}</button>` : ""}
            </div>
          </div>
        </div>
        <form id="bio-form">
          <label>${t("settings.bio")} <textarea name="bio" maxlength="1000" rows="3" placeholder="${t("settings.bio_placeholder")}">${escapeHtml(me?.bio || "")}</textarea></label>
          <button type="submit" class="btn btn-primary btn-sm">${t("common.save")}</button>
        </form>
      </div>

      <div class="card">
        <h3>${t("settings.telegram")}</h3>
        <p class="muted" style="font-size:13px;margin-top:-6px">${t("settings.telegram_hint")}</p>
        <form id="telegram-form">
          <label>${t("settings.bot_token")} <input name="telegram_bot_token" value="${escapeHtml(settings.telegram_bot_token || "")}" placeholder="123456:ABC..."></label>
          <label>${t("settings.chat_id")} <input name="telegram_chat_id" value="${escapeHtml(settings.telegram_chat_id || "")}" placeholder="123456789"></label>
          <div class="card-row">
            <button type="submit" class="btn btn-primary btn-sm">${t("common.save")}</button>
            <button type="button" id="telegram-test" class="btn btn-sm">${t("settings.send_test")}</button>
          </div>
        </form>
      </div>

      <div class="card">
        <h3>${t("settings.password")}</h3>
        <form id="password-form">
          <label>${t("settings.new_password")} <input type="password" name="password" minlength="6" required></label>
          <button type="submit" class="btn btn-primary btn-sm">${t("settings.change_password")}</button>
        </form>
      </div>

      <div class="card">
        <h3>${t("settings.about")}</h3>
        <p class="muted" style="font-size:13px">${t("settings.about_text")}</p>
      </div>
    </div>
  `;

  container.querySelector("#avatar-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.postFile("/api/me/avatar", fd);
      setCurrentUser({ ...currentUser(), has_avatar: true });
      container.querySelector("#avatar-preview").innerHTML = `<img src="/api/users/${me.id}/avatar?v=${Date.now()}" alt="">`;
      toast(t("settings.photo_saved"), "success");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  container.querySelector("#avatar-remove")?.addEventListener("click", async () => {
    try {
      await api.del("/api/me/avatar");
      setCurrentUser({ ...currentUser(), has_avatar: false });
      toast(t("settings.photo_removed"), "success");
      mountSettings(container);
    } catch (err) {
      toast(err.message, "error");
    }
  });

  container.querySelector("#bio-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api.put("/api/me", { bio: fd.get("bio") });
      setCurrentUser({ ...currentUser(), bio: fd.get("bio") });
      toast(t("settings.saved"), "success");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  container.querySelector("#telegram-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api.put("/api/settings", {
        telegram_bot_token: fd.get("telegram_bot_token"),
        telegram_chat_id: fd.get("telegram_chat_id"),
      });
      toast(t("settings.saved"), "success");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  container.querySelector("#telegram-test").addEventListener("click", async () => {
    try {
      const res = await api.post("/api/settings/telegram/test", {});
      toast(res.ok ? t("settings.test_sent") : t("settings.test_failed"), res.ok ? "success" : "error");
    } catch (err) {
      toast(err.message, "error");
    }
  });

  container.querySelector("#password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api.put("/api/settings/password", { password: fd.get("password") });
      toast(t("settings.password_changed"), "success");
      e.target.reset();
    } catch (err) {
      toast(err.message, "error");
    }
  });

  return () => {};
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
