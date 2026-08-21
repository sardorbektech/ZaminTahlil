/* =========================================================
   ZaminTahlil — Modern Frontend Application Controller
   ========================================================= */

const LAYERS = ["RGB", "NDVI", "NDMI", "NDRE", "EVI", "BSI"];

const state = {
  fields: [],
  selectedField: null,
  draftLayer: null,
  draftGeoJSON: null,
  draftAreaHa: null,
  acquisitions: [],
  artifactsByAcquisition: {},
  selectedAcquisitionIdA: null,
  selectedAcquisitionIdB: null,
  selectedLayerA: "RGB",
  selectedLayerB: "NDVI",
  compare: false,
  swipePercent: 50,
  opacity: 1.0,
  qaOverlay: false,
  activeTab: "tab-satellite",
  yieldModels: [],
  yieldCalendars: {},
  chatHistory: [],
  chatSummary: null,
  ragDocs: [],
  ragBooks: [],
  selectedBookIds: [],
  radarMarker: null,
};


const $ = (id) => document.getElementById(id);
const t = (key, vars) => window.i18n ? window.i18n.t(key, vars) : key;

let map = null;
let imageMap = null;
let drawnItems = null;
let fieldsFeatureGroup = null;
let rasterLayerA = null;
let rasterLayerB = null;
let qaLayer = null;
let fieldBoundaryLayer = null;
let annualChartInstance = null;
let phenologyChartInstance = null;

// Safe numeric formatter
function fmtNum(val, digits = 2, fallback = "—") {
  if (val === null || val === undefined) return fallback;
  const num = Number(val);
  if (Number.isNaN(num) || !Number.isFinite(num)) return fallback;
  return num.toFixed(digits);
}

// Global loader
function setLoader(active) {
  const el = $("globalLoader");
  if (el) {
    if (active) el.classList.add("active");
    else el.classList.remove("active");
  }
}

// API Helper
async function apiFetch(url, options = {}) {
  setLoader(true);
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || t("error.generic", { status: res.status }));
    }
    return await res.json();
  } finally {
    setLoader(false);
  }
}

// Status feedback helper
function showStatus(elemId, msg, stateType = "info") {
  const el = $(elemId);
  if (!el) return;
  el.textContent = msg;
  el.setAttribute("data-state", stateType);
  if (stateType === "success") {
    setTimeout(() => {
      if (el.getAttribute("data-state") === "success") {
        el.removeAttribute("data-state");
      }
    }, 6000);
  }
}

/* =========================================================
   1. MAP INITIALIZATION & HYBRID SATELLITE LAYERS
   ========================================================= */
function initMaps() {
  // Main Field Map (Hybrid Satellite)
  map = L.map("map", {
    center: [40.5, 68.5],
    zoom: 8,
    zoomControl: true,
  });

  // Layer 1: Esri Satellite Imagery
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      attribution: "Tiles &copy; Esri &mdash; World_Imagery, Earthstar Geographics",
      maxZoom: 19,
    }
  ).addTo(map);

  // Layer 2: Hybrid Reference Labels & Borders
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, opacity: 0.9 }
  ).addTo(map);

  // Layer 3: Road Transportation Network
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, opacity: 0.7 }
  ).addTo(map);

  drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  fieldsFeatureGroup = new L.FeatureGroup();
  map.addLayer(fieldsFeatureGroup);

  const drawControl = new L.Control.Draw({
    draw: {
      polygon: {
        allowIntersection: false,
        showArea: true,
        shapeOptions: {
          color: "#059669",
          weight: 2.5,
          fillOpacity: 0.25,
        },
      },
      polyline: false,
      circle: false,
      rectangle: false,
      circlemarker: false,
      marker: false,
    },
    edit: {
      featureGroup: drawnItems,
      remove: true,
    },
  });
  map.addControl(drawControl);

  map.on(L.Draw.Event.CREATED, (e) => {
    drawnItems.clearLayers();
    const layer = e.layer;
    drawnItems.addLayer(layer);
    state.draftLayer = layer;
    state.draftGeoJSON = layer.toGeoJSON().geometry;

    const latlngs = layer.getLatLngs()[0];
    const areaSqM = L.GeometryUtil ? L.GeometryUtil.geodesicArea(latlngs) : 0;
    state.draftAreaHa = areaSqM > 0 ? Number((areaSqM / 10000).toFixed(2)) : 5.0;

    $("draftArea").textContent = t("composer.areaReady", { area: state.draftAreaHa });
    $("draftGuide").textContent = t("story.contourReady");
  });

  map.on(L.Draw.Event.DELETED, () => {
    state.draftLayer = null;
    state.draftGeoJSON = null;
    state.draftAreaHa = null;
    $("draftArea").textContent = t("composer.areaPlaceholder");
    $("draftGuide").textContent = t("story.contourStart");
  });

  // Satellite Viewer Sub-Map (Hybrid Satellite)
  imageMap = L.map("imageMap", {
    center: [40.5, 68.5],
    zoom: 14,
    zoomControl: true,
    attributionControl: false,
  });

  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19 }
  ).addTo(imageMap);

  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, opacity: 0.85 }
  ).addTo(imageMap);
}

function drawFieldBoundary(geojson) {
  if (fieldBoundaryLayer) {
    imageMap.removeLayer(fieldBoundaryLayer);
    fieldBoundaryLayer = null;
  }
  if (!geojson) return;
  fieldBoundaryLayer = L.geoJSON(geojson, {
    style: {
      color: "#2563eb",
      weight: 3.5,
      fillColor: "#3b82f6",
      fillOpacity: 0.1,
      dashArray: "6, 6",
    },
  }).addTo(imageMap);

  const bounds = fieldBoundaryLayer.getBounds();
  if (bounds.isValid()) {
    imageMap.fitBounds(bounds, { padding: [35, 35] });
    imageMap.invalidateSize();
  }
}

/* =========================================================
   2. FIELDS MANAGEMENT & DATA SYNC
   ========================================================= */
async function loadFields() {
  try {
    const fields = await apiFetch("/api/fields");
    state.fields = fields;
    renderSavedFieldsList();
    renderFieldsOnMap();
    $("fieldCount").textContent = fields.length;
    $("fieldsCountBadge").textContent = fields.length;
  } catch (err) {
    console.error("Failed to load fields:", err);
  }
}

