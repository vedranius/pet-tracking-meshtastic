import { t } from "./i18n.js";

// The backend stores UTC timestamps but SQLite round-trips them as naive
// (no offset), so the JSON we get back looks like "2026-09-04T08:28:00" with
// no "Z". `new Date(...)` on a string like that is parsed as *local* time by
// spec, not UTC — silently shifting every timestamp by the local UTC offset.
// Always route API timestamps through this before turning them into a Date.
export function parseApiDate(iso) {
  if (!iso) return null;
  const hasOffset = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasOffset ? iso : iso + "Z");
}

export function timeAgo(iso) {
  const d = parseApiDate(iso);
  if (!d) return t("time.never");
  const diffMs = Date.now() - d.getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 10) return t("time.just_now");
  if (s < 60) return t("time.seconds_ago", { n: s });
  const m = Math.floor(s / 60);
  if (m < 60) return t("time.minutes_ago", { n: m });
  const h = Math.floor(m / 60);
  if (h < 24) return t("time.hours_ago", { n: h });
  const d2 = Math.floor(h / 24);
  return t("time.days_ago", { n: d2 });
}

// No fixed IANA zone here on purpose — this is a generic, self-hosted,
// multi-region app now, so timestamps render in whatever timezone the
// viewer's own browser/OS is set to, rather than one hardcoded region.
export function fmtDateTime(iso) {
  const d = parseApiDate(iso);
  if (!d) return "–";
  return d.toLocaleString();
}

export function el(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

let modalStack = 0;

export function openModal({ title, bodyHtml, onMount, onSubmit, submitLabel }) {
  const backdrop = el(`<div class="modal-backdrop"></div>`);
  const modal = el(`
    <div class="modal">
      <div class="modal-header"><h3>${title}</h3><button type="button" class="btn btn-ghost btn-sm" data-close>✕</button></div>
      <form data-form>${bodyHtml}
        <div class="modal-actions">
          <button type="button" class="btn" data-close>${t("common.cancel")}</button>
          <button type="submit" class="btn btn-primary">${submitLabel || t("common.save")}</button>
        </div>
      </form>
    </div>
  `);
  backdrop.appendChild(modal);
  document.body.appendChild(backdrop);
  modalStack++;

  const close = () => {
    backdrop.remove();
    modalStack--;
  };
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  modal.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));

  const form = modal.querySelector("[data-form]");
  if (onMount) onMount(form);
  if (onSubmit) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      try {
        const ok = await onSubmit(new FormData(form), form);
        if (ok !== false) close();
      } finally {
        submitBtn.disabled = false;
      }
    });
  }
  return { close, modal, form };
}

export function confirmDialog(message) {
  return window.confirm(message);
}
