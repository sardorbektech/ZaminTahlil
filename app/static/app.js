/**
 * app.js \u2014 ZaminTahlil AgriTech Decision-Support Platform
 * Manages State, Leaflet GIS, Chart.js Analytics, ML Yield Prediction,
 * AI Agronomist Chat, Knowledge Base, and System Maintenance.
 */

(function () {
  "use strict";

  // Contract: Supported spectral layers
  const LAYERS = ["RGB", "NDVI", "NDMI", "NDRE", "EVI", "BSI"];

  // Application State
  const state = {
    fields: [],
    selectedField: null,
    acquisitions: [],
    selectedAcquisition: null,
    selectedLayer: "NDVI",
    compare: false,
    compareLayerA: "NDVI",
    compareLayerB: "NDMI",
    compareAcqIdA: null,
    compareAcqIdB: null,
    swipePercent: 50,
    currentView: "dashboard",
    ragMode: "advanced",
    yieldModel: "CatBoost",
    cachedArtifacts: new Map(),
    charts: {
      monitoring: null,
      phenology: null,
    },
    maps: {
      main: null,
      wizard: null,
      drawnItems: null,
      fieldBoundaryLayer: null,
      rasterOverlayA: null,
      rasterOverlayB: null,
      hotspotMarker: null,
    },
    wizardDraft: null,
    currentUser: null,
  };

  // Expose state globally for API synchronization
  window.state = state;

  // Toast Notification System
  function showToast(message, type = "success") {
    const container = document.getElementById("global-toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === "success" ? "\u2713" : type === "error" ? "\u2715" : "\u2139";
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Date Formatting Helper
  function formatDateUI(dateString) {
    if (!dateString) return "\u2014";
    try {
      const d = new Date(dateString);
      if (isNaN(d.getTime())) return dateString;
      return d.toLocaleDateString(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    } catch {
      return dateString;
    }
  }

  // Format month and day for chart ticks
  function formatChartDate(dateString) {
    if (!dateString) return "";
    try {
      const parsed = Date.parse(dateString);
      if (isNaN(parsed)) return dateString;
      const d = new Date(parsed);
      return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
    } catch {
      return dateString;
    }
  }

  // Acquisition deduplication by calendar date (Lowest cloud coverage per day)
  function deduplicateAcquisitionsByDay(list) {
    if (!Array.isArray(list)) return [];
    const byDate = new Map();
    for (const item of list) {
      const d = (item.acquired_at || "").split("T")[0];
      if (!byDate.has(d)) {
        byDate.set(d, item);
      } else {
        const prev = byDate.get(d);
        const prevCloud = prev.cloud_coverage ?? 100;
        const currCloud = item.cloud_coverage ?? 100;
        if (currCloud < prevCloud) {
          byDate.set(d, item);
        }
      }
    }
    return Array.from(byDate.values()).sort(
      (a, b) => new Date(b.acquired_at) - new Date(a.acquired_at)
    );
  }

  // Update spectral layer chips state (Enabled only if acquisitions exist)
  function updateLayerChipsState(hasAcquisitions) {
    document.querySelectorAll(".layer-chip").forEach((chip) => {
      chip.disabled = !hasAcquisitions;
      if (!hasAcquisitions) {
        chip.style.opacity = "0.4";
        chip.style.cursor = "not-allowed";
        chip.style.pointerEvents = "none";
      } else {
        chip.style.opacity = "1";
        chip.style.cursor = "pointer";
        chip.style.pointerEvents = "auto";
      }
    });
  }

  // View Navigation Router
  function switchView(viewName) {
    state.currentView = viewName;
    document.querySelectorAll(".nav-item").forEach((item) => {
      if (item.getAttribute("data-view") === viewName) {
        item.classList.add("active");
      } else {
        item.classList.remove("active");
      }
    });

    document.querySelectorAll(".view-container").forEach((view) => {
      if (view.id === `view-${viewName}`) {
        view.classList.add("active");
      } else {
        view.classList.remove("active");
      }
    });

    const imageMap = state.maps.main;
    if (viewName === "satellite" && imageMap) {
      setTimeout(() => {
        imageMap.invalidateSize();
        if (state.maps.fieldBoundaryLayer) {
          imageMap.fitBounds(state.maps.fieldBoundaryLayer.getBounds(), { padding: [30, 30] });
        }
      }, 100);
    } else if (viewName === "monitoring") {
      renderMonitoringChart();
    } else if (viewName === "yield") {
      updateYieldFieldSelect();
    } else if (viewName === "knowledge") {
      loadKnowledgeBaseBooks();
    }
  }

  // Record recently viewed field in Session Storage
  function recordRecentField(field) {
    if (!field || !field.id) return;
    try {
      const raw = sessionStorage.getItem("zamintahlil_recent_fields");
      let recent = raw ? JSON.parse(raw) : [];
      recent = recent.filter((f) => f.id !== field.id);
      recent.push({
        id: field.id,
        crop_name: field.crop_name,
        area_hectares: field.area_hectares,
        updated_at: new Date().toISOString(),
      });
      sessionStorage.setItem(
        "zamintahlil_recent_fields",
        JSON.stringify(recent.slice(-10))
      );
    } catch {
      // Ignore sessionStorage restrictions
    }
  }

  // Leaflet Map Initialization
  function initMainMap() {
    const mapEl = document.getElementById("satellite-map");
    if (!mapEl || state.maps.main) return;

    // Esri World Imagery Base Layer
    const esriWorldImagery = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
        maxZoom: 19,
      }
    );

    const imageMap = L.map("satellite-map", {
      center: [41.311081, 69.240562],
      zoom: 12,
      zoomControl: true,
      layers: [esriWorldImagery],
    });

    imageMap.on("zoomend moveend", () => {
      if (state.compare) {
        applySwipe();
      }
    });

    state.maps.main = imageMap;
  }

  // Draw Field Boundary Polygon on Map
  function drawFieldBoundary(geometry) {
    const imageMap = state.maps.main;
    if (!imageMap || !geometry) return;

    if (state.maps.fieldBoundaryLayer) {
      imageMap.removeLayer(state.maps.fieldBoundaryLayer);
      state.maps.fieldBoundaryLayer = null;
    }

    const boundary = L.geoJSON(geometry, {
      style: {
        color: "#22c55e",
        weight: 3,
        fillColor: "#16a34a",
        fillOpacity: 0.12,
        dashArray: "4, 4",
      },
    }).addTo(imageMap);

    state.maps.fieldBoundaryLayer = boundary;
    imageMap.fitBounds(boundary.getBounds(), { padding: [40, 40] });
    imageMap.invalidateSize();
  }

  // Apply A/B Swipe Split Clipping
  function applySwipe() {
    const divider = document.getElementById("swipe-divider-line");
    const overlayA = state.maps.rasterOverlayA;
    const overlayB = state.maps.rasterOverlayB;

    if (!state.compare) {
      if (divider) divider.style.display = "none";
      if (overlayA && overlayA.getElement()) {
        overlayA.getElement().style.clipPath = "none";
        overlayA.setOpacity(0.9);
      }
      if (overlayB) {
        overlayB.setOpacity(0);
      }
      return;
    }

    if (divider) {
      divider.style.display = "block";
      divider.style.left = `${state.swipePercent}%`;
    }

    const percent = state.swipePercent;
    if (overlayA && overlayA.getElement()) {
      overlayA.setOpacity(1);
      overlayA.getElement().style.clipPath = `polygon(0 0, ${percent}% 0, ${percent}% 100%, 0 100%)`;
    }
    if (overlayB && overlayB.getElement()) {
      overlayB.setOpacity(1);
      overlayB.getElement().style.clipPath = `polygon(${percent}% 0, 100% 0, 100% 100%, ${percent}% 100%)`;
    }
  }

  // Update comparison date dropdowns
  function updateCompareDateDropdowns() {
    const dateA = document.getElementById("compare-date-a");
    const dateB = document.getElementById("compare-date-b");
    if (!dateA || !dateB) return;

    if (!state.acquisitions || !state.acquisitions.length) {
      dateA.innerHTML = '<option value="">\u2014</option>';
      dateB.innerHTML = '<option value="">\u2014</option>';
      return;
    }

    const optionsA = state.acquisitions
      .map((acq, idx) => {
        const d = formatDateUI(acq.acquired_at);
        return `<option value="${acq.id}" ${idx === 0 ? "selected" : ""}>${d}</option>`;
      })
      .join("");

    const optionsB = state.acquisitions
      .map((acq, idx) => {
        const d = formatDateUI(acq.acquired_at);
        const isSel = (state.acquisitions.length > 1 && idx === 1) || (state.acquisitions.length === 1 && idx === 0);
        return `<option value="${acq.id}" ${isSel ? "selected" : ""}>${d}</option>`;
      })
      .join("");

    dateA.innerHTML = optionsA;
    dateB.innerHTML = optionsB;
  }

  // Helper: Get best bounds for raster overlay (Exact artifact bbox or field polygon fallback)
  function getArtifactBounds(artifact) {
    if (artifact && artifact.bbox && Array.isArray(artifact.bbox) && artifact.bbox.length === 4) {
      // GeoJSON bbox: [min_lon, min_lat, max_lon, max_lat] -> Leaflet: [[south, west], [north, east]]
      return L.latLngBounds([
        [artifact.bbox[1], artifact.bbox[0]],
        [artifact.bbox[3], artifact.bbox[2]],
      ]);
    }
    return state.maps.fieldBoundaryLayer ? state.maps.fieldBoundaryLayer.getBounds() : null;
  }

  // Update A/B compare overlays
  async function updateCompareOverlays() {
    const imageMap = state.maps.main;
    if (!imageMap || !state.maps.fieldBoundaryLayer) return;

    if (!state.compare) {
      if (state.maps.rasterOverlayB) {
        imageMap.removeLayer(state.maps.rasterOverlayB);
        state.maps.rasterOverlayB = null;
      }
      applySwipe();
      return;
    }

    const layerA = document.getElementById("compare-layer-a")?.value || "NDVI";
    const dateAVal = document.getElementById("compare-date-a")?.value;
    const acqA = state.acquisitions.find((a) => String(a.id) === String(dateAVal)) || state.selectedAcquisition;

    const layerB = document.getElementById("compare-layer-b")?.value || "NDMI";
    const dateBVal = document.getElementById("compare-date-b")?.value;
    const acqB = state.acquisitions.find((a) => String(a.id) === String(dateBVal)) || state.acquisitions[1] || state.selectedAcquisition;

    const fieldId = state.selectedField?.id;

    if (acqA && fieldId) {
      try {
        let artsA = state.cachedArtifacts.get(acqA.id);
        if (!artsA) {
          artsA = await api.getArtifacts(fieldId, acqA.id);
          state.cachedArtifacts.set(acqA.id, artsA);
        }
        const artA = artsA.find((a) => a.layer_name.toUpperCase() === layerA.toUpperCase()) || artsA[0];
        if (artA) {
          const boundsA = getArtifactBounds(artA);
          const urlA = artA.image_url || `/api/fields/${fieldId}/acquisitions/${acqA.id}/images/${artA.layer_name}`;
          if (state.maps.rasterOverlayA) imageMap.removeLayer(state.maps.rasterOverlayA);
          if (boundsA) {
            state.maps.rasterOverlayA = L.imageOverlay(urlA, boundsA, { opacity: 1, interactive: false }).addTo(imageMap);
          }
        }
      } catch (err) {
        console.error("Failed to load overlay A:", err);
      }
    }

    if (acqB && fieldId) {
      try {
        let artsB = state.cachedArtifacts.get(acqB.id);
        if (!artsB) {
          artsB = await api.getArtifacts(fieldId, acqB.id);
          state.cachedArtifacts.set(acqB.id, artsB);
        }
        const artB = artsB.find((a) => a.layer_name.toUpperCase() === layerB.toUpperCase()) || artsB[0];
        if (artB) {
          const boundsB = getArtifactBounds(artB);
          const urlB = artB.image_url || `/api/fields/${fieldId}/acquisitions/${acqB.id}/images/${artB.layer_name}`;
          if (state.maps.rasterOverlayB) imageMap.removeLayer(state.maps.rasterOverlayB);
          if (boundsB) {
            state.maps.rasterOverlayB = L.imageOverlay(urlB, boundsB, { opacity: 1, interactive: false }).addTo(imageMap);
          }
        }
      } catch (err) {
        console.error("Failed to load overlay B:", err);
      }
    }

    applySwipe();
  }

  // Fetch & Display Satellite Layer Artifacts
  async function loadAcquisitionArtifacts(acquisition) {
    if (!acquisition || !acquisition.id) {
      renderArtifactStats({});
      const warningEl = document.getElementById("map-cloud-warning");
      if (warningEl) warningEl.style.display = "none";
      return;
    }
    state.selectedAcquisition = acquisition;

    // Check cloud coverage and valid pixels for warning banner
    const isCloudy = (acquisition.valid_pixel_count || 0) === 0 || !!acquisition.fully_cloudy;
    const warningEl = document.getElementById("map-cloud-warning");
    const warningText = document.getElementById("map-cloud-warning-text");
    if (warningEl && warningText) {
      if (isCloudy) {
        warningText.textContent = `\u26a0\ufe0f Ushbu sanada (${formatDateUI(acquisition.acquired_at)}) dala to'liq bulut bilan qoplangan (0 ta yaroqli piksel). Xaritada sun'iy yo'ldosh qatlami ko'rinmaydi. Quyidagi ro'yxatdan bulutsiz sanani tanlang.`;
        warningEl.style.display = "flex";
      } else {
        warningEl.style.display = "none";
      }
    }

    try {
      let artifacts = state.cachedArtifacts.get(acquisition.id);
      if (!artifacts) {
        // Endpoint: /artifacts
        const fieldId = acquisition.field_id || (state.selectedField && state.selectedField.id);
        artifacts = await api.getArtifacts(fieldId, acquisition.id);
        state.cachedArtifacts.set(acquisition.id, artifacts);
      }

      // Check for processing error
      if (acquisition.processing_error) {
        showToast(`Tahlilda xatolik: ${acquisition.processing_error}`, "error");
      }

      // Find active layer artifact
      const activeLayer = state.selectedLayer || "NDVI";
      const layerArtifact = artifacts.find(
        (a) => a.layer_name.toUpperCase() === activeLayer.toUpperCase()
      ) || artifacts[0];

      if (layerArtifact) {
        renderArtifactStats(layerArtifact);
        renderRasterOverlay(layerArtifact);
      } else {
        renderArtifactStats({});
      }

      // Hotspot check (Lowest NDRE point)
      renderHotspot(layerArtifact);
    } catch (err) {
      console.error("Failed to load /artifacts:", err);
      renderArtifactStats({});
      showToast(window.i18n ? window.i18n.t("toasts.error", { msg: err.message }) : err.message, "error");
    }
  }

  // Render Raster Layer Overlay on Map
  function renderRasterOverlay(artifact) {
    const imageMap = state.maps.main;
    if (!imageMap || !artifact) return;

    if (state.maps.rasterOverlayA) {
      imageMap.removeLayer(state.maps.rasterOverlayA);
      state.maps.rasterOverlayA = null;
    }

    const imageUrl = artifact.image_url || `/api/artifacts/${artifact.id}/image`;
    const bounds = getArtifactBounds(artifact);
    if (bounds) {
      state.maps.rasterOverlayA = L.imageOverlay(imageUrl, bounds, {
        opacity: 0.9,
        interactive: false,
      }).addTo(imageMap);
    }
  }

  // Render Artifact Statistics
  function renderArtifactStats(artifact) {
    const meanEl = document.getElementById("stat-mean");
    const medianEl = document.getElementById("stat-median");
    const minEl = document.getElementById("stat-min");
    const maxEl = document.getElementById("stat-max");
    const pixelsEl = document.getElementById("stat-pixels");
    const productIdEl = document.getElementById("stat-product-id");
    const versionEl = document.getElementById("stat-render-version");

    if (meanEl) meanEl.textContent = (artifact && artifact.mean_value != null) ? Number(artifact.mean_value).toFixed(2) : "\u2014";
    if (medianEl) medianEl.textContent = (artifact && artifact.median_value != null) ? Number(artifact.median_value).toFixed(2) : "\u2014";
    if (minEl) minEl.textContent = (artifact && artifact.min_value != null) ? Number(artifact.min_value).toFixed(2) : "\u2014";
    if (maxEl) maxEl.textContent = (artifact && artifact.max_value != null) ? Number(artifact.max_value).toFixed(2) : "\u2014";

    // valid_pixel_count & layer_valid_pixel_count
    const validCount = (artifact && artifact.layer_valid_pixel_count) ?? (artifact && artifact.valid_pixel_count) ?? state.selectedAcquisition?.valid_pixel_count ?? "\u2014";
    if (pixelsEl) pixelsEl.textContent = typeof validCount === "number" ? validCount.toLocaleString() : validCount;

    if (productIdEl) productIdEl.textContent = (artifact && artifact.product_id) || state.selectedAcquisition?.product_id || "\u2014";
    if (versionEl) versionEl.textContent = (artifact && artifact.render_version) || "1.0";
  }

  // Hotspot Sonar Radar Marker
  function renderHotspot(artifact) {
    const imageMap = state.maps.main;
    const card = document.getElementById("hotspot-info-card");
    const coordsText = document.getElementById("hotspot-coords-text");

    if (state.maps.hotspotMarker) {
      imageMap.removeLayer(state.maps.hotspotMarker);
      state.maps.hotspotMarker = null;
    }

    const coords = artifact?.hotspot_coordinates;
    if (coords && Array.isArray(coords) && coords.length === 2) {
      const [lat, lon] = coords;
      const sonarIcon = L.divIcon({
        className: "sonar-marker",
        html: '<div class="sonar-ring"></div><div class="sonar-dot"></div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });

      state.maps.hotspotMarker = L.marker([lat, lon], { icon: sonarIcon })
        .addTo(imageMap)
        .bindPopup(`<b>\u26a0\ufe0f Hotspot (Eng past NDRE)</b><br>Koordinata: ${lat.toFixed(6)}, ${lon.toFixed(6)}`);

      if (card && coordsText) {
        card.style.display = "block";
        coordsText.textContent = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
      }
    } else if (card) {
      card.style.display = "none";
    }
  }

  // Render Recommendation Advice Cards (No mock data)
  function renderRecommendations(rec) {
    const container = document.getElementById("satellite-advice-container");
    if (!container) return;

    const redTitle = (window.i18n ? window.i18n.t("recommendation.groupRedTitle") : "") || "Qilinishi shart bo'lgan choralar";
    const yellowTitle = (window.i18n ? window.i18n.t("recommendation.groupYellowTitle") : "") || "Nazorat va ehtiyot choralari";
    const greenTitle = (window.i18n ? window.i18n.t("recommendation.groupGreenTitle") : "") || "Ijobiy rivojlanish jarayonlari";

    if (!rec || !rec.advice || (!rec.advice.red?.length && !rec.advice.yellow?.length && !rec.advice.green?.length)) {
      container.innerHTML = `<p style="font-size: 0.88rem; color: var(--color-text-muted); text-align: center; padding: 24px 0;">Hozircha tavsiyalar mavjud emas. Yuqoridagi "Sun'iy yo'ldoshdan tahlil qilish" tugmasini bosing.</p>`;
      return;
    }

    const groups = rec.advice;
    let html = "";
    if (groups.red && groups.red.length) {
      html += `
        <div class="advice-card red">
          <div class="advice-card-title">\ud83d\udd34 ${redTitle}</div>
          <ul>${groups.red.map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      `;
    }

    if (groups.yellow && groups.yellow.length) {
      html += `
        <div class="advice-card yellow">
          <div class="advice-card-title">\ud83d\udfe1 ${yellowTitle}</div>
          <ul>${groups.yellow.map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      `;
    }

    if (groups.green && groups.green.length) {
      html += `
        <div class="advice-card green">
          <div class="advice-card-title">\ud83d\udfe2 ${greenTitle}</div>
          <ul>${groups.green.map((item) => `<li>${item}</li>`).join("")}</ul>
        </div>
      `;
    }

    container.innerHTML = html;
  }

  // Update yield view field dropdown options
  function updateYieldFieldSelect() {
    const select = document.getElementById("yield-field-select");
    if (!select) return;
    const currentVal = state.selectedField ? String(state.selectedField.id) : "";
    const options = state.fields
      .map(
        (f) =>
          `<option value="${f.id}" ${String(f.id) === currentVal ? "selected" : ""}>${f.crop_name} (${f.area_hectares} ha)</option>`
      )
      .join("");
    select.innerHTML = '<option value="">-- Dalani tanlang --</option>' + options;
    select.value = currentVal;
  }

  // Select Field Handler
  async function selectField(field) {
    if (!field) return;
    state.selectedField = field;
    recordRecentField(field);

    // Update Topbar Badge
    const pill = document.getElementById("current-field-name");
    if (pill) {
      pill.textContent = `${field.crop_name} (${field.area_hectares} ha)`;
    }

    // Update Context in AI Chat
    const ctxCrop = document.getElementById("chat-ctx-crop");
    const ctxArea = document.getElementById("chat-ctx-area");
    if (ctxCrop) ctxCrop.textContent = field.crop_name;
    if (ctxArea) ctxArea.textContent = `${field.area_hectares} ha`;

    // Sync Yield view selector
    updateYieldFieldSelect();

    // Draw field boundary on main map
    drawFieldBoundary(field.geometry);

    // Load Acquisitions
    try {
      const rawAcqs = await api.getAcquisitions(field.id);
      const deduped = deduplicateAcquisitionsByDay(rawAcqs);
      state.acquisitions = deduped;

      updateLayerChipsState(deduped.length > 0);
      updateCompareDateDropdowns();

      if (deduped.length > 0) {
        // Select newest acquisition with valid pixels, fallback to newest overall
        const bestAcq = deduped.find((a) => (a.valid_pixel_count || 0) > 0 && !a.fully_cloudy) || deduped[0];
        renderAcquisitionsList(deduped, bestAcq.id);
        await loadAcquisitionArtifacts(bestAcq);
      } else {
        renderAcquisitionsList([], null);
        renderArtifactStats({});
        const warningEl = document.getElementById("map-cloud-warning");
        if (warningEl) warningEl.style.display = "none";
      }

      // Load Recommendations cleanly
      try {
        const rec = await api.getRecommendation(field.id);
        renderRecommendations(rec);
      } catch {
        renderRecommendations(null);
      }

      // Pre-fill Yield Form
      const cropInput = document.getElementById("yield-crop-select");
      const plantedInput = document.getElementById("yield-planting-date");
      if (cropInput && field.crop_name) {
        cropInput.value =
          field.crop_name.toLowerCase().includes("bug'doy") ||
          field.crop_name.toLowerCase().includes("wheat")
            ? "wheat"
            : "cotton";
      }
      if (plantedInput && field.planted_on) {
        plantedInput.value = field.planted_on;
      }

      // Load Latest Yield & Chat Summary
      loadLatestYield(field.id);
      loadChatSummary(field.id);
      loadChatHistory(field.id);
    } catch (err) {
      console.error("Error selecting field:", err);
    }
  }

  // Render Acquisitions List
  function renderAcquisitionsList(acquisitions, activeId = null) {
    const container = document.getElementById("acquisitions-list-container");
    if (!container) return;

    if (!acquisitions || !acquisitions.length) {
      container.innerHTML = `<p style="font-size: 0.85rem; color: var(--color-text-muted);">${window.i18n ? window.i18n.t("satellite.noAcquisitions") : "Tahlillar mavjud emas"}</p>`;
      return;
    }

    const currentSelectedId = activeId ?? state.selectedAcquisition?.id ?? acquisitions[0]?.id;

    container.innerHTML = acquisitions
      .map((acq) => {
        const d = formatDateUI(acq.acquired_at);
        const cloud = acq.cloud_coverage != null ? `${Math.round(acq.cloud_coverage)}%` : "0%";
        const isValid = (acq.valid_pixel_count || 0) > 0 && !acq.fully_cloudy;
        const badgeText = isValid
          ? `\u2601\ufe0f ${cloud} \u2022 ${Number(acq.valid_pixel_count).toLocaleString()} px`
          : `\u26a0\ufe0f Bulutli (0 px)`;
        const badgeColor = isValid ? "opacity: 0.85;" : "color: #dc2626; font-weight: 600;";
        const activeClass = acq.id === currentSelectedId ? "active" : "";
        return `
          <div class="acq-item ${activeClass}" data-id="${acq.id}" style="display: flex; justify-content: space-between; align-items: center;">
            <span>\ud83d\udcc5 ${d}</span>
            <span style="font-size: 0.76rem; ${badgeColor}">${badgeText}</span>
          </div>
        `;
      })
      .join("");

    container.querySelectorAll(".acq-item").forEach((el) => {
      el.addEventListener("click", () => {
        container.querySelectorAll(".acq-item").forEach((i) => i.classList.remove("active"));
        el.classList.add("active");
        const acqId = parseInt(el.getAttribute("data-id"), 10);
        const target = acquisitions.find((a) => a.id === acqId);
        if (target) loadAcquisitionArtifacts(target);
      });
    });
  }

  // Load All Fields
  async function loadFields() {
    try {
      const fields = await api.getFields();
      state.fields = fields;

      // Update Dashboard Top Metrics
      const totalFieldsEl = document.getElementById("dash-total-fields");
      const totalAreaEl = document.getElementById("dash-total-area");
      const coverageEl = document.getElementById("dash-coverage");

      if (totalFieldsEl) totalFieldsEl.textContent = fields.length;
      if (totalAreaEl) {
        const sumArea = fields.reduce((acc, f) => acc + (f.area_hectares || 0), 0);
        totalAreaEl.textContent = `${sumArea.toFixed(2)} ha`;
      }
      if (coverageEl) {
        coverageEl.textContent = fields.length > 0 ? "100%" : "0%";
      }

      renderFieldsList(fields);
      renderDashboardRecent(fields);
      updateYieldFieldSelect();

      if (fields.length > 0 && !state.selectedField) {
        selectField(fields[0]);
      }
    } catch (err) {
      console.error("Failed to load fields:", err);
      showToast(window.i18n ? window.i18n.t("toasts.error", { msg: err.message }) : err.message, "error");
    }
  }

  // Render Fields Grid in "Mening dalalarim" View
  function renderFieldsList(fields) {
    const container = document.getElementById("fields-cards-container");
    if (!container) return;

    if (!fields || !fields.length) {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 40px;">
          <h3>${window.i18n ? window.i18n.t("fields.emptyTitle") : "Dalalar yo'q"}</h3>
          <p style="color: var(--color-text-muted); margin-top: 8px;">${window.i18n ? window.i18n.t("fields.emptyDesc") : ""}</p>
        </div>
      `;
      return;
    }

    container.innerHTML = fields
      .map((f) => {
        const isSelected = state.selectedField?.id === f.id ? "selected" : "";
        return `
          <div class="field-card ${isSelected}" data-id="${f.id}">
            <div class="field-card-header">
              <span class="field-name-title">\ud83c\udf3e ${f.crop_name}</span>
              <span class="status-badge good">\ud83d\udfe2 Yaxshi</span>
            </div>
            <div class="field-card-meta">
              <span>Maydon: <strong>${f.area_hectares} ha</strong></span>
              <span>Ekilgan: <strong>${f.planted_on || "\u2014"}</strong></span>
              <span>Bosqich: <strong>${f.growth_stage || "\u2014"}</strong></span>
              <span>ID: <strong>${f.public_id || f.id}</strong></span>
            </div>
            <div class="field-card-actions">
              <button class="btn btn-primary btn-sm btn-select-field" data-id="${f.id}" type="button">
                Tahlil & Xarita
              </button>
            </div>
          </div>
        `;
      })
      .join("");

    container.querySelectorAll(".btn-select-field").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute("data-id"), 10);
        const f = fields.find((x) => x.id === id);
        if (f) {
          selectField(f);
          switchView("satellite");
        }
      });
    });

    container.querySelectorAll(".field-card").forEach((card) => {
      card.addEventListener("click", () => {
        const id = parseInt(card.getAttribute("data-id"), 10);
        const f = fields.find((x) => x.id === id);
        if (f) selectField(f);
      });
    });
  }

  // Render Dashboard Recent List
  function renderDashboardRecent(fields) {
    const container = document.getElementById("dash-recent-list");
    if (!container) return;

    if (!fields || !fields.length) {
      container.innerHTML = `<p style="padding: 20px; color: var(--color-text-muted);">${window.i18n ? window.i18n.t("dashboard.noFieldsYet") : "Hozircha dalalar mavjud emas"}</p>`;
      return;
    }

    container.innerHTML = fields
      .slice(0, 3)
      .map(
        (f) => `
        <div class="card" style="border: 1px solid var(--color-border); padding: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <strong>\ud83c\udf3e ${f.crop_name}</strong>
            <span class="status-badge good">\ud83d\udfe2 Yaxshi</span>
          </div>
          <p style="font-size: 0.85rem; color: var(--color-text-muted);">Maydon: ${f.area_hectares} ha \u00b7 Ekilgan: ${f.planted_on || "\u2014"}</p>
        </div>
      `
      )
      .join("");
  }

  // Synchronize metric checkboxes with Chart datasets
  function syncChartCheckboxes() {
    const map = [
      { id: "chk-metric-ndvi", index: 0 },
      { id: "chk-metric-ndmi", index: 1 },
      { id: "chk-metric-ndre", index: 2 },
      { id: "chk-metric-evi", index: 3 },
      { id: "chk-metric-bsi", index: 4 },
    ];
    map.forEach(({ id, index }) => {
      const chk = document.getElementById(id);
      if (chk && state.charts.monitoring && state.charts.monitoring.data.datasets[index]) {
        state.charts.monitoring.setDatasetVisibility(index, chk.checked);
      }
    });
    if (state.charts.monitoring) {
      state.charts.monitoring.update();
    }
  }

  // Render Monitoring Chart with Continuous Lines & Fixed [-1.0, 1.0] Range
  function renderMonitoringChartData(points) {
    const chartEl = document.getElementById("monitoring-history-chart");
    if (!chartEl || !points) return;

    // Sort points chronologically
    const sorted = [...points].sort((a, b) => {
      const tA = Date.parse(a.acquired_at || a.date || 0);
      const tB = Date.parse(b.acquired_at || b.date || 0);
      return tA - tB;
    });

    const labels = sorted.map((p) => formatChartDate(p.acquired_at || p.date));
    const ndviVals = sorted.map((p) => p.values?.["NDVI"] ?? p.ndvi ?? null);
    const ndmiVals = sorted.map((p) => p.values?.["NDMI"] ?? p.ndmi ?? null);
    const ndreVals = sorted.map((p) => p.values?.["NDRE"] ?? p.ndre ?? null);
    const eviVals = sorted.map((p) => p.values?.["EVI"] ?? p.evi ?? null);
    const bsiVals = sorted.map((p) => p.values?.["BSI"] ?? p.bsi ?? null);

    if (state.charts.monitoring) {
      state.charts.monitoring.destroy();
    }

    state.charts.monitoring = new Chart(chartEl, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "NDVI",
            data: ndviVals,
            borderColor: "#16a34a",
            backgroundColor: "rgba(22, 163, 74, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            spanGaps: true,
            pointRadius: 3.5,
            pointHoverRadius: 6,
            fill: false,
          },
          {
            label: "NDMI",
            data: ndmiVals,
            borderColor: "#2563eb",
            backgroundColor: "rgba(37, 99, 235, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            spanGaps: true,
            pointRadius: 3.5,
            pointHoverRadius: 6,
            fill: false,
          },
          {
            label: "NDRE",
            data: ndreVals,
            borderColor: "#d97706",
            backgroundColor: "rgba(217, 119, 6, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            spanGaps: true,
            pointRadius: 3.5,
            pointHoverRadius: 6,
            fill: false,
          },
          {
            label: "EVI",
            data: eviVals,
            borderColor: "#059669",
            backgroundColor: "rgba(5, 150, 105, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            spanGaps: true,
            pointRadius: 3.5,
            pointHoverRadius: 6,
            fill: false,
          },
          {
            label: "BSI",
            data: bsiVals,
            borderColor: "#dc2626",
            backgroundColor: "rgba(220, 38, 38, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            spanGaps: true,
            pointRadius: 3.5,
            pointHoverRadius: 6,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 12,
            },
          },
          y: {
            min: -1.0,
            max: 1.0,
            ticks: {
              stepSize: 0.2,
            },
            title: {
              display: true,
              text: "Indeks Qiymati (-1.0 dan +1.0 gacha)",
            },
          },
        },
      },
    });

    syncChartCheckboxes();
  }

  // Monitoring Historical Chart.js Renderer
  async function renderMonitoringChart() {
    if (!state.selectedField) return;
    try {
      // Endpoint: /annual-metrics with Date.parse
      const annualData = await api.getAnnualMetrics(state.selectedField.id);
      const points =
        annualData?.points ||
        (Array.isArray(annualData?.series) ? annualData.series : annualData?.series?.points || []);
      renderMonitoringChartData(points);
    } catch (err) {
      console.error("Failed to render monitoring chart:", err);
    }
  }

  // Load Historical Metrics by Date Range
  async function loadHistoricalMetrics() {
    if (!state.selectedField) return;
    const fromInput = document.getElementById("chartFromDate");
    const toInput = document.getElementById("chartToDate");
    const from_date = fromInput?.value || `${new Date().getFullYear()}-01-01`;
    const to_date = toInput?.value || null;

    try {
      showToast("Tarixiy ma'lumotlar yuklanmoqda...", "info");
      // Endpoint: /historical-metrics with from_date
      const res = await api.getHistoricalMetrics(state.selectedField.id, from_date, to_date);
      const points =
        res?.series?.points || (Array.isArray(res?.series) ? res.series : res?.points || []);
      if (points && points.length) {
        showToast(`${points.length} ta kuzatuv yuklandi`, "success");
        renderMonitoringChartData(points);
      } else {
        showToast(window.i18n ? window.i18n.t("monitoring.noData") : "Ma'lumot topilmadi", "info");
      }
    } catch (err) {
      console.error("Failed to load /historical-metrics:", err);
      showToast(err.message, "error");
    }
  }

  function setDateRangePreset(days) {
    const toDate = new Date();
    const fromDate = new Date();
    if (days === "season") {
      fromDate.setMonth(2, 1);
    } else if (days === "year") {
      fromDate.setMonth(0, 1);
    } else {
      fromDate.setDate(toDate.getDate() - days);
    }

    const fromInput = document.getElementById("chartFromDate");
    const toInput = document.getElementById("chartToDate");
    if (fromInput) fromInput.value = fromDate.toISOString().split("T")[0];
    if (toInput) toInput.value = toDate.toISOString().split("T")[0];

    loadHistoricalMetrics();
  }

  // Yield Prediction Handler
  async function handlePredictYield() {
    let field = state.selectedField;
    const yieldFieldSelect = document.getElementById("yield-field-select");
    if (!field && yieldFieldSelect?.value) {
      field = state.fields.find((f) => String(f.id) === yieldFieldSelect.value);
      if (field) selectField(field);
    }

    if (!field) {
      showToast("Avval dalani tanlang!", "error");
      return;
    }

    const btn = document.getElementById("btn-run-yield-predict");
    const origHtml = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.style.opacity = "0.7";
      btn.style.cursor = "not-allowed";
      btn.innerHTML = `<span>\u23f3</span> <span>Hisoblanmoqda...</span>`;
    }

    const modelSelect = document.getElementById("yield-model-select");
    const cropSelect = document.getElementById("yield-crop-select");
    const plantingDateInput = document.getElementById("yield-planting-date");
    const harvestDateInput = document.getElementById("yield-harvest-date");

    const payload = {
      model_name: modelSelect?.value || "CatBoost",
      crop: cropSelect?.value || "cotton",
      planting_date: plantingDateInput?.value || null,
      harvest_date: harvestDateInput?.value || null,
    };

    try {
      showToast("Hosil bashorati hisoblanmoqda...", "info");
      const res = await api.predictYield(field.id, payload);
      renderYieldResults(res);
      showToast(window.i18n ? window.i18n.t("toasts.yieldReady") : "Hosil bashorati tayyor!", "success");
    } catch (err) {
      console.error("Yield prediction failed:", err);
      showToast(err.message, "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = "1";
        btn.style.cursor = "pointer";
        btn.innerHTML = origHtml;
      }
    }
  }

  // Load Latest Yield Results
  async function loadLatestYield(fieldId) {
    try {
      const res = await api.getLatestYield(fieldId);
      if (res) {
        renderYieldResults(res);
      }
    } catch (err) {
      console.error("Failed to load latest yield:", err);
    }
  }

  // Render Yield Results & 4 Data Sources Cards
  function renderYieldResults(data) {
    if (!data) return;

    const valEl = document.getElementById("yield-hero-val");
    const intervalEl = document.getElementById("yield-hero-interval");
    const totalEl = document.getElementById("yield-hero-total");
    const areaEl = document.getElementById("yield-hero-area");
    const avgYieldDash = document.getElementById("dash-avg-yield");

    if (valEl) valEl.textContent = `${data.predicted_yield_t_ha} t/ga`;
    if (intervalEl)
      intervalEl.textContent = `Ishonch oralig'i: ${data.yield_min_expected} \u2014 ${data.yield_max_expected} t/ga`;
    if (totalEl) totalEl.textContent = `${data.total_expected_yield_tons} tonna`;
    if (areaEl) areaEl.textContent = `Maydon: ${data.field_area_ha} ha (${data.crop_display_name})`;
    if (avgYieldDash) avgYieldDash.textContent = `${data.predicted_yield_t_ha} t/ga`;

    // Render Top Features
    const featContainer = document.getElementById("yield-features-container");
    if (featContainer && data.top_features) {
      featContainer.innerHTML = data.top_features
        .map((f) => {
          const pct = Math.round(f.importance * 100);
          return `
          <div class="feature-item">
            <div class="feature-info">
              <span>${f.feature}</span>
              <span>${pct}%</span>
            </div>
            <div class="feature-progress-bg">
              <div class="feature-progress-bar" style="width: ${pct}%;"></div>
            </div>
          </div>
        `;
        })
        .join("");
    }

    // Render Phenology Timeline Chart
    if (data.phenology_timeline && data.phenology_timeline.length) {
      renderPhenologyChart(data.phenology_timeline);
    }

    // Render 4 Data Sources Cards
    const sourcesContainer = document.getElementById("yield-data-sources-container");
    if (sourcesContainer && data.data_sources) {
      sourcesContainer.innerHTML = data.data_sources
        .map(
          (src) => `
        <div class="source-card">
          <div class="source-card-header">
            <span class="source-icon">${src.icon || "\ud83d\udef0\ufe0f"}</span>
            <div>
              <div class="source-title">${src.name}</div>
              <div class="source-count">${src.count}</div>
            </div>
          </div>
          <div class="source-desc">${src.detail}</div>
        </div>
      `
        )
        .join("");
    }
  }

  // Phenology Timeline Dual-Axis Chart
  function renderPhenologyChart(timeline) {
    const canvas = document.getElementById("yield-phenology-chart");
    if (!canvas) return;

    const labels = timeline.map((pt) => `Oy ${pt.month}`);
    const ndviData = timeline.map((pt) => pt.ndvi);
    const rainData = timeline.map((pt) => pt.rain_sum);
    const tempData = timeline.map((pt) => pt.temp_mean);

    if (state.charts.phenology) {
      state.charts.phenology.destroy();
    }

    state.charts.phenology = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "NDVI",
            data: ndviData,
            borderColor: "#16a34a",
            yAxisID: "yVegetation",
            tension: 0.3,
          },
          {
            label: "Harorat (\u00b0C)",
            data: tempData,
            borderColor: "#d97706",
            yAxisID: "yWeather",
            tension: 0.3,
          },
          {
            label: "Yog'in (mm)",
            data: rainData,
            type: "bar",
            backgroundColor: "rgba(37, 99, 235, 0.3)",
            borderColor: "#2563eb",
            yAxisID: "yWeather",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          yVegetation: {
            type: "linear",
            position: "left",
            min: 0,
            max: 1.0,
            title: { display: true, text: "Vegetatsiya" },
          },
          yWeather: {
            type: "linear",
            position: "right",
            grid: { drawOnChartArea: false },
            title: { display: true, text: "Ob-havo" },
          },
        },
      },
    });
  }

  // AI Agronomist Chat
  async function loadChatHistory(fieldId) {
    const feed = document.getElementById("chat-messages-feed");
    if (!feed) return;

    try {
      const messages = await api.getChatHistory(fieldId);
      if (!messages || !messages.length) {
        feed.innerHTML = `<p style="text-align: center; color: var(--color-text-muted); margin-top: 40px;">${window.i18n ? window.i18n.t("chat.noMessages") : "Xabarlar yo'q"}</p>`;
        return;
      }

      feed.innerHTML = messages
        .map((m) => {
          const roleClass = m.role === "user" ? "user" : "ai";
          const safeContent = window.DOMPurify
            ? window.DOMPurify.sanitize(window.marked.parse(m.content))
            : m.content;
          const ragBadge =
            m.role === "assistant" && m.rag_mode
              ? `<span class="rag-badge ${m.rag_mode}">\ud83d\udd2c ${m.rag_mode.toUpperCase()}</span>`
              : "";
          return `
          <div class="chat-bubble ${roleClass}">
            <div class="bubble-content">${safeContent}</div>
            <div class="bubble-meta">
              <span>${formatDateUI(m.created_at)}</span>
              ${ragBadge}
            </div>
          </div>
        `;
        })
        .join("");
      feed.scrollTop = feed.scrollHeight;
    } catch (err) {
      console.error("Failed to load chat history:", err);
    }
  }

  // Load Chat Summary
  async function loadChatSummary(fieldId) {
    const summaryBox = document.getElementById("chat-field-summary-text");
    if (!summaryBox) return;

    try {
      const summary = await api.getChatSummary(fieldId);
      if (summary && summary.summary_text) {
        summaryBox.innerHTML = `
          <p>${summary.summary_text}</p>
          <span style="font-size: 0.75rem; color: var(--color-text-muted); display: block; margin-top: 8px;">
            Yangilangan: ${formatDateUI(summary.updated_at)} (${summary.message_count} xabar)
          </span>
        `;
      } else {
        summaryBox.innerHTML = `<p style="color: var(--color-text-muted);">${window.i18n ? window.i18n.t("chat.noSummary") : "Xulosa mavjud emas"}</p>`;
      }
    } catch (err) {
      console.error("Failed to load chat summary:", err);
    }
  }

  // Send Chat Message
  async function handleSendChatMessage() {
    if (!state.selectedField) {
      showToast("Avval dala tanlang!", "error");
      return;
    }

    const input = document.getElementById("chat-message-input");
    const feed = document.getElementById("chat-messages-feed");
    const sendBtn = document.getElementById("btn-chat-send");
    const text = input?.value?.trim();
    if (!text) return;

    input.value = "";
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.style.opacity = "0.6";
      sendBtn.style.cursor = "not-allowed";
    }
    if (input) {
      input.disabled = true;
    }

    // Append User Bubble Optimistically
    const userBubble = document.createElement("div");
    userBubble.className = "chat-bubble user";
    userBubble.innerHTML = `<div class="bubble-content">${text}</div>`;
    feed.appendChild(userBubble);
    feed.scrollTop = feed.scrollHeight;

    // Append AI Thinking Indicator
    const thinkingBubble = document.createElement("div");
    thinkingBubble.className = "chat-bubble ai";
    thinkingBubble.innerHTML = `<div class="bubble-content"><em>${window.i18n ? window.i18n.t("chat.thinking") : "AI javob tayyorlamoqda..."}</em></div>`;
    feed.appendChild(thinkingBubble);
    feed.scrollTop = feed.scrollHeight;

    try {
      const ragMode = document.getElementById("chat-rag-mode-select")?.value || "advanced";
      const lang = window.i18n ? window.i18n.getLanguage() : "uz-latn";
      const res = await api.sendChatMessage(state.selectedField.id, {
        messages: [{ role: "user", content: text }],
        message: text,
        rag_mode: ragMode,
        language: lang,
      });

      thinkingBubble.remove();

      const aiBubble = document.createElement("div");
      aiBubble.className = "chat-bubble ai";
      const answerText = res.answer || res.reply || "Javob olindi";
      const safeHtml = window.DOMPurify
        ? window.DOMPurify.sanitize(window.marked.parse(answerText))
        : answerText;

      const sourcesList = res.rag_sources || res.sources || [];
      const sourcesCount = sourcesList.length;
      const sourcesBtn =
        sourcesCount > 0
          ? `<button class="btn-sources-drawer" data-sources='${JSON.stringify(sourcesList).replace(/'/g, "&apos;")}' type="button">\ud83d\udcda Manbalar (${sourcesCount})</button>`
          : "";

      const modeBadge = res.rag_strategy || res.rag_mode || ragMode;
      aiBubble.innerHTML = `
        <div class="bubble-content">${safeHtml}</div>
        <div class="bubble-meta">
          <span class="rag-badge ${modeBadge}">\ud83d\udd2c ${modeBadge.toUpperCase()}</span>
          ${sourcesBtn}
        </div>
      `;

      feed.appendChild(aiBubble);
      feed.scrollTop = feed.scrollHeight;

      // Attach Sources Drawer opener
      aiBubble.querySelectorAll(".btn-sources-drawer").forEach((btn) => {
        btn.addEventListener("click", () => {
          const raw = btn.getAttribute("data-sources");
          if (raw) openSourcesDrawer(JSON.parse(raw));
        });
      });

      loadChatSummary(state.selectedField.id);
    } catch (err) {
      thinkingBubble.remove();
      const errorMsg =
        err.status === 409
          ? "AI maslahatchidan foydalanish uchun avval 'Sun'iy yo'ldosh' bo'limida tahlilni bajaring."
          : err.message;
      showToast(errorMsg, "error");
    } finally {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.style.opacity = "1";
        sendBtn.style.cursor = "pointer";
      }
      if (input) {
        input.disabled = false;
        input.focus();
      }
    }
  }

  // Open Sources Drawer
  function openSourcesDrawer(sources) {
    const drawer = document.getElementById("drawer-rag-sources");
    const list = document.getElementById("sources-drawer-list");
    if (!drawer || !list) return;

    if (!sources || !sources.length) {
      list.innerHTML = `<p style="color: var(--color-text-muted);">Manbalar mavjud emas.</p>`;
    } else {
      list.innerHTML = sources
        .map(
          (s) => `
        <div class="source-item-card">
          <div class="source-item-title">\ud83d\udcd6 ${s.document_name || "Qo'llanma"}</div>
          <div class="source-item-score">Sahifa: ${s.page_number || "\u2014"} \u00b7 Score: ${s.score ? s.score.toFixed(2) : "\u2014"}</div>
          <div class="source-item-text">"${s.text}"</div>
        </div>
      `
        )
        .join("");
    }
    drawer.classList.add("open");
  }

  // Knowledge Base RAG Books
  async function loadKnowledgeBaseBooks() {
    const grid = document.getElementById("kb-books-grid");
    const activeCountEl = document.getElementById("kb-active-count");
    const indexedCountEl = document.getElementById("kb-indexed-count");
    if (!grid) return;

    try {
      const books = await api.getRagBooks();
      const activeCount = books.filter((b) => b.is_active).length;
      if (activeCountEl) activeCountEl.textContent = `Faol: ${activeCount}`;
      if (indexedCountEl) indexedCountEl.textContent = `Indekslangan: ${books.length}`;

      if (!books.length) {
        grid.innerHTML = `<p style="color: var(--color-text-muted);">${window.i18n ? window.i18n.t("knowledge.emptyBooks") : "Kitoblar yo'q"}</p>`;
        return;
      }

      grid.innerHTML = books
        .map(
          (b) => `
        <div class="card" style="display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <h3 style="font-size: 1.05rem; font-weight: 750; margin-bottom: 6px;">\ud83d\udcda ${b.name}</h3>
            <p style="font-size: 0.82rem; color: var(--color-text-muted); margin-bottom: 12px;">
              ${b.total_pages || 0} sahifa \u00b7 ${b.chunk_count || 0} bo'lak
            </p>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--color-border); padding-top: 12px;">
            <span style="font-size: 0.82rem; font-weight: 700; color: ${b.is_active ? "var(--color-primary)" : "var(--color-text-muted)"};">
              ${b.is_active ? "\u25cf AI uchun faol" : "\u25cb O'chirilgan"}
            </span>
            <label class="switch">
              <input type="checkbox" class="kb-book-toggle" data-id="${b.id}" ${b.is_active ? "checked" : ""} />
              <span class="slider"></span>
            </label>
          </div>
        </div>
      `
        )
        .join("");

      grid.querySelectorAll(".kb-book-toggle").forEach((toggle) => {
        toggle.addEventListener("change", async () => {
          const bookId = parseInt(toggle.getAttribute("data-id"), 10);
          const isActive = toggle.checked;
          try {
            await api.toggleRagBook(bookId, isActive);
            showToast(window.i18n ? window.i18n.t("toasts.bookToggled") : "Kitob yangilandi", "success");
            loadKnowledgeBaseBooks();
          } catch (err) {
            toggle.checked = !isActive;
            showToast(err.message, "error");
          }
        });
      });
    } catch (err) {
      console.error("Failed to load RAG books:", err);
    }
  }

  // 3-Step Field Creation Wizard
  function initFieldWizard() {
    let step = 1;
    const modal = document.getElementById("modal-field-wizard");
    const mapEl = document.getElementById("wizard-map");

    function updateStepUI() {
      document.getElementById("step-node-1").classList.toggle("active", step >= 1);
      document.getElementById("step-node-2").classList.toggle("active", step >= 2);
      document.getElementById("step-node-3").classList.toggle("active", step >= 3);

      document.getElementById("wizard-step-1-content").style.display = step === 1 ? "block" : "none";
      document.getElementById("wizard-step-2-content").style.display = step === 2 ? "flex" : "none";
      document.getElementById("wizard-step-3-content").style.display = step === 3 ? "flex" : "none";

      document.getElementById("btn-wizard-back").style.display = step > 1 ? "inline-flex" : "none";
      document.getElementById("btn-wizard-next").style.display = step < 3 ? "inline-flex" : "none";
      document.getElementById("btn-wizard-save-field").style.display = step === 3 ? "inline-flex" : "none";

      if (step === 1 && state.maps.wizard) {
        setTimeout(() => state.maps.wizard.invalidateSize(), 100);
      }
    }

    function initWizardMap() {
      if (state.maps.wizard || !mapEl) return;

      const wizardMap = L.map("wizard-map", {
        center: [41.311081, 69.240562],
        zoom: 13,
      });

      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { maxZoom: 19 }
      ).addTo(wizardMap);

      const drawnItems = new L.FeatureGroup();
      wizardMap.addLayer(drawnItems);
      state.maps.drawnItems = drawnItems;

      const drawControl = new L.Control.Draw({
        draw: {
          polygon: {
            allowIntersection: false,
            shapeOptions: { color: "#22c55e", fillColor: "#16a34a", fillOpacity: 0.3 },
          },
          polyline: false,
          rectangle: false,
          circle: false,
          marker: false,
          circlemarker: false,
        },
        edit: { featureGroup: drawnItems },
      });
      wizardMap.addControl(drawControl);

      wizardMap.on(L.Draw.Event.CREATED, (e) => {
        drawnItems.clearLayers();
        drawnItems.addLayer(e.layer);
        state.wizardDraft = e.layer.toGeoJSON().geometry;
        const areaHa = (
          L.GeometryUtil ? L.GeometryUtil.geodesicArea(e.layer.getLatLngs()[0]) / 10000 : 1.5
        ).toFixed(2);
        const areaDisp = document.getElementById("wizard-area-display");
        if (areaDisp) areaDisp.textContent = `Hisoblangan maydon: ~${areaHa} ha (WGS84)`;
      });

      state.maps.wizard = wizardMap;
    }

    document.getElementById("btn-open-field-wizard")?.addEventListener("click", () => {
      step = 1;
      updateStepUI();
      modal.classList.add("open");
      initWizardMap();
    });

    document.getElementById("btn-dash-add-field")?.addEventListener("click", () => {
      step = 1;
      updateStepUI();
      modal.classList.add("open");
      initWizardMap();
    });

    document.getElementById("btn-wizard-close")?.addEventListener("click", () => {
      modal.classList.remove("open");
    });

    document.getElementById("btn-wizard-cancel")?.addEventListener("click", () => {
      modal.classList.remove("open");
    });

    document.getElementById("btn-wizard-clear-draw")?.addEventListener("click", () => {
      if (state.maps.drawnItems) state.maps.drawnItems.clearLayers();
      state.wizardDraft = null;
      const areaDisp = document.getElementById("wizard-area-display");
      if (areaDisp) areaDisp.textContent = "Hisoblangan maydon: 0.00 ha";
    });

    document.getElementById("btn-wizard-next")?.addEventListener("click", () => {
      if (step === 1) {
        if (!state.wizardDraft) {
          showToast(window.i18n ? window.i18n.t("wizard.errorNoPolygon") : "Chegarani chizing", "error");
          return;
        }
        step = 2;
        updateStepUI();
      } else if (step === 2) {
        const crop = document.getElementById("wizard-crop-name")?.value?.trim();
        const planted = document.getElementById("wizard-planted-date")?.value;
        const stage = document.getElementById("wizard-growth-stage")?.value?.trim();

        if (!crop || !planted || !stage) {
          showToast("Barcha maydonlarni to'ldiring!", "error");
          return;
        }

        document.getElementById("wizard-summary-area").textContent = "Hisoblanmoqda...";
        document.getElementById("wizard-summary-crop").textContent = crop;
        document.getElementById("wizard-summary-planted").textContent = planted;
        document.getElementById("wizard-summary-stage").textContent = stage;

        step = 3;
        updateStepUI();
      }
    });

    document.getElementById("btn-wizard-back")?.addEventListener("click", () => {
      if (step > 1) {
        step -= 1;
        updateStepUI();
      }
    });

    document.getElementById("btn-wizard-save-field")?.addEventListener("click", async () => {
      const crop = document.getElementById("wizard-crop-name")?.value?.trim();
      const planted = document.getElementById("wizard-planted-date")?.value;
      const stage = document.getElementById("wizard-growth-stage")?.value?.trim();

      const payload = {
        geometry: state.wizardDraft,
        crop_name: crop,
        planted_on: planted,
        growth_stage: stage,
      };

      try {
        showToast(window.i18n ? window.i18n.t("wizard.saving") : "Saqlanmoqda...", "info");
        const newField = await api.createField(payload);
        showToast(window.i18n ? window.i18n.t("wizard.savedSuccess") : "Dala saqlandi!", "success");
        modal.classList.remove("open");
        await loadFields();
        selectField(newField);
        switchView("satellite");
      } catch (err) {
        if (err.status === 409) {
          showToast(window.i18n ? window.i18n.t("wizard.errorDuplicate") : "Dublikat dala", "error");
        } else {
          showToast(err.message, "error");
        }
      }
    });
  }

  // Database Purge System
  function initPurgeSystem() {
    const modal = document.getElementById("modal-purge-database");
    const openBtn = document.getElementById("btn-open-purge-modal");
    const closeBtn = document.getElementById("btn-close-purge-modal");
    const cancelBtn = document.getElementById("btn-cancel-purge-db");
    const confirmBtn = document.getElementById("btn-confirm-purge-db");
    const input = document.getElementById("purge-confirm-input");

    openBtn?.addEventListener("click", () => {
      if (input) input.value = "";
      modal.classList.add("open");
    });

    closeBtn?.addEventListener("click", () => modal.classList.remove("open"));
    cancelBtn?.addEventListener("click", () => modal.classList.remove("open"));

    confirmBtn?.addEventListener("click", async () => {
      const val = input?.value?.trim().toLowerCase();
      if (val !== "roziman") {
        showToast(window.i18n ? window.i18n.t("settings.purgeError") : "Xato parol", "error");
        return;
      }

      try {
        await api.purgeFields("roziman");
        showToast(window.i18n ? window.i18n.t("settings.purgeSuccess") : "Baza tozalandi", "success");
        modal.classList.remove("open");
        state.selectedField = null;
        state.fields = [];
        await loadFields();
        switchView("dashboard");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }

  // Global Event Listeners & Bootstrapping
  function initEventListeners() {
    // Navigation items
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => {
        const view = item.getAttribute("data-view");
        if (view) switchView(view);
      });
    });

    // Logo click goes to Dashboard
    document.getElementById("brand-logo-link")?.addEventListener("click", (e) => {
      e.preventDefault();
      switchView("dashboard");
    });

    // Topbar Language Selector
    const langSelect = document.getElementById("language-select");
    if (langSelect) {
      langSelect.value = window.i18n.getLanguage();
      langSelect.addEventListener("change", () => {
        window.i18n.setLanguage(langSelect.value);
      });
    }

    // Settings Language Selector sync
    const settingsLang = document.getElementById("settings-lang-select");
    if (settingsLang) {
      settingsLang.value = window.i18n.getLanguage();
      settingsLang.addEventListener("change", () => {
        window.i18n.setLanguage(settingsLang.value);
        if (langSelect) langSelect.value = settingsLang.value;
      });
    }

    // Dashboard CTAs
    document.getElementById("btn-dash-view-all-fields")?.addEventListener("click", () => switchView("fields"));

    // Layer Selector Chips on Map
    document.querySelectorAll(".layer-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        if (chip.disabled || !state.acquisitions.length) return;
        document.querySelectorAll(".layer-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        state.selectedLayer = chip.getAttribute("data-layer");
        const legendName = document.getElementById("legend-layer-name");
        if (legendName) legendName.textContent = state.selectedLayer;
        if (state.selectedAcquisition) {
          loadAcquisitionArtifacts(state.selectedAcquisition);
        }
      });
    });

    // A/B Compare Toggle & Range & Inputs
    const compareToggle = document.getElementById("compare-toggle");
    const swipeBox = document.getElementById("swipe-slider-box");
    const swipeRange = document.getElementById("swipe-range");

    compareToggle?.addEventListener("change", () => {
      state.compare = compareToggle.checked;
      if (swipeBox) swipeBox.style.display = state.compare ? "flex" : "none";
      if (state.compare) {
        updateCompareDateDropdowns();
        updateCompareOverlays();
      } else {
        applySwipe();
        if (state.selectedAcquisition) {
          loadAcquisitionArtifacts(state.selectedAcquisition);
        }
      }
    });

    swipeRange?.addEventListener("input", () => {
      state.swipePercent = parseInt(swipeRange.value, 10);
      applySwipe();
    });

    document.getElementById("compare-layer-a")?.addEventListener("change", () => {
      if (state.compare) updateCompareOverlays();
    });
    document.getElementById("compare-date-a")?.addEventListener("change", () => {
      if (state.compare) updateCompareOverlays();
    });
    document.getElementById("compare-layer-b")?.addEventListener("change", () => {
      if (state.compare) updateCompareOverlays();
    });
    document.getElementById("compare-date-b")?.addEventListener("change", () => {
      if (state.compare) updateCompareOverlays();
    });

    // Run Satellite Analysis (with Loading state & Button disabling)
    document.getElementById("btn-run-analysis")?.addEventListener("click", async () => {
      if (!state.selectedField) {
        showToast("Avval dala tanlang!", "error");
        return;
      }
      const btn = document.getElementById("btn-run-analysis");
      const origHtml = btn ? btn.innerHTML : "";
      if (btn) {
        btn.disabled = true;
        btn.style.opacity = "0.7";
        btn.style.cursor = "not-allowed";
        btn.innerHTML = `<span>\u23f3</span> <span>${window.i18n ? window.i18n.t("satellite.btnAnalyzing") : "Sentinel-2 tahlil qilinmoqda..."}</span>`;
      }
      const mode = document.getElementById("select-analysis-mode")?.value || "latest";
      try {
        showToast(window.i18n ? window.i18n.t("satellite.btnAnalyzing") : "Tahlil boshlandi...", "info");
        await api.analyzeField(state.selectedField.id, mode);
        showToast(window.i18n ? window.i18n.t("toasts.analysisDone") : "Tahlil muvaffaqiyatli yakunlandi!", "success");
        await selectField(state.selectedField);
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.style.opacity = "1";
          btn.style.cursor = "pointer";
          btn.innerHTML = origHtml;
        }
      }
    });

    // Monitoring Date Filter Button & Presets
    document.getElementById("loadHistoryButton")?.addEventListener("click", () => {
      loadHistoricalMetrics();
    });
    document.getElementById("btn-range-30d")?.addEventListener("click", () => setDateRangePreset(30));
    document.getElementById("btn-range-90d")?.addEventListener("click", () => setDateRangePreset(90));
    document.getElementById("btn-range-season")?.addEventListener("click", () => setDateRangePreset("season"));
    document.getElementById("btn-range-year")?.addEventListener("click", () => setDateRangePreset("year"));

    // Metric index visibility checkboxes
    ["chk-metric-ndvi", "chk-metric-ndmi", "chk-metric-ndre", "chk-metric-evi", "chk-metric-bsi"].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", syncChartCheckboxes);
    });

    // Yield Prediction Form Field Selector synchronization
    document.getElementById("yield-field-select")?.addEventListener("change", (e) => {
      const fieldId = parseInt(e.target.value, 10);
      const target = state.fields.find((f) => f.id === fieldId);
      if (target) {
        selectField(target);
      }
    });

    // Yield Prediction Button
    document.getElementById("btn-run-yield-predict")?.addEventListener("click", () => {
      handlePredictYield();
    });

    // Chat Send Button & Enter Key
    document.getElementById("btn-chat-send")?.addEventListener("click", () => {
      handleSendChatMessage();
    });

    document.getElementById("chat-message-input")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleSendChatMessage();
      }
    });

    // Sources Drawer Close Button
    document.getElementById("btn-close-sources-drawer")?.addEventListener("click", () => {
      document.getElementById("drawer-rag-sources")?.classList.remove("open");
    });
  }

  // Authentication & User Session Management
  function initAuth() {
    const modal = document.getElementById("modal-auth");
    const btnOpen = document.getElementById("btn-open-auth");
    const btnClose = document.getElementById("btn-close-auth-modal");
    const tabLogin = document.getElementById("tab-auth-login");
    const tabRegister = document.getElementById("tab-auth-register");
    const title = document.getElementById("auth-modal-title");
    const formLogin = document.getElementById("form-auth-login");
    const formRegister = document.getElementById("form-auth-register");
    const loginError = document.getElementById("login-error-msg");
    const regError = document.getElementById("reg-error-msg");
    const btnLogout = document.getElementById("btn-logout");

    function openModal(mode = "login") {
      if (!modal) return;
      modal.style.display = "flex";
      switchTab(mode);
    }

    function closeModal() {
      if (!modal) return;
      modal.style.display = "none";
      if (loginError) loginError.style.display = "none";
      if (regError) regError.style.display = "none";
    }

    function switchTab(mode) {
      if (mode === "login") {
        tabLogin?.classList.add("active");
        if (tabLogin) tabLogin.style.borderBottomColor = "var(--color-primary)";
        if (tabLogin) tabLogin.style.color = "var(--color-primary)";
        tabRegister?.classList.remove("active");
        if (tabRegister) tabRegister.style.borderBottomColor = "transparent";
        if (tabRegister) tabRegister.style.color = "var(--color-text-muted)";
        if (title) title.textContent = "Tizimga kirish";
        if (formLogin) formLogin.style.display = "block";
        if (formRegister) formRegister.style.display = "none";
      } else {
        tabRegister?.classList.add("active");
        if (tabRegister) tabRegister.style.borderBottomColor = "var(--color-primary)";
        if (tabRegister) tabRegister.style.color = "var(--color-primary)";
        tabLogin?.classList.remove("active");
        if (tabLogin) tabLogin.style.borderBottomColor = "transparent";
        if (tabLogin) tabLogin.style.color = "var(--color-text-muted)";
        if (title) title.textContent = "Ro'yxatdan o'tish";
        if (formLogin) formLogin.style.display = "none";
        if (formRegister) formRegister.style.display = "block";
      }
      if (loginError) loginError.style.display = "none";
      if (regError) regError.style.display = "none";
    }

    btnOpen?.addEventListener("click", () => openModal("login"));
    btnClose?.addEventListener("click", closeModal);
    modal?.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    tabLogin?.addEventListener("click", () => switchTab("login"));
    tabRegister?.addEventListener("click", () => switchTab("register"));

    // Login submit
    formLogin?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const usernameInput = document.getElementById("login-username");
      const passwordInput = document.getElementById("login-password");
      const btnSubmit = document.getElementById("btn-submit-login");

      const username = usernameInput?.value.trim();
      const password = passwordInput?.value;
      if (!username || !password) return;

      if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = "Kirilmoqda...";
      }
      if (loginError) loginError.style.display = "none";

      try {
        const res = await api.login({ username, password });
        localStorage.setItem("zamintahlil_token", res.access_token);
        state.currentUser = res.user;
        showToast(`Xush kelibsiz, ${res.user.full_name || res.user.username}!`, "success");
        closeModal();
        formLogin.reset();
        await updateAuthUI();
        await loadFields();
      } catch (err) {
        if (loginError) {
          loginError.textContent = err.message || "Kirishda xatolik yuz berdi";
          loginError.style.display = "block";
        }
      } finally {
        if (btnSubmit) {
          btnSubmit.disabled = false;
          btnSubmit.textContent = "Kirish";
        }
      }
    });

    // Register submit
    formRegister?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fullNameInput = document.getElementById("reg-fullname");
      const usernameInput = document.getElementById("reg-username");
      const passwordInput = document.getElementById("reg-password");
      const btnSubmit = document.getElementById("btn-submit-reg");

      const full_name = fullNameInput?.value.trim() || null;
      const username = usernameInput?.value.trim();
      const password = passwordInput?.value;
      if (!username || !password) return;

      if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = "Ro'yxatdan o'tilmoqda...";
      }
      if (regError) regError.style.display = "none";

      try {
        const res = await api.register({ username, password, full_name });
        localStorage.setItem("zamintahlil_token", res.access_token);
        state.currentUser = res.user;
        showToast("Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!", "success");
        closeModal();
        formRegister.reset();
        await updateAuthUI();
        await loadFields();
      } catch (err) {
        if (regError) {
          regError.textContent = err.message || "Ro'yxatdan o'tishda xatolik yuz berdi";
          regError.style.display = "block";
        }
      } finally {
        if (btnSubmit) {
          btnSubmit.disabled = false;
          btnSubmit.textContent = "Ro'yxatdan o'tish";
        }
      }
    });

    // Logout click
    btnLogout?.addEventListener("click", async () => {
      localStorage.removeItem("zamintahlil_token");
      state.currentUser = null;
      showToast("Tizimdan chiqdingiz", "info");
      await updateAuthUI();
      await loadFields();
    });

    // Dismiss Cloud Warning Banner
    document.getElementById("btn-dismiss-cloud-warning")?.addEventListener("click", () => {
      const banner = document.getElementById("map-cloud-warning");
      if (banner) banner.style.display = "none";
    });
  }

  // Update Auth Profile UI
  async function updateAuthUI() {
    const authBtn = document.getElementById("btn-open-auth");
    const userPill = document.getElementById("user-profile-pill");
    const userNameEl = document.getElementById("user-display-name");

    const token = localStorage.getItem("zamintahlil_token");
    if (!token) {
      state.currentUser = null;
      if (authBtn) authBtn.style.display = "flex";
      if (userPill) userPill.style.display = "none";
      return;
    }

    try {
      const user = await api.getMe();
      state.currentUser = user;
      if (authBtn) authBtn.style.display = "none";
      if (userPill) {
        userPill.style.display = "flex";
        if (userNameEl) userNameEl.textContent = user.full_name || user.username;
      }
    } catch {
      localStorage.removeItem("zamintahlil_token");
      state.currentUser = null;
      if (authBtn) authBtn.style.display = "flex";
      if (userPill) userPill.style.display = "none";
    }
  }

  // Application Startup
  async function init() {
    window.i18n.applyTranslations();
    initMainMap();
    initEventListeners();
    initFieldWizard();
    initPurgeSystem();
    initAuth();
    updateLayerChipsState(false);
    await updateAuthUI();
    await loadFields();
  }

  window.addEventListener("DOMContentLoaded", init);
})();