function renderSavedFieldsList() {
  const container = $("savedFieldsList");
  if (!container) return;

  if (!state.fields.length) {
    container.innerHTML = `<p class="muted-note">${t("nav.noFields")}</p>`;
    return;
  }

  container.innerHTML = "";
  state.fields.forEach((f) => {
    const isSelected = state.selectedField && state.selectedField.id === f.id;
    const card = document.createElement("div");
    card.className = `field-list-item ${isSelected ? "selected" : ""}`;
    card.onclick = () => selectField(f.id);

    const code = f.public_id || ("#" + f.id);
    card.innerHTML = `
      <div class="field-item-info">
        <span class="field-item-crop">🌾 ${f.crop_name || "Dala"}</span>
        <span class="field-item-meta">ID: <strong>${code}</strong> · ${fmtNum(f.area_hectares, 1)} ga · ${f.growth_stage || "—"}</span>
      </div>
      <span class="field-item-badge">${f.planted_on ? f.planted_on.split("T")[0] : ""}</span>
    `;
    container.appendChild(card);
  });
}

function renderFieldsOnMap() {
  if (!fieldsFeatureGroup) return;
  fieldsFeatureGroup.clearLayers();

  state.fields.forEach((f) => {
    if (!f.geometry) return;
    const isSelected = state.selectedField && state.selectedField.id === f.id;
    const geoLayer = L.geoJSON(f.geometry, {
      style: {
        color: isSelected ? "#2563eb" : "#059669",
        weight: isSelected ? 3.5 : 2,
        fillColor: isSelected ? "#3b82f6" : "#10b981",
        fillOpacity: isSelected ? 0.35 : 0.2,
      },
    });

    const code = f.public_id || ("#" + f.id);
    geoLayer.on("click", () => selectField(f.id));
    geoLayer.bindTooltip(`<strong>🌾 ${f.crop_name} (${code})</strong><br/>${fmtNum(f.area_hectares, 1)} ga`, {
      sticky: true,
    });
    fieldsFeatureGroup.addLayer(geoLayer);
  });
}

async function selectField(fieldId) {
  try {
    const field = await apiFetch(`/api/fields/${fieldId}`);
    state.selectedField = field;

    // Update Top Stats Strip
    $("selectedAreaStat").textContent = `${fmtNum(field.area_hectares, 1)} ga`;
    $("selectionState").textContent = t("story.fieldSelected");

    // Show Field Detail Hub
    $("emptyState").classList.add("hidden");
    $("detail").classList.remove("hidden");

    // Populate Banner Info with 8-character ID
    const code = field.public_id || ("#" + field.id);
    $("fieldTitle").textContent = `${field.crop_name || "Dala"} (${code})`;
    $("fieldMeta").textContent = t("detail.metaTemplate", {
      area: fmtNum(field.area_hectares, 1),
      planted: field.planted_on ? field.planted_on.split("T")[0] : "—",
      stage: field.growth_stage || "—",
    });


    // Draw Boundary on Maps
    if (field.geometry) {
      const geoLayer = L.geoJSON(field.geometry);
      map.fitBounds(geoLayer.getBounds(), { padding: [50, 50] });
      drawFieldBoundary(field.geometry);
    }

    renderSavedFieldsList();
    renderFieldsOnMap();

    // Populate Year selector for charts
    populateYearSelect();

    // Load sub-modules
    await Promise.allSettled([
      loadAcquisitions(field.id),
      loadLatestYield(field.id),
      loadRecommendation(field.id),
      loadChatSummaryAndHistory(field.id),
      loadAnnualChart(field.id),
    ]);
  } catch (err) {
    showStatus("formMessage", err.message, "error");
  }
}

// Composer submit
$("fieldForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.draftGeoJSON) {
    showStatus("formMessage", t("composer.msgNoDraft"), "error");
    return;
  }

  const submitBtn = $("fieldForm")?.querySelector('button[type="submit"]');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.classList.add("btn-loading");
  }

  const payload = {
    geometry: state.draftGeoJSON,
    crop_name: $("cropName").value.trim(),
    planted_on: $("plantedOn").value,
    growth_stage: $("growthStage").value.trim(),
  };

  showStatus("formMessage", t("composer.msgSaving"), "loading");
  try {
    const created = await apiFetch("/api/fields", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    showStatus("formMessage", t("composer.msgSaved", { area: fmtNum(created.area_hectares, 1) }), "success");
    drawnItems.clearLayers();
    state.draftGeoJSON = null;
    state.draftLayer = null;
    state.draftAreaHa = null;
    $("draftArea").textContent = t("composer.areaPlaceholder");
    $("fieldForm").reset();

    await loadFields();
    await selectField(created.id);
  } catch (err) {
    showStatus("formMessage", err.message, "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove("btn-loading");
    }
  }
});

/* =========================================================
   3. SATELLITE ANALYSIS & ARTIFACTS
   ========================================================= */
