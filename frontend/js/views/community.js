import { api } from "../api.js";
import { t } from "../i18n.js";

export async function mountCommunity(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header"><h2>🐾 ${t("nav.community")}</h2></div>
      <p class="muted" style="font-size:13px;margin-top:-8px">${t("community.hint")}</p>
      <div id="community-grid"></div>
    </div>
  `;

  let pets = [];
  try {
    pets = await api.get("/api/community/pets");
  } catch (err) {
    container.querySelector("#community-grid").innerHTML = `<div class="list-empty">${err.message}</div>`;
    return () => {};
  }

  const gridEl = container.querySelector("#community-grid");
  if (!pets.length) {
    gridEl.innerHTML = `<div class="list-empty">${t("community.none")}</div>`;
    return () => {};
  }

  gridEl.className = "community-grid";
  gridEl.innerHTML = pets.map((p) => {
    const firstPhoto = p.photos[0];
    const photoHtml = firstPhoto
      ? `<img src="/api/trackers/${p.id}/photos/${firstPhoto.id}/file" alt="${escapeHtml(p.name)}" data-lightbox="${firstPhoto.id}" data-tracker="${p.id}">`
      : `<span style="color:${p.color}">🐾</span>`;
    return `
      <div class="community-card">
        <div class="community-card-photo">${photoHtml}</div>
        <div class="community-card-body">
          <div class="community-card-name">${escapeHtml(p.name)}${p.species ? ` · ${t(`devices.species_${p.species}`)}` : ""}</div>
          <div class="community-card-owner">${t("community.owner")}: ${escapeHtml(p.owner_username)}</div>
          ${p.photos.length > 1 ? `<div class="muted" style="font-size:11px;margin-top:2px">📷 ${p.photos.length}</div>` : ""}
        </div>
      </div>
    `;
  }).join("");

  gridEl.querySelectorAll("img[data-lightbox]").forEach((img) => {
    img.addEventListener("click", () => openLightbox(img.dataset.tracker, img.dataset.lightbox));
  });

  function openLightbox(trackerId, photoId) {
    const box = document.createElement("div");
    box.className = "photo-lightbox";
    box.innerHTML = `<img src="/api/trackers/${trackerId}/photos/${photoId}/file" alt="">`;
    box.addEventListener("click", () => box.remove());
    document.body.appendChild(box);
  }

  return () => {};
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
