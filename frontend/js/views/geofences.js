import { api } from "../api.js";
import { state, subscribe, trackerById, ownedTrackers } from "../state.js";
import { openModal, confirmDialog, el } from "../util.js";
import { toast } from "../toast.js";
import { t, onLocaleChange } from "../i18n.js";

const DEFAULT_CENTER = [45.1, 15.2];

export async function mountGeofences(container) {
  container.innerHTML = `
    <div class="page" style="padding-bottom:20px">
      <div class="page-header">
        <h2>📐 ${t("nav.geofences")}</h2>
        <select id="tracker-select" style="max-width:220px"></select>
      </div>
      <div id="geo-map" style="height:360px;border-radius:14px;overflow:hidden;border:1px solid var(--border)"></div>
      <p class="muted" style="font-size:13px">${t("geofences.hint")}</p>
      <div id="fence-list" style="margin-top:10px"></div>
    </div>
  `;

  const trackerSelect = document.getElementById("tracker-select");
  const myTrackers = ownedTrackers();
  trackerSelect.innerHTML = myTrackers.map((tr) => `<option value="${tr.id}">${escapeHtml(tr.name)}</option>`).join("")
    || `<option value="">${t("geofences.no_pets")}</option>`;

  const map = L.map("geo-map").setView(DEFAULT_CENTER, 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);

  const drawnLayer = new L.FeatureGroup().addTo(map);
  const drawControl = new L.Control.Draw({
    draw: {
      circle: { shapeOptions: { color: "#1f6b4d" } },
      polygon: { shapeOptions: { color: "#1f6b4d" } },
      marker: false, circlemarker: false, polyline: false, rectangle: false,
    },
    edit: { featureGroup: drawnLayer, remove: false },
  });
  map.addControl(drawControl);

  let currentTrackerId = myTrackers[0]?.id ?? null;

  function centerOnTracker() {
    const tr = trackerById(currentTrackerId);
    if (tr && tr.last_lat != null) map.setView([tr.last_lat, tr.last_lon], 16);
  }

  async function loadFences() {
    drawnLayer.clearLayers();
    const listEl = document.getElementById("fence-list");
    if (!currentTrackerId) {
      listEl.innerHTML = `<div class="list-empty">${t("geofences.add_pet_first")}</div>`;
      return;
    }
    const fences = await api.get(`/api/geofences?tracker_id=${currentTrackerId}`);
    if (!fences.length) {
      listEl.innerHTML = `<div class="list-empty">${t("geofences.none")}</div>`;
    } else {
      listEl.innerHTML = "";
      for (const f of fences) {
        const card = el(`
          <div class="card">
            <div class="card-row">
              <div class="card-title">${escapeHtml(f.name)}</div>
              <label class="switch"><input type="checkbox" ${f.enabled ? "checked" : ""} data-toggle="${f.id}"><span class="slider"></span></label>
            </div>
            <div class="muted" style="font-size:13px">${f.shape === "circle" ? t("geofences.circle") : t("geofences.polygon")}</div>
            <div class="card-row" style="margin-top:8px">
              <button class="btn btn-sm btn-danger" data-del="${f.id}">${t("common.delete")}</button>
            </div>
          </div>
        `);
        card.querySelector("[data-toggle]").addEventListener("change", async (e) => {
          await api.put(`/api/geofences/${f.id}`, {
            tracker_id: f.tracker_id, name: f.name, shape: f.shape,
            geometry: JSON.parse(f.geometry_json), enabled: e.target.checked,
          });
          toast(t("common.updated"), "success");
        });
        card.querySelector("[data-del]").addEventListener("click", async () => {
          if (!confirmDialog(t("geofences.confirm_delete", { name: f.name }))) return;
          await api.del(`/api/geofences/${f.id}`);
          await loadFences();
          toast(t("geofences.deleted"), "success");
        });
        listEl.appendChild(card);
      }
    }
    for (const f of fences) {
      let geom;
      try { geom = JSON.parse(f.geometry_json); } catch { continue; }
      if (f.shape === "circle") {
        L.circle([geom.lat, geom.lon], { radius: geom.radius_m, color: "#1f6b4d", fillOpacity: 0.08 }).addTo(drawnLayer);
      } else if (f.shape === "polygon") {
        L.polygon(geom.points, { color: "#1f6b4d", fillOpacity: 0.08 }).addTo(drawnLayer);
      }
    }
  }

  map.on(L.Draw.Event.CREATED, (e) => {
    const layer = e.layer;
    let shape, geometry;
    if (e.layerType === "circle") {
      shape = "circle";
      geometry = { lat: layer.getLatLng().lat, lon: layer.getLatLng().lng, radius_m: Math.round(layer.getRadius()) };
    } else if (e.layerType === "polygon") {
      shape = "polygon";
      geometry = { points: layer.getLatLngs()[0].map((ll) => [ll.lat, ll.lng]) };
    } else {
      return;
    }
    openModal({
      title: t("geofences.name_prompt"),
      bodyHtml: `<label>${t("geofences.name")} <input name="name" required placeholder="${t("geofences.name_placeholder")}"></label>`,
      onSubmit: async (fd) => {
        if (!currentTrackerId) { toast(t("geofences.pick_pet"), "error"); return false; }
        await api.post("/api/geofences", {
          tracker_id: currentTrackerId, name: fd.get("name"), shape, geometry, enabled: true,
        });
        toast(t("geofences.saved"), "success");
        await loadFences();
      },
    });
  });

  trackerSelect.addEventListener("change", () => {
    currentTrackerId = trackerSelect.value ? Number(trackerSelect.value) : null;
    centerOnTracker();
    loadFences();
  });

  centerOnTracker();
  await loadFences();
  setTimeout(() => map.invalidateSize(), 50);

  const unsub = subscribe(() => {});
  const unsubLocale = onLocaleChange(loadFences);
  return () => { unsub(); unsubLocale(); map.remove(); };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