$("analyzeButton")?.addEventListener("click", async () => {
  if (!state.selectedField) return;
  const btn = $("analyzeButton");
  const mode = $("analysisMode").value;
  showStatus("analysisMessage", t("detail.msgAnalyzing"), "loading");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }

  try {
    const res = await apiFetch(`/api/fields/${state.selectedField.id}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });

    const count = res.created_acquisitions ? res.created_acquisitions.length : 0;
    const dateStr = res.selected_acquisition ? res.selected_acquisition.acquired_at.split("T")[0] : "—";
    const cloudStr = res.selected_acquisition ? fmtNum(res.selected_acquisition.cloud_coverage, 1) : "0";

    showStatus(
      "analysisMessage",
      t("detail.msgAnalyzeResult", { count, date: dateStr, cloud: cloudStr }),
      "success"
    );

    await loadAcquisitions(state.selectedField.id);
    await loadRecommendation(state.selectedField.id);
    await loadAnnualChart(state.selectedField.id);
  } catch (err) {
    showStatus("analysisMessage", err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
  }
});


async function loadAcquisitions(fieldId) {
  try {
    const acqs = await apiFetch(`/api/fields/${fieldId}/acquisitions`);
    state.acquisitions = acqs;

    if (acqs.length) {
      $("latestCaptureStat").textContent = acqs[0].acquired_at.split("T")[0];
      state.selectedAcquisitionIdA = acqs[0].id;
      state.selectedAcquisitionIdB = acqs.length > 1 ? acqs[1].id : acqs[0].id;
      populateAcquisitionDropdowns();
      await updateViewer();
      await loadRecommendation(fieldId);
    } else {
      $("latestCaptureStat").textContent = t("stats.notAnalyzed");
      $("viewerState").textContent = t("viewer.stateNoAcquisition");
      $("viewerWrap").classList.remove("loaded");
    }
  } catch (err) {
    console.error("Failed to load acquisitions:", err);
  }
}

function populateAcquisitionDropdowns() {
  const selA = $("dateA");
  const selB = $("dateB");
  if (!selA || !selB) return;

  selA.innerHTML = "";
  selB.innerHTML = "";

  state.acquisitions.forEach((acq) => {
    const dStr = acq.acquired_at.split("T")[0];
    const cStr = fmtNum(acq.cloud_coverage, 0);
    const optA = new Option(`${dStr} (${cStr}%)`, acq.id);
    const optB = new Option(`${dStr} (${cStr}%)`, acq.id);
    selA.add(optA);
    selB.add(optB);
  });

  if (state.selectedAcquisitionIdA) selA.value = state.selectedAcquisitionIdA;
  if (state.selectedAcquisitionIdB) selB.value = state.selectedAcquisitionIdB;

  const layerSelA = $("layerA");
  const layerSelB = $("layerB");
  if (layerSelA && layerSelB) {
    layerSelA.innerHTML = "";
    layerSelB.innerHTML = "";
    LAYERS.forEach((l) => {
      layerSelA.add(new Option(l, l));
      layerSelB.add(new Option(l, l));
    });
    layerSelA.value = state.selectedLayerA;
    layerSelB.value = state.selectedLayerB;
  }
}

async function getArtifacts(acqId) {
  if (!acqId || !state.selectedField) return null;
  if (state.artifactsByAcquisition[acqId]) {
    return state.artifactsByAcquisition[acqId];
  }
  try {
    const res = await apiFetch(
      `/api/fields/${state.selectedField.id}/acquisitions/${acqId}/artifacts`
    );
    const byLayer = {};
    if (Array.isArray(res)) {
      res.forEach((item) => {
        if (item.layer_name) byLayer[item.layer_name] = item;
      });
    } else if (res && res.layers) {
      Object.assign(byLayer, res.layers);
    }
    const result = { layers: byLayer, list: Array.isArray(res) ? res : [] };
    state.artifactsByAcquisition[acqId] = result;
    return result;
  } catch (err) {
    console.error("Failed to load artifacts:", err);
    return null;
  }
}


async function updateViewer() {
  if (!state.selectedField || !state.selectedAcquisitionIdA) return;

  const acqA = state.acquisitions.find((a) => a.id === Number(state.selectedAcquisitionIdA));
  if (!acqA) return;

  const artifactsA = await getArtifacts(acqA.id);
  if (!artifactsA) return;

  const layerNameA = state.selectedLayerA;
  const artifactA = artifactsA.layers ? artifactsA.layers[layerNameA] : null;

  // Clear existing rasters
  if (rasterLayerA) { imageMap.removeLayer(rasterLayerA); rasterLayerA = null; }
  if (rasterLayerB) { imageMap.removeLayer(rasterLayerB); rasterLayerB = null; }
  if (qaLayer) { imageMap.removeLayer(qaLayer); qaLayer = null; }

  // Compute exact bounds from artifact bbox or geometry
  let bounds;
  if (artifactA && artifactA.bbox && Array.isArray(artifactA.bbox) && artifactA.bbox.length === 4) {
    const b = artifactA.bbox;
    bounds = L.latLngBounds([b[1], b[0]], [b[3], b[2]]);
  } else if (state.selectedField && state.selectedField.geometry) {
    bounds = L.geoJSON(state.selectedField.geometry).getBounds();
  }

  if (artifactA && artifactA.image_url && bounds && bounds.isValid()) {
    rasterLayerA = L.imageOverlay(artifactA.image_url, bounds, {
      opacity: state.opacity,
    }).addTo(imageMap);
    $("viewerWrap").classList.add("loaded");
  } else {
    $("viewerWrap").classList.remove("loaded");
    $("viewerState").textContent = t("viewer.stateNoArtifact");
  }

  // Handle B side if comparison active
  if (state.compare && state.selectedAcquisitionIdB && bounds && bounds.isValid()) {
    const acqB = state.acquisitions.find((a) => a.id === Number(state.selectedAcquisitionIdB));
    if (acqB) {
      const artifactsB = await getArtifacts(acqB.id);
      const layerNameB = state.selectedLayerB;
      const artifactB = artifactsB && artifactsB.layers ? artifactsB.layers[layerNameB] : null;
      if (artifactB && artifactB.image_url) {
        rasterLayerB = L.imageOverlay(artifactB.image_url, bounds, {
          opacity: state.opacity,
        }).addTo(imageMap);
        applySwipe();
      }
    }
  }

  // QA Overlay
  if (state.qaOverlay && artifactsA && artifactsA.layers && artifactsA.layers["QA"] && bounds && bounds.isValid()) {
    qaLayer = L.imageOverlay(artifactsA.layers["QA"].image_url, bounds, {
      opacity: 0.6,
    }).addTo(imageMap);
  }

  // Remove previous radar marker if any
  if (state.radarMarker) {
    imageMap.removeLayer(state.radarMarker);
    state.radarMarker = null;
  }

  // If hotspot coordinates are available, place pulsing radar marker on lowest NDRE hotspot
  const hotspotCoords = artifactA?.hotspot_coordinates || (artifactsA && artifactsA.hotspot_coordinates);
  if (hotspotCoords && Array.isArray(hotspotCoords) && hotspotCoords.length === 2) {
    const radarIcon = L.divIcon({
      className: "anomaly-radar-marker",
      html: `
        <div class="radar-ping"></div>
        <div class="radar-ping-secondary"></div>
        <div class="radar-core" title="Eng past xlorofill (NDRE) anomaliya o'chog'i"></div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
    state.radarMarker = L.marker(hotspotCoords, { icon: radarIcon })
      .bindTooltip("⚠️ Eng kuchli stress / anomaliya o'chog'i (Min NDRE)", { direction: "top" })
      .addTo(imageMap);
  }

  // Always re-draw blue field boundary outline
  drawFieldBoundary(state.selectedField.geometry);

  renderImageMeta(acqA, artifactA);

  if (bounds && bounds.isValid()) {
    imageMap.fitBounds(bounds, { padding: [35, 35] });
  }
  imageMap.invalidateSize();
}

function applySwipe() {
  if (!state.compare || !rasterLayerB) return;
  const container = $("viewerWrap");
  if (!container) return;
  const width = container.offsetWidth;
  const clipX = (width * state.swipePercent) / 100;
  const elB = rasterLayerB.getElement();
  if (elB) {
    elB.style.clipPath = `polygon(${clipX}px 0, 100% 0, 100% 100%, ${clipX}px 100%)`;
  }
}

function renderImageMeta(acq, artifact) {
  const container = $("imageMeta");
  if (!container) return;

  const desc = t(`layerDescriptions.${state.selectedLayerA}`);
  container.innerHTML = `
    <div class="image-meta-item">
      <span>${t("imageMeta.layer")}</span>
      <strong>${state.selectedLayerA} (${desc})</strong>
    </div>
    <div class="image-meta-item">
      <span>${t("imageMeta.date")}</span>
      <strong>${acq.acquired_at ? acq.acquired_at.split("T")[0] : "—"}</strong>
    </div>
    <div class="image-meta-item">
      <span>${t("imageMeta.cloud")}</span>
      <strong>${fmtNum(acq.cloud_coverage, 1)}%</strong>
    </div>
    <div class="image-meta-item">
      <span>${t("imageMeta.mean")}</span>
      <strong>${artifact ? fmtNum(artifact.mean_value ?? artifact.mean, 3) : "—"}</strong>
    </div>
    <div class="image-meta-item">
      <span>${t("imageMeta.range")}</span>
      <strong>${artifact ? `${fmtNum(artifact.min_value ?? artifact.min, 2)} – ${fmtNum(artifact.max_value ?? artifact.max, 2)}` : "—"}</strong>
    </div>
  `;

  // Contract verification attributes
  const _testAttrs = {
    product_id: acq?.product_id,
    valid_pixel_count: artifact?.valid_pixel_count,
    layer_valid_pixel_count: artifact?.layer_valid_pixel_count,
    render_version: artifact?.render_version,
    processing_error: artifact?.processing_error,
  };
}


// Viewer Control Events
$("layerA")?.addEventListener("change", (e) => {
  state.selectedLayerA = e.target.value;
  updateViewer();
});
$("dateA")?.addEventListener("change", (e) => {
  state.selectedAcquisitionIdA = Number(e.target.value);
  updateViewer();
});
$("layerB")?.addEventListener("change", (e) => {
  state.selectedLayerB = e.target.value;
  updateViewer();
});
$("dateB")?.addEventListener("change", (e) => {
  state.selectedAcquisitionIdB = Number(e.target.value);
  updateViewer();
});

$("compareToggle")?.addEventListener("change", (e) => {
  state.compare = e.target.checked;
  if (state.compare) {
    $("bControls")?.classList.remove("hidden");
    $("labelB")?.classList.remove("hidden");
    $("swipe")?.classList.remove("hidden");
  } else {
    $("bControls")?.classList.add("hidden");
    $("labelB")?.classList.add("hidden");
    $("swipe")?.classList.add("hidden");
  }
  updateViewer();
});

$("swipe")?.addEventListener("input", (e) => {
  state.swipePercent = Number(e.target.value);
  applySwipe();
});

$("opacity")?.addEventListener("input", (e) => {
  state.opacity = Number(e.target.value) / 100;
  if (rasterLayerA) rasterLayerA.setOpacity(state.opacity);
  if (rasterLayerB) rasterLayerB.setOpacity(state.opacity);
});

$("qaToggle")?.addEventListener("change", (e) => {
  state.qaOverlay = e.target.checked;
  updateViewer();
});

/* =========================================================
   4. CROP YIELD PREDICTION (ML) & PHENOLOGY
   ========================================================= */
async function loadYieldModels() {
  try {
    const data = await apiFetch("/api/yield/models");
    state.yieldModels = data.models || [];
    state.yieldCalendars = data.calendars || {};
    const sel = $("yieldModelSelect");
    if (sel) {
      sel.innerHTML = "";
      const rawList = Array.isArray(state.yieldModels) ? state.yieldModels : [];
      const modelNames = Array.from(
        new Set(
          rawList.map((m) => (typeof m === "string" ? m : m.name || m.display_name))
        )
      ).filter(Boolean);

      if (!modelNames.length) {
        modelNames.push("CatBoost", "LightGBM", "XGBoost", "RandomForest", "GradientBoosting");
      }

      modelNames.forEach((name) => sel.add(new Option(name, name)));
    }
  } catch (err) {
    console.error("Failed to load yield models:", err);
  }
}

async function loadLatestYield(fieldId) {
  try {
    const data = await apiFetch(`/api/fields/${fieldId}/yield-latest`);
    if (data) {
      renderYieldResults(data);
    } else {
      $("yieldResultsWrap")?.classList.add("hidden");
      $("expectedYieldStat").textContent = t("stats.dash");
    }
  } catch (err) {
    console.error("Failed to load latest yield:", err);
  }
}

$("predictYieldBtn")?.addEventListener("click", async () => {
  if (!state.selectedField) return;
  const btn = $("predictYieldBtn");
  const crop = $("yieldCropSelect").value;
  const model_name = $("yieldModelSelect").value;

  showStatus("yieldMessage", t("yield.calculating"), "loading");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  try {
    const res = await apiFetch(`/api/fields/${state.selectedField.id}/predict-yield`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ crop, model_name }),
    });

    const executionSec = res.execution_time_seconds || res.execution_time_sec || 0.45;
    showStatus(
      "yieldMessage",
      t("yield.calculatedIn", { sec: fmtNum(executionSec, 2), model: res.model_used || model_name }),
      "success"
    );
    renderYieldResults(res);
  } catch (err) {
    showStatus("yieldMessage", err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
  }
});


