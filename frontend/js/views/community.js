import { api } from "../api.js";
import { t } from "../i18n.js";

const VIEW_KEY = "pawtrack_community_view";

export async function mountCommunity(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header"><h2>🐾 ${t("nav.community")}</h2></div>
      <p class="muted" style="font-size:13px;margin-top:-8px">${t("community.hint")}</p>
      <div class="view-toggle" id="community-view-toggle">
        <button type="button" data-view="pet">🐾 ${t("community.view_by_pet")}</button>
        <button type="button" data-view="user">🧑 ${t("community.view_by_user")}</button>
      </div>
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
  const toggleEl = container.querySelector("#community-view-toggle");
  let view = localStorage.getItem(VIEW_KEY) === "user" ? "user" : "pet";

  function setView(v) {
    view = v;
    localStorage.setItem(VIEW_KEY, v);
    toggleEl.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    render();
  }

  toggleEl.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));

  function render() {
    if (!pets.length) {
      gridEl.innerHTML = `<div class="list-empty">${t("community.none")}</div>`;
      return;
    }
    gridEl.className = "community-grid";
    gridEl.innerHTML = view === "user" ? renderByUser(pets) : renderByPet(pets);
    wireLightbox();
  }

  function wireLightbox() {
    gridEl.querySelectorAll("img[data-lightbox]").forEach((img) => {
      img.addEventListener("click", () => openLightbox(img.dataset.tracker, img.dataset.lightbox));
    });
  }

  function openLightbox(trackerId, photoId) {
    const box = document.createElement("div");
    box.className = "photo-lightbox";
    box.innerHTML = `<img src="/api/trackers/${trackerId}/photos/${photoId}/file" alt="">`;
    box.addEventListener("click", () => box.remove());
    document.body.appendChild(box);
  }

  setView(view);

  return () => {};
}

function petPhotoHtml(p) {
  const firstPhoto = p.photos[0];
  return firstPhoto
    ? `<img src="/api/trackers/${p.id}/photos/${firstPhoto.id}/file" alt="${escapeHtml(p.name)}" data-lightbox="${firstPhoto.id}" data-tracker="${p.id}">`
    : `<span style="color:${p.color}">🐾</span>`;
}

function personChip(person) {
  const cls = person.role === "owner" ? "chip chip-owner" : "chip";
  const icon = person.role === "owner" ? "👑" : "🤝";
  return `<span class="${cls}">${icon} ${escapeHtml(person.username)}</span>`;
}

// One card per pet — the pet is the primary unit, its owner and any
// caretakers (family members sharing the same account setup) are listed
// underneath, collapsed by default so the grid stays compact.
function renderByPet(pets) {
  return pets.map((p) => `
    <div class="community-card">
      <div class="community-card-photo">${petPhotoHtml(p)}</div>
      <div class="community-card-body">
        <div class="community-card-name">${escapeHtml(p.name)}${p.species ? ` · ${t(`devices.species_${p.species}`)}` : ""}</div>
        ${p.photos.length > 1 ? `<div class="muted" style="font-size:11px;margin-top:2px">📷 ${p.photos.length}</div>` : ""}
        <details class="disclosure community-card-people">
          <summary>${t("community.people_count", { count: p.people.length })}</summary>
          <div class="community-people-list">${p.people.map(personChip).join("")}</div>
        </details>
      </div>
    </div>
  `).join("");
}

// One card per person (owner or caretaker on at least one pet) — the pets
// they're linked to are listed underneath, same collapsed-by-default style.
function renderByUser(pets) {
  const byUser = new Map(); // user_id -> { username, pets: [{pet, role}] }
  for (const p of pets) {
    for (const person of p.people) {
      if (!byUser.has(person.user_id)) byUser.set(person.user_id, { username: person.username, pets: [] });
      byUser.get(person.user_id).pets.push({ pet: p, role: person.role });
    }
  }
  const users = [...byUser.values()].sort((a, b) => a.username.localeCompare(b.username));

  return users.map((u) => `
    <div class="community-card">
      <div class="community-card-photo"><span>🧑</span></div>
      <div class="community-card-body">
        <div class="community-card-name">${escapeHtml(u.username)}</div>
        <details class="disclosure community-card-people" open>
          <summary>${t("community.pets_count", { count: u.pets.length })}</summary>
          <div class="community-people-list">
            ${u.pets.map(({ pet, role }) => `
              <div style="display:flex;align-items:center;gap:6px">
                <span style="color:${pet.color}">🐾</span>
                <span>${escapeHtml(pet.name)}</span>
                ${role === "owner" ? `<span class="chip chip-owner" style="padding:1px 7px">👑</span>` : `<span class="chip" style="padding:1px 7px">🤝</span>`}
              </div>
            `).join("")}
          </div>
        </details>
      </div>
    </div>
  `).join("");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