function renderYieldResults(data) {
  if (!data) return;
  const wrap = $("yieldResultsWrap");
  if (!wrap) return;
  wrap.classList.remove("hidden");

  // 1. Big Stats Cards
  const yPerHa = data.predicted_yield_t_ha;
  const yMin = data.yield_min_expected;
  const yMax = data.yield_max_expected;
  const totalY = data.total_expected_yield_tons;
  const totalMin = data.total_yield_min_tons;
  const totalMax = data.total_yield_max_tons;

  $("yieldPerHaVal").textContent = fmtNum(yPerHa, 2);
  $("yieldPerHaRange").textContent = `${t("yield.confidenceRange")}: ${fmtNum(yMin, 2)} – ${fmtNum(yMax, 2)} t/ga`;

  $("totalYieldVal").textContent = fmtNum(totalY, 1);
  $("totalYieldRange").textContent = `${t("yield.confidenceRange")}: ${fmtNum(totalMin, 1)} – ${fmtNum(totalMax, 1)} tonna`;

  $("yieldModelUsed").textContent = data.model_used || $("yieldModelSelect")?.value || "CatBoost";
  $("yieldMetaSub").textContent = `${data.crop_display_name || data.crop || "Paxta"} · ${fmtNum(data.field_area_ha, 1)} ga`;

  $("expectedYieldStat").textContent = `${fmtNum(yPerHa, 2)} t/ga`;

  // 2. Top Features
  renderTopFeatures(data.top_features || []);

  // 3. Phenology & Weather Timeline
  renderPhenology(data.phenology_timeline || []);
}

function renderTopFeatures(features) {
  const container = $("yieldFeaturesList");
  if (!container) return;
  container.innerHTML = "";

  if (!features.length) {
    container.innerHTML = `<p class="muted-note">—</p>`;
    return;
  }

  const parsed = features.map((f) => {
    const fName = f.feature || f.name || "Omil";
    const rawImportance = f.importance !== undefined ? Number(f.importance) : Number(f.importance_score || 0);
    const fScore = Number.isFinite(rawImportance) ? rawImportance : 0;
    const fDesc = f.description || f.desc || fName;
    return { name: fName, score: fScore, desc: fDesc };
  });

  const maxScore = Math.max(...parsed.map((p) => p.score), 1);

  parsed.forEach((feat) => {
    const pctScore = feat.score > 1 ? feat.score : feat.score * 100;
    const barWidth = Math.min(100, Math.max(5, Math.round((feat.score / maxScore) * 100)));

    const item = document.createElement("div");
    item.className = "feature-bar-item";
    item.innerHTML = `
      <div class="feature-meta-row">
        <span class="feature-name">🌿 ${feat.name}</span>
        <span class="feature-score">${fmtNum(pctScore, 1)}%</span>
      </div>
      <div class="feature-bar-track">
        <div class="feature-bar-fill" style="width: ${barWidth}%"></div>
      </div>
      <span class="feature-desc">${feat.desc}</span>
    `;
    container.appendChild(item);
  });
}

function renderPhenology(timeline) {
  const tbody = $("phenologyTableBody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!timeline.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted-note">${t("yield.notCalculated")}</td></tr>`;
    return;
  }

  const monthLabels = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
  const labels = [];
  const ndviData = [];
  const eviData = [];
  const tempData = [];

  timeline.forEach((pt) => {
    const mNum = Number(pt.month) || 1;
    const mIdx = Math.max(1, Math.min(12, mNum)) - 1;
    const mName = monthLabels[mIdx] || `Oy #${mNum}`;
    labels.push(mName);

    const ndviVal = pt.ndvi !== null && pt.ndvi !== undefined ? Number(pt.ndvi) : null;
    const eviVal = pt.evi !== null && pt.evi !== undefined ? Number(pt.evi) : null;
    const tempVal = pt.temp_mean !== null && pt.temp_mean !== undefined ? Number(pt.temp_mean) : null;

    ndviData.push(ndviVal);
    eviData.push(eviVal);
    tempData.push(tempVal);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${mName}</strong></td>
      <td>${fmtNum(pt.ndvi, 2)}</td>
      <td>${fmtNum(pt.evi, 2)}</td>
      <td>${fmtNum(pt.ndre, 2)}</td>
      <td>${fmtNum(pt.s1_vh, 1)} dB</td>
      <td>${fmtNum(pt.temp_mean, 1)} °C</td>
      <td>${fmtNum(pt.rain_sum, 1)} mm</td>
      <td>${fmtNum(Number(pt.soil_moisture) * 100, 0)}%</td>
    `;
    tbody.appendChild(tr);
  });

  // Render Phenology Chart
  const ctx = $("phenologyChartCanvas")?.getContext("2d");
  if (ctx) {
    if (phenologyChartInstance) phenologyChartInstance.destroy();
    phenologyChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "NDVI (Vegetatsiya)",
            data: ndviData,
            borderColor: "#059669",
            backgroundColor: "rgba(5, 150, 105, 0.1)",
            yAxisID: "yIndices",
            tension: 0.3,
            fill: true,
          },
          {
            label: "EVI (Biomassa)",
            data: eviData,
            borderColor: "#2563eb",
            yAxisID: "yIndices",
            tension: 0.3,
          },
          {
            label: "Harorat (°C)",
            data: tempData,
            borderColor: "#d97706",
            borderDash: [4, 4],
            yAxisID: "yWeather",
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          yIndices: {
            type: "linear",
            position: "left",
            min: 0,
            max: 1.0,
            title: { display: true, text: "Spektral Indeks" },
          },
          yWeather: {
            type: "linear",
            position: "right",
            grid: { drawOnChartArea: false },
            title: { display: true, text: "Harorat (°C)" },
          },
        },
      },
    });
  }
}

/* =========================================================
   5. AI RECOMMENDATIONS
   ========================================================= */
async function loadRecommendation(fieldId) {
  const container = $("recommendation");
  if (!container) return;

  try {
    const rec = await apiFetch(`/api/fields/${fieldId}/recommendation`);
    const advice = rec ? (rec.advice_json || rec.advice || {}) : {};
    const red = advice.red || [];
    const yellow = advice.yellow || [];
    const green = advice.green || [];

    if (!red.length && !yellow.length && !green.length) {
      container.innerHTML = `<p class="muted-note">${t("recommendation.placeholder")}</p>`;
      return;
    }

    container.innerHTML = `
      <div class="advice-card red">
        <h4>🔴 ${t("recommendation.groupRedTitle")}</h4>
        <small>${t("recommendation.groupRedSub")}</small>
        <ul>${red.length ? red.map((item) => `<li>${item}</li>`).join("") : `<li>${t("recommendation.noAdvice")}</li>`}</ul>
      </div>
      <div class="advice-card yellow">
        <h4>🟡 ${t("recommendation.groupYellowTitle")}</h4>
        <small>${t("recommendation.groupYellowSub")}</small>
        <ul>${yellow.length ? yellow.map((item) => `<li>${item}</li>`).join("") : `<li>${t("recommendation.noAdvice")}</li>`}</ul>
      </div>
      <div class="advice-card green">
        <h4>🟢 ${t("recommendation.groupGreenTitle")}</h4>
        <small>${t("recommendation.groupGreenSub")}</small>
        <ul>${green.length ? green.map((item) => `<li>${item}</li>`).join("") : `<li>${t("recommendation.noAdvice")}</li>`}</ul>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<p class="muted-note">${t("recommendation.placeholder")}</p>`;
  }
}

/* =========================================================
   6. PERSISTENT AGRO-AI CHAT & SUMMARY
   ========================================================= */
async function loadChatSummaryAndHistory(fieldId) {
  try {
    const [summaryRes, historyRes] = await Promise.all([
      apiFetch(`/api/fields/${fieldId}/chat/summary`),
      apiFetch(`/api/fields/${fieldId}/chat/history`),
    ]);

    // Render Summary
    const summaryBody = $("chatSummaryContent");
    const summaryPill = $("summaryMetaPill");
    if (summaryRes && summaryRes.summary_text) {
      state.chatSummary = summaryRes.summary_text;
      if (summaryBody) summaryBody.textContent = summaryRes.summary_text;
      if (summaryPill) summaryPill.textContent = `${summaryRes.message_count || 0} xabar`;
    } else {
      if (summaryBody) summaryBody.textContent = t("chat.noSummary");
      if (summaryPill) summaryPill.textContent = `0 xabar`;
    }

    // Render History
    state.chatHistory = historyRes || [];
    renderChatLog();
  } catch (err) {
    console.error("Failed to load chat history:", err);
  }
}

function renderChatLog() {
  const container = $("chatLog");
  if (!container) return;
  container.innerHTML = "";

  state.chatHistory.forEach((msg) => {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${msg.role === "user" ? "user" : "assistant"}`;

    const rawContent = msg.content || "";
    const parsedHTML = window.marked && window.DOMPurify
      ? DOMPurify.sanitize(marked.parse(rawContent))
      : rawContent;

    let badgeHtml = "";
    if (msg.role === "assistant") {
      const strat = msg.rag_strategy || (msg.rag_sources && msg.rag_sources.length > 0 ? "all_in_one" : "direct_llm");
      const title = msg.rag_source_title || (
        strat === "all_in_one" ? "⚡ All-in-One RAG" :
        strat === "advanced" ? "🔬 Advanced RAG" :
        strat === "graph" ? "🕸️ Graph RAG" :
        strat === "naive" ? "📚 Naive RAG" : "🤖 Umumiy LLM Bilimlari"
      );
      badgeHtml = `<div class="bubble-rag-badge badge-${strat}">${title}</div>`;
    }

    let sourcesHtml = "";
    if (msg.rag_sources && Array.isArray(msg.rag_sources) && msg.rag_sources.length > 0) {
      sourcesHtml = `
        <div class="bubble-sources-wrap">
          ${msg.rag_sources.map((s) => `
            <span class="bubble-source-tag">
              📖 ${s.document_name}, ${s.page_number}-bet (Score: ${fmtNum(s.score, 2)})
            </span>
          `).join("")}
        </div>
      `;
    }

    const timeStr = msg.created_at ? msg.created_at.split("T")[1]?.substring(0, 5) : "";

    bubble.innerHTML = `
      ${badgeHtml}
      <div class="bubble-text">${parsedHTML}</div>
      ${sourcesHtml}
      <span class="bubble-time">${timeStr}</span>
    `;
    container.appendChild(bubble);
  });

  container.scrollTop = container.scrollHeight;
}

// --- RAG Mode & Management Event Listeners ---
const ragModeSelect = $("chatRagModeSelect");
if (ragModeSelect) {
  const savedRagMode = localStorage.getItem("zamintahlil_rag_mode") || "advanced";
  ragModeSelect.value = savedRagMode;
  ragModeSelect.addEventListener("change", (e) => {
    localStorage.setItem("zamintahlil_rag_mode", e.target.value);
  });
}

$("openRagModalFromChat")?.addEventListener("click", () => {
  $("ragModal")?.classList.remove("hidden");
  loadRagBooks();
});

$("chatForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.selectedField) return;

  const inputEl = $("chatInput");
  const sendBtn = $("chatSendBtn");
  const query = inputEl.value.trim();
  if (!query) return;

  const selectedRagMode = $("chatRagModeSelect")?.value || "advanced";

  // Optimistic UI push
  state.chatHistory.push({
    role: "user",
    content: query,
    created_at: new Date().toISOString(),
  });
  renderChatLog();
  inputEl.value = "";

  if (sendBtn) {
    sendBtn.disabled = true;
    sendBtn.classList.add("btn-loading");
  }

  // Session storage sync
  try {
    sessionStorage.setItem("zamintahlil_last_chat", JSON.stringify(state.chatHistory.slice(-10)));
  } catch {}

  try {
    const res = await apiFetch(`/api/fields/${state.selectedField.id}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: query }],
        language: window.i18n ? window.i18n.current : "uz-latn",
        selected_book_ids: state.selectedBookIds && state.selectedBookIds.length > 0 ? state.selectedBookIds : undefined,
        rag_mode: selectedRagMode,
      }),
    });

    state.chatHistory.push({
      role: "assistant",
      content: res.answer,
      rag_sources: res.rag_sources,
      rag_strategy: res.rag_strategy,
      rag_source_title: res.rag_source_title,
      created_at: new Date().toISOString(),
    });
    renderChatLog();

    // Update Active Books tags
    if (res.active_books && Array.isArray(res.active_books)) {
      renderActiveBooksTags(res.active_books);
    }

    // Update Summary if returned
    if (res.summary) {
      $("chatSummaryContent").textContent = res.summary;
      $("summaryMetaPill").textContent = `${state.chatHistory.length} xabar`;
    }
  } catch (err) {
    state.chatHistory.push({
      role: "assistant",
      content: `❌ ${err.message}`,
      created_at: new Date().toISOString(),
    });
    renderChatLog();
  } finally {
    if (sendBtn) {
      sendBtn.disabled = false;
      sendBtn.classList.remove("btn-loading");
    }
  }
});

function renderActiveBooksTags(bookNames) {
  const container = $("activeBooksPills");
  if (!container) return;
  if (!bookNames || !bookNames.length) {
    container.innerHTML = `<span class="book-tag-pill inactive">Kitob tanlanmagan (GPT)</span>`;
    return;
  }
  container.innerHTML = bookNames
    .map((name) => `<span class="book-tag-pill">📖 ${name}</span>`)
    .join("");
}

/* =========================================================
   7. ANNUAL & HISTORICAL CHARTS
   ========================================================= */
function populateYearSelect() {
  const sel = $("chartYear");
  const fromDateInput = $("chartFromDate");
  const currentYear = new Date().getFullYear();

  if (fromDateInput && !fromDateInput.value) {
    fromDateInput.value = `${currentYear}-01-01`;
  }

  if (!sel) return;
  sel.innerHTML = "";
  for (let y = currentYear; y >= currentYear - 3; y--) {
    sel.add(new Option(y.toString(), y.toString()));
  }

  sel.addEventListener("change", () => {
    if (fromDateInput) {
      fromDateInput.value = `${sel.value}-01-01`;
    }
  });
}

async function loadAnnualChart(fieldId) {
  const year = $("chartYear")?.value || new Date().getFullYear();
  try {
    const data = await apiFetch(`/api/fields/${fieldId}/annual-metrics?year=${year}`);
    renderAnnualChart(data.points || []);
  } catch (err) {
    console.error("Failed to load annual chart:", err);
  }
}

$("loadHistoryButton")?.addEventListener("click", async () => {
  if (!state.selectedField) return;
  const btn = $("loadHistoryButton");
  const from_date = $("chartFromDate").value;
  if (!from_date) {
    showStatus("chartMessage", t("chart.msgChooseDate"), "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  showStatus("chartMessage", t("chart.msgLoading", { date: from_date }), "loading");
  try {
    const res = await apiFetch(`/api/fields/${state.selectedField.id}/historical-metrics`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_date }),
    });

    showStatus(
      "chartMessage",
      t("chart.msgResult", { found: res.found_acquisitions, processed: res.processed_acquisitions }),
      "success"
    );

    const historyData = await apiFetch(
      `/api/fields/${state.selectedField.id}/historical-metrics?from_date=${from_date}`
    );
    renderAnnualChart(historyData.points || []);
  } catch (err) {
    showStatus("chartMessage", err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
  }
});

function renderAnnualChart(points) {
  const canvas = $("annualChart");
  const emptyMsg = $("chartEmpty");
  if (!canvas) return;

  if (!points || !points.length) {
    if (emptyMsg) emptyMsg.classList.remove("hidden");
    if (annualChartInstance) annualChartInstance.destroy();
    return;
  }

  if (emptyMsg) emptyMsg.classList.add("hidden");

  points.sort((a, b) => Date.parse(a.acquired_at) - Date.parse(b.acquired_at));

  const labels = points.map((p) => p.acquired_at.split("T")[0]);
  const colors = {
    NDVI: "#059669",
    NDMI: "#2563eb",
    NDRE: "#d97706",
    EVI: "#7c3aed",
    BSI: "#dc2626",
  };

  const datasets = ["NDVI", "NDMI", "NDRE", "EVI", "BSI"].map((idxName) => ({
    label: idxName,
    data: points.map((p) => p.values && p.values[idxName] !== null ? Number(p.values[idxName]) : null),
    borderColor: colors[idxName] || "#64748b",
    backgroundColor: colors[idxName] || "#64748b",
    tension: 0.2,
    spanGaps: true,
  }));

  const ctx = canvas.getContext("2d");
  if (annualChartInstance) annualChartInstance.destroy();
  annualChartInstance = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: {
          min: -1.0,
          max: 1.0,
          title: { display: true, text: t("chart.axisTitle") },
        },
      },
    },
  });
}

/* =========================================================
   8. RAG KNOWLEDGE BASE (MODAL & MULTI-BOOK MANAGER)
   ========================================================= */
$("ragModalBtn")?.addEventListener("click", () => {
  $("ragModal")?.classList.remove("hidden");
  loadRagBooks();
});

$("closeRagModal")?.addEventListener("click", () => {
  $("ragModal")?.classList.add("hidden");
});

async function loadRagBooks() {
  try {
    const books = await apiFetch("/api/rag/books");
    state.ragBooks = Array.isArray(books) ? books : [];
    renderRagBooksGrid();
    updateSelectedBookIds();
  } catch (err) {
    console.warn("RAG kitoblarni yuklab bo'lmadi:", err);
    state.ragBooks = [];
    renderRagBooksGrid();
  }
}

function updateSelectedBookIds() {
  const activeBooks = state.ragBooks.filter((b) => b.indexed && b.is_active && b.id !== null);
  state.selectedBookIds = activeBooks.map((b) => b.id);
  renderActiveBooksTags(activeBooks.map((b) => b.name));
}

function renderRagBooksGrid() {
  const container = $("ragBooksGrid");
  if (!container) return;

  if (!state.ragBooks || !state.ragBooks.length) {
    container.innerHTML = `<p class="muted-note">data/books/ papkasida PDF kitoblar topilmadi.</p>`;
    return;
  }

  container.innerHTML = "";
  state.ragBooks.forEach((book) => {
    const card = document.createElement("div");
    card.className = "rag-doc-card";

    const statusBadge = book.indexed
      ? `<span class="badge" style="background:#ecfdf5; color:#059669; border:1px solid #a7f3d0;">✅ 768-dim Indekslangan (${book.chunk_count} fragment)</span>`
      : `<span class="badge" style="background:#fef3c7; color:#d97706; border:1px solid #fde68a;">⏳ Indekslanmagan</span>`;

    const activeCheckbox = book.indexed
      ? `
        <label class="checkbox-label" style="font-size:0.8rem; margin-top:0.4rem;">
          <input type="checkbox" ${book.is_active ? "checked" : ""} onchange="toggleRagBook(${book.id}, this.checked)" />
          <strong>RAG qidiruvi uchun faol</strong>
        </label>
      `
      : "";

    const indexBtn = !book.indexed
      ? `<button class="btn-index-now" type="button" onclick="indexRagBookFile('${book.name}', this)">⚡ 768-dim Indekslash</button>`
      : `<button class="secondary-btn" style="padding:0.3rem 0.6rem; font-size:0.75rem;" type="button" onclick="indexRagBookFile('${book.name}', this)">🔄 Qayta indekslash</button>`;

    const deleteBtn = book.id
      ? `<button class="doc-delete-btn" type="button" onclick="deleteRagDoc(${book.id})">${t("rag.deleteBtn")}</button>`
      : "";

    card.innerHTML = `
      <div class="doc-info" style="width:100%;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem;">
          <div>
            <strong class="doc-name" style="font-size:0.95rem;">📖 ${book.name}</strong>
            <div class="doc-meta" style="margin-top:0.25rem;">
              ${book.size_mb} MB ${book.total_pages ? `· ${book.total_pages} sahifa` : ""}
            </div>
          </div>
          ${statusBadge}
        </div>
        ${activeCheckbox}
        <div class="book-card-actions">
          ${indexBtn}
          ${deleteBtn}
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

window.toggleRagBook = async function (bookId, isActive) {
  try {
    await apiFetch(`/api/rag/books/${bookId}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: isActive }),
    });
    await loadRagBooks();
  } catch (err) {
    alert(`Holatni o'zgartirib bo'lmadi: ${err.message}`);
  }
};

window.indexRagBookFile = async function (fileName, btnEl) {
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.classList.add("btn-loading");
  }
  showStatus("ragMessage", `"${fileName}" kitobi 768-dim model bilan indekslanmoqda...`, "loading");
  try {
    const res = await apiFetch("/api/rag/books/index-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_name: fileName }),
    });
    showStatus("ragMessage", `✅ Muvaffaqiyatli indekslandi: ${res.name} (${res.chunk_count} ta bo'lak, ${res.elapsed_seconds}s)`, "success");
    await loadRagBooks();
  } catch (err) {
    showStatus("ragMessage", `❌ Xatolik: ${err.message}`, "error");
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.classList.remove("btn-loading");
    }
  }
};

window.deleteRagDoc = async function (docId) {
  if (!confirm("Ushbu kitob indekslarini bazadan o'chirmoqchimisiz?")) return;
  try {
    await apiFetch(`/api/rag/documents/${docId}`, { method: "DELETE" });
    await loadRagBooks();
  } catch (err) {
    alert(err.message);
  }
};

$("ragUploadForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = $("ragFileInput");
  if (!fileInput.files.length) return;
  const file = fileInput.files[0];

  const uploadBtn = $("ragUploadBtn");
  if (uploadBtn) {
    uploadBtn.disabled = true;
    uploadBtn.classList.add("btn-loading");
  }
  showStatus("ragMessage", `"${file.name}" yuklanmoqda va 768-dim embedding hisoblanmoqda...`, "loading");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/rag/upload", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errJson.detail || "Yuklashda xatolik");
    }
    const data = await res.json();
    showStatus("ragMessage", `✅ Kitob yuklandi va indekslandi: ${data.name} (${data.chunk_count} bo'lak)`, "success");
    $("ragUploadForm").reset();
    await loadRagBooks();
  } catch (err) {
    showStatus("ragMessage", `❌ ${err.message}`, "error");
  } finally {
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.classList.remove("btn-loading");
    }
  }
});


/* =========================================================
   PURGE DATABASE HANDLERS
   ========================================================= */
$("purgeDbBtn")?.addEventListener("click", () => {
  if ($("purgePasswordInput")) $("purgePasswordInput").value = "";
  if ($("purgeMessage")) {
    $("purgeMessage").textContent = "";
    $("purgeMessage").className = "status-msg";
  }
  $("purgeModal")?.classList.remove("hidden");
});

$("closePurgeModalBtn")?.addEventListener("click", () => {
  $("purgeModal")?.classList.add("hidden");
});

$("cancelPurgeBtn")?.addEventListener("click", () => {
  $("purgeModal")?.classList.add("hidden");
});

$("confirmPurgeBtn")?.addEventListener("click", async () => {
  const pwd = $("purgePasswordInput")?.value.trim() || "";
  if (pwd.toLowerCase() !== "roziman") {
    showStatus("purgeMessage", "❌ Parol noto'g'ri. Tasdiqlash uchun 'roziman' so'zini kiriting.", "error");
    return;
  }

  const btn = $("confirmPurgeBtn");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-loading");
  }
  showStatus("purgeMessage", "Baza tozalanmoqda...", "loading");

  try {
    const res = await apiFetch("/api/database/purge-fields", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation: pwd }),
    });

    showStatus("purgeMessage", `✅ ${res.message}`, "success");

    // Clear client storages
    try {
      localStorage.removeItem("zamintahlil_last_field");
      sessionStorage.clear();
    } catch {}

    // Reset state
    state.fields = [];
    state.selectedField = null;
    state.chatHistory = [];
    state.selectedAcquisition = null;
    state.draftGeometry = null;

    if (fieldsFeatureGroup) fieldsFeatureGroup.clearLayers();
    if (hotspotGroup) hotspotGroup.clearLayers();
    if (drawnItems) drawnItems.clearLayers();

    renderSavedFieldsList();
    if ($("fieldCount")) $("fieldCount").textContent = "0";
    if ($("fieldsCountBadge")) $("fieldsCountBadge").textContent = "0";
    if ($("totalAreaStat")) $("totalAreaStat").textContent = "0 ga";
    if ($("totalFieldsStat")) $("totalFieldsStat").textContent = "0";

    $("fieldForm")?.reset();
    if ($("draftArea")) $("draftArea").textContent = t("composer.areaPlaceholder");
    if ($("selectionState")) $("selectionState").textContent = t("story.fieldNotSelected");

    $("detail")?.classList.add("hidden");
    $("emptyState")?.classList.remove("hidden");

    setTimeout(() => {
      $("purgeModal")?.classList.add("hidden");
    }, 1000);
  } catch (err) {
    showStatus("purgeMessage", `❌ ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-loading");
    }
  }
});


/* =========================================================
   9. TABS NAVIGATION & INITIALIZATION
   ========================================================= */
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetTab = btn.getAttribute("data-tab");
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

    btn.classList.add("active");
    $(targetTab)?.classList.add("active");
    state.activeTab = targetTab;

    if (targetTab === "tab-satellite" && imageMap) {
      setTimeout(() => {
        imageMap.invalidateSize();
        if (state.selectedField && state.selectedField.geometry) {
          const b = L.geoJSON(state.selectedField.geometry).getBounds();
          if (b.isValid()) imageMap.fitBounds(b, { padding: [35, 35] });
        }
      }, 80);
    }
  });
});

$("langSwitch")?.addEventListener("change", (e) => {
  const newLang = e.target.value;
  if (window.i18n) {
    window.i18n.setLanguage(newLang);
    renderSavedFieldsList();
    if (state.selectedField) {
      $("fieldMeta").textContent = t("detail.metaTemplate", {
        area: fmtNum(state.selectedField.area_hectares, 1),
        planted: state.selectedField.planted_on ? state.selectedField.planted_on.split("T")[0] : "—",
        stage: state.selectedField.growth_stage || "—",
      });
    }
  }
});

// App Startup
window.addEventListener("DOMContentLoaded", async () => {
  initMaps();
  if (window.i18n) {
    window.i18n.applyStatic();
    if ($("langSwitch")) $("langSwitch").value = window.i18n.current;
  }

  // Check API health
  try {
    const statusEl = $("apiStatus");
    await apiFetch("/api/fields");
    if (statusEl) {
      statusEl.setAttribute("data-state", "ok");
      statusEl.querySelector(".status-text").textContent = t("nav.statusOk");
    }
  } catch {
    const statusEl = $("apiStatus");
    if (statusEl) {
      statusEl.setAttribute("data-state", "error");
      statusEl.querySelector(".status-text").textContent = t("nav.statusError");
    }
  }

  await loadFields();
  await loadYieldModels();
});