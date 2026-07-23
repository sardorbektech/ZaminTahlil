/* global L, Chart, i18n, marked, DOMPurify */
const LAYERS = ["RGB", "NDVI", "NDMI", "NDRE", "EVI", "BSI"];
const METRICS = ["NDVI", "NDMI", "NDRE", "EVI", "BSI"];
const COLORS = {
  NDVI: "#268443",
  NDMI: "#337bb5",
  NDRE: "#8a4ea3",
  EVI: "#dc7626",
  BSI: "#89552f"
};

const $ = (id) => document.getElementById(id);
const t = (key, vars) => i18n.t(key, vars);

// Markdown -> xavfsiz HTML render sozlamalari (chat javoblari uchun).
// GFM (jadval, ro'yxat, satr ichi kod) yoqilgan, xom HTML esa kirish satrida
// bloklanadi (sanitize bosqichida yana bir bor tozalanadi).
if (typeof marked !== "undefined") {
  marked.setOptions({
    breaks: true,
    gfm: true
  });
}

function renderMarkdown(text) {
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
    // Kutubxona yuklanmagan bo'lsa, xavfsiz fallback sifatida oddiy matn qaytariladi.
    return escapeHtml(text);
  }
  const rawHtml = marked.parse(String(text ?? ""));
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: [
      "p", "br", "strong", "em", "b", "i", "u", "s", "del",
      "ul", "ol", "li", "blockquote", "code", "pre",
      "h1", "h2", "h3", "h4", "h5", "h6",
      "a", "table", "thead", "tbody", "tr", "th", "td", "hr"
    ],
    ALLOWED_ATTR: ["href", "target", "rel"]
  });
}

const state = {
  fieldId: null,
  field: null,
  fields: [],
  draft: null,
  acquisitions: [],
  artifacts: new Map(),
  overlays: { a: null, b: null, qa: null, field: null },
  compare: false,
  mobileSide: "A",
  chart: null,
  chartFromDate: null,
  // caches kept only so the UI can be re-rendered in the new language
  // without re-hitting the backend when the person switches languages.
  recommendation: null,
  lastMetaInfo: null,
  lastChartSeries: null,
  statusKey: "nav.statusLoading",
  statusState: "loading"
};

/* ---------- Global request loader (shown for every backend call) ---------- */

let pendingRequests = 0;

function beginRequest() {
  pendingRequests += 1;
  $("globalLoader").classList.add("active");
}

function endRequest() {
  pendingRequests = Math.max(0, pendingRequests - 1);
  if (pendingRequests === 0) $("globalLoader").classList.remove("active");
}

async function api(path, options = {}) {
  beginRequest();
  try {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options
    });

    if (!response.ok) {
      let messageText = t("error.generic", { status: response.status });
      try {
        const body = await response.json();
        if (Array.isArray(body.detail)) {
          messageText = body.detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
        } else if (typeof body.detail === "string") {
          messageText = body.detail;
        }
      } catch {}
      throw new Error(messageText);
    }

    return response.status === 204 ? null : response.json();
  } finally {
    endRequest();
  }
}

const formatDate = (value) =>
  value ? new Intl.DateTimeFormat(i18n.getLocale(), { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "-";

const formatShortDate = (value) =>
  value ? new Intl.DateTimeFormat(i18n.getLocale(), { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)) : "-";

function message(element, text, error = false, loading = false) {
  element.textContent = text;
  element.classList.toggle("error", error);
  element.classList.toggle("is-loading", loading && !error);
}

function setOptionalText(id, text) {
  const element = $(id);
  if (element) element.textContent = text;
}

function setStatus(key, stateName) {
  state.statusKey = key;
  state.statusState = stateName;
  const element = $("apiStatus");
  element.textContent = t(key);
  element.dataset.state = stateName;
}

function updateSummary() {
  setOptionalText("fieldCount", String(state.fields.length));
  setOptionalText("selectionState", state.field ? t("story.fieldSelected") : t("story.fieldNotSelected"));
  setOptionalText("draftGuide", state.draft ? t("story.contourReady") : t("story.contourStart"));
  setOptionalText("selectedAreaStat", state.field ? `${state.field.area_hectares.toFixed(2)} ${t("units.ha")}` : t("stats.dash"));
  setOptionalText(
    "latestCaptureStat",
    state.acquisitions.length ? formatShortDate(state.acquisitions[0].acquired_at) : t("stats.notAnalyzed")
  );
}

const map = L.map("map").setView([41.3, 64.5], 6);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Tiles © Esri"
}).addTo(map);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Labels © Esri"
}).addTo(map);

const savedLayer = L.featureGroup().addTo(map);
const draftLayer = L.featureGroup().addTo(map);

map.addControl(
  new L.Control.Draw({
    edit: false,
    draw: {
      polyline: false,
      rectangle: false,
      circle: false,
      circlemarker: false,
      marker: false,
      polygon: { allowIntersection: false, showArea: true }
    }
  })
);

map.on(L.Draw.Event.CREATED, (event) => {
  draftLayer.clearLayers();
  draftLayer.addLayer(event.layer);
  state.draft = event.layer.toGeoJSON().geometry;
  const area = L.GeometryUtil.geodesicArea(event.layer.getLatLngs()[0]) / 10000;
  $("draftArea").textContent = t("composer.areaReady", { area: area.toFixed(3) });
  updateSummary();
});

const imageMap = L.map("imageMap", { zoomControl: true, attributionControl: true, minZoom: 1 });

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Imagery © Esri"
}).addTo(imageMap);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Labels © Esri"
}).addTo(imageMap);

function geoBounds(bbox) {
  return [[bbox[1], bbox[0]], [bbox[3], bbox[2]]];
}

function clearOverlay(name) {
  if (state.overlays[name]) {
    imageMap.removeLayer(state.overlays[name]);
    state.overlays[name] = null;
  }
}

function drawFieldBoundary() {
  clearOverlay("field");
  if (!state.field) return;
  state.overlays.field = L.geoJSON(state.field.geometry, {
    interactive: false,
    style: { color: "#2457b8", weight: 4, opacity: 1, fill: false }
  }).addTo(imageMap);
  state.overlays.field.bringToFront();
}

async function loadFields(fit = false) {
  state.fields = await api("/api/fields");
  savedLayer.clearLayers();
  const bounds = [];

  state.fields.forEach((field) => {
    const layer = L.geoJSON(field.geometry, {
      style: { color: "#2457b8", weight: 2, fillColor: "#5c93e0", fillOpacity: 0.24 }
    }).addTo(savedLayer);

    layer.on("click", (event) => {
      L.DomEvent.stopPropagation(event);
      selectField(field.id);
    });

    bounds.push(...layer.getLayers().map((item) => item.getBounds()));
  });

  if (fit && bounds.length) {
    map.fitBounds(bounds.reduce((all, item) => all.extend(item), bounds[0]));
  }

  updateSummary();
}

$("fieldForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!state.draft) {
    return message($("formMessage"), t("composer.msgNoDraft"), true);
  }

  message($("formMessage"), t("composer.msgSaving"), false, true);

  try {
    const field = await api("/api/fields", {
      method: "POST",
      body: JSON.stringify({
        geometry: state.draft,
        crop_name: $("cropName").value,
        planted_on: $("plantedOn").value,
        growth_stage: $("growthStage").value
      })
    });

    event.target.reset();
    draftLayer.clearLayers();
    state.draft = null;
    $("draftArea").textContent = t("composer.areaPlaceholder");
    await loadFields();
    message($("formMessage"), t("composer.msgSaved", { area: field.area_hectares.toFixed(3) }));
    await selectField(field.id);
  } catch (error) {
    message($("formMessage"), error.message, true);
  } finally {
    updateSummary();
  }
});

async function selectField(fieldId) {
  state.fieldId = fieldId;
  state.chartFromDate = null;
  message($("chartMessage"), "");
  $("emptyState").classList.add("hidden");
  $("detail").classList.remove("hidden");

  requestAnimationFrame(() => imageMap.invalidateSize());
  message($("analysisMessage"), t("detail.msgLoadingField"), false, true);

  try {
    const [field, acquisitions] = await Promise.all([
      api(`/api/fields/${fieldId}`),
      api(`/api/fields/${fieldId}/acquisitions`)
    ]);

    state.field = field;
    state.acquisitions = [...acquisitions].sort(
      (a, b) => new Date(b.acquired_at).getTime() - new Date(a.acquired_at).getTime()
    );
    state.artifacts.clear();
    state.recommendation = field.recommendation || null;

    renderFieldHeader();
    renderAdvice(state.recommendation);
    populateDateSelectors();
    restoreChat();
    await refreshViewer();
    await refreshChart();
    updateSummary();

    message(
      $("analysisMessage"),
      state.acquisitions.length
        ? t("detail.msgHasAcquisitions", { count: state.acquisitions.length })
        : t("detail.msgNoAcquisitions")
    );
  } catch (error) {
    message($("analysisMessage"), error.message, true);
  }
}

function renderFieldHeader() {
  if (!state.field) return;
  $("fieldTitle").textContent = state.field.crop_name;
  $("fieldMeta").textContent = t("detail.metaTemplate", {
    area: state.field.area_hectares.toFixed(3),
    planted: state.field.planted_on,
    stage: state.field.growth_stage
  });
}

$("analyzeButton").addEventListener("click", async () => {
  if (!state.fieldId) return;

  const button = $("analyzeButton");
  button.disabled = true;
  message($("analysisMessage"), t("detail.msgAnalyzing"), false, true);

  try {
    const result = await api(`/api/fields/${state.fieldId}/analyze`, {
      method: "POST",
      body: JSON.stringify({ mode: $("analysisMode").value })
    });

    state.recommendation = result.recommendation || null;
    renderAdvice(state.recommendation);
    state.acquisitions = await api(`/api/fields/${state.fieldId}/acquisitions`);
    state.acquisitions.sort((a, b) => new Date(b.acquired_at).getTime() - new Date(a.acquired_at).getTime());
    state.artifacts.clear();
    populateDateSelectors(result.selected_acquisition.id);
    await refreshViewer();
    await refreshChart();
    updateSummary();

    const cloud = result.selected_acquisition.cloud_coverage;
    const cloudText = cloud == null ? t("detail.cloudNone") : t("detail.cloudPct", { value: cloud });
    const suffix = result.recommendation_error ? ` ${result.recommendation_error}` : "";
    message(
      $("analysisMessage"),
      `${t("detail.msgAnalyzeResult", {
        count: result.new_acquisitions_processed,
        date: formatDate(result.selected_acquisition.acquired_at),
        cloud: cloudText
      })}${suffix}`,
      Boolean(result.recommendation_error)
    );
  } catch (error) {
    message($("analysisMessage"), error.message, true);
  } finally {
    button.disabled = false;
  }
});

function fillSelect(select, values, selected) {
  select.innerHTML = "";
  values.forEach(([value, label]) => {
    select.add(new Option(label, value, false, String(value) === String(selected)));
  });
}

function populateDateSelectors(selectedId = null) {
  const options = state.acquisitions.map((item) => [
    item.id,
    `${formatDate(item.acquired_at)} · ${item.cloud_coverage == null ? "?" : `${item.cloud_coverage}%`}`
  ]);

  const currentA = selectedId || $("dateA").value || options[0]?.[0];
  const currentB = $("dateB").value || options[1]?.[0] || currentA;
  fillSelect($("dateA"), options, currentA);
  fillSelect($("dateB"), options, currentB);
}

fillSelect($("layerA"), LAYERS.map((item) => [item, item]), "RGB");
fillSelect($("layerB"), LAYERS.map((item) => [item, item]), "NDVI");

async function artifactMap(acquisitionId) {
  if (!acquisitionId) return new Map();

  if (!state.artifacts.has(acquisitionId)) {
    const list = await api(`/api/fields/${state.fieldId}/acquisitions/${acquisitionId}/artifacts`);
    state.artifacts.set(acquisitionId, new Map(list.map((item) => [item.layer_name, item])));
  }

  return state.artifacts.get(acquisitionId);
}

function selectedAcquisition(side) {
  const id = Number($(side === "A" ? "dateA" : "dateB").value);
  return state.acquisitions.find((item) => item.id === id);
}

function selectedLayer(side) {
  return $(side === "A" ? "layerA" : "layerB").value;
}

async function makeOverlay(side) {
  const acquisition = selectedAcquisition(side);
  const layer = selectedLayer(side);
  if (!acquisition) return null;

  const artifacts = await artifactMap(acquisition.id);
  const artifact = artifacts.get(layer);
  if (!artifact) return null;

  const overlay = L.imageOverlay(artifact.image_url, geoBounds(artifact.bbox), {
    opacity: Number($("opacity").value) / 100,
    interactive: false,
    crossOrigin: false
  });

  overlay.on("error", () => showViewerState(t("viewer.stateError")));
  overlay.addTo(imageMap);
  return { overlay, artifact, acquisition, layer };
}

function showViewerState(text = "") {
  $("viewerState").textContent = text;
  $("viewerState").classList.toggle("hidden", !text);
}

function applySwipe() {
  if (!state.overlays.b?.getElement) return;
  const value = Number($("swipe").value);
  const element = state.overlays.b.getElement();
  if (element) element.style.clipPath = `inset(0 0 0 ${value}%)`;
}

async function refreshViewer(fit = true) {
  imageMap.invalidateSize();
  clearOverlay("a");
  clearOverlay("b");
  clearOverlay("qa");
  showViewerState(t("viewer.stateLoading"));
  drawFieldBoundary();

  if (!state.acquisitions.length) {
    showViewerState(t("viewer.stateNoAcquisition"));
    renderMeta(null);
    updateSummary();
    return;
  }

  try {
    const a = await makeOverlay("A");
    if (!a) {
      const fallback =
        selectedAcquisition("A")?.fully_cloudy && selectedLayer("A") !== "RGB"
          ? t("viewer.stateFullyCloudy")
          : t("viewer.stateNoArtifact");
      showViewerState(fallback);
      renderMeta(null);
      updateSummary();
      return;
    }

    state.overlays.a = a.overlay;

    if (state.compare) {
      const b = await makeOverlay("B");
      if (b) {
        state.overlays.b = b.overlay;
        applySwipe();
      }
    }

    if ($("qaToggle").checked) await addQa();
    state.overlays.field?.bringToFront();
    if (fit) imageMap.fitBounds(geoBounds(a.artifact.bbox), { padding: [18, 18] });
    showViewerState("");
    renderMeta(a);
  } catch (error) {
    showViewerState(error.message);
  }
}

async function addQa() {
  clearOverlay("qa");
  const acquisition = selectedAcquisition("A");
  if (!acquisition) return;

  const artifact = (await artifactMap(acquisition.id)).get("QA");
  if (artifact) {
    state.overlays.qa = L.imageOverlay(artifact.image_url, geoBounds(artifact.bbox), { opacity: 0.75 }).addTo(imageMap);
  }
}

function renderMeta(info) {
  state.lastMetaInfo = info;
  if (!info) {
    $("imageMeta").innerHTML = "";
    $("legend").classList.add("hidden");
    return;
  }

  const acquisition = info.acquisition;
  const data = [
    [t("imageMeta.layer"), info.layer],
    [t("imageMeta.date"), formatDate(acquisition.acquired_at)],
    [t("imageMeta.productId"), acquisition.product_id],
    [t("imageMeta.cloud"), acquisition.cloud_coverage == null ? t("imageMeta.notAvailable") : `${acquisition.cloud_coverage}%`],
    [t("imageMeta.validPixels"), acquisition.valid_pixel_count ?? t("imageMeta.notAvailable")]
  ];

  $("imageMeta").innerHTML = data
    .map(([key, value]) => `<div class="datum">${escapeHtml(key)}<strong>${escapeHtml(String(value))}</strong></div>`)
    .join("");

  $("legend").classList.toggle("hidden", !METRICS.includes(info.layer));
}

function cycle(selectId, delta) {
  const select = $(selectId);
  if (!select.options.length) return;
  select.selectedIndex = (select.selectedIndex + delta + select.options.length) % select.options.length;
  select.dispatchEvent(new Event("change"));
}

[
  ["prevLayerA", "layerA", -1],
  ["nextLayerA", "layerA", 1],
  ["prevLayerB", "layerB", -1],
  ["nextLayerB", "layerB", 1],
  ["prevDateA", "dateA", -1],
  ["nextDateA", "dateA", 1],
  ["prevDateB", "dateB", -1],
  ["nextDateB", "dateB", 1]
].forEach(([button, select, delta]) => {
  $(button).addEventListener("click", () => cycle(select, delta));
});

["layerA", "layerB", "dateA", "dateB"].forEach((id) => {
  $(id).addEventListener("change", () => refreshViewer(false));
});

$("compareToggle").addEventListener("change", (event) => {
  state.compare = event.target.checked;
  $("bControls").classList.toggle("hidden", !state.compare);
  $("swipe").classList.toggle("hidden", !state.compare);
  $("labelB").classList.toggle("hidden", !state.compare);
  $("mobileCompare").classList.toggle("active", state.compare);
  refreshViewer(false);
});

$("swipe").addEventListener("input", applySwipe);

$("opacity").addEventListener("input", () => {
  ["a", "b"].forEach((name) => state.overlays[name]?.setOpacity(Number($("opacity").value) / 100));
});

$("qaToggle").addEventListener("change", () => {
  if ($("qaToggle").checked) {
    addQa();
  } else {
    clearOverlay("qa");
  }
});

$("mobileCompare").addEventListener("click", (event) => {
  const side = event.target.dataset.side;
  if (!side) return;
  state.mobileSide = side;
  $("swipe").value = side === "A" ? 95 : 5;
  applySwipe();
});

document.addEventListener("keydown", (event) => {
  if (event.target.matches("input, textarea, select")) return;
  if (event.key === "ArrowLeft") cycle("layerA", -1);
  if (event.key === "ArrowRight") cycle("layerA", 1);
});

const metricChecks = $("metricChecks");
METRICS.forEach((name) => {
  const label = document.createElement("label");
  label.innerHTML = `<input type="checkbox" value="${name}" checked><span style="color:${COLORS[name]}">●</span> ${name}`;
  metricChecks.append(label);
});

const currentYear = new Date().getFullYear();
const now = new Date();
const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
  now.getDate()
).padStart(2, "0")}`;
$("chartFromDate").max = today;
$("chartFromDate").value = `${currentYear}-01-01`;
for (let year = currentYear - 4; year <= currentYear; year += 1) {
  $("chartYear").add(new Option(year, year, false, year === currentYear));
}

metricChecks.addEventListener("change", refreshChart);
$("chartYear").addEventListener("change", () => {
  state.chartFromDate = null;
  message($("chartMessage"), "");
  refreshChart();
});

$("loadHistoryButton").addEventListener("click", async () => {
  if (!state.fieldId) return;
  const fromDate = $("chartFromDate").value;
  if (!fromDate) {
    message($("chartMessage"), t("chart.msgChooseDate"), true);
    return;
  }

  const button = $("loadHistoryButton");
  button.disabled = true;
  message($("chartMessage"), t("chart.msgLoading", { date: fromDate }), false, true);
  try {
    const result = await api(`/api/fields/${state.fieldId}/historical-metrics`, {
      method: "POST",
      body: JSON.stringify({ from_date: fromDate })
    });
    state.chartFromDate = fromDate;
    renderChart(result.series);
    message(
      $("chartMessage"),
      t("chart.msgResult", { found: result.acquisitions_found, processed: result.new_acquisitions_processed })
    );
  } catch (error) {
    message($("chartMessage"), error.message, true);
  } finally {
    button.disabled = false;
  }
});

async function refreshChart() {
  if (!state.fieldId) return;

  const query = state.chartFromDate
    ? `/api/fields/${state.fieldId}/historical-metrics?from_date=${encodeURIComponent(state.chartFromDate)}`
    : `/api/fields/${state.fieldId}/annual-metrics?year=${$("chartYear").value || currentYear}`;
  const series = await api(query);
  renderChart(series);
}

function renderChart(series) {
  state.lastChartSeries = series;
  const selected = [...metricChecks.querySelectorAll("input:checked")].map((item) => item.value);
  const datasets = selected.map((name) => ({
    label: name,
    data: series.points.map((point) => ({
      x: Date.parse(point.acquired_at),
      y: point.values[name],
      cloud: point.cloud_coverage,
      fullyCloudy: point.fully_cloudy
    })),
    borderColor: COLORS[name],
    backgroundColor: COLORS[name],
    borderWidth: 1.75,
    pointRadius: 2.5,
    pointHoverRadius: 5,
    // Qiymat yo'q (bulut yoki no-data) nuqtalarda chiziq uzilmasin — keyingi
    // mavjud nuqtaga ulanadi.
    spanGaps: true,
    // Silliq, lekin "monotone" rejimi ortiqcha to'lqin/oshib ketishning oldini oladi.
    cubicInterpolationMode: "monotone",
    tension: 0.3
  }));

  if (state.chart) state.chart.destroy();
  $("chartEmpty").classList.toggle("hidden", series.points.length > 0 && selected.length > 0);

  const locale = i18n.getLocale();
  state.chart = new Chart($("annualChart"), {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      interaction: { mode: "nearest", intersect: false },
      scales: {
        x: {
          type: "linear",
          ticks: {
            callback: (value) => new Date(value).toLocaleDateString(locale)
          }
        },
        y: {
          min: -1,
          max: 1,
          title: { display: true, text: t("chart.axisTitle") }
        }
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            title: (items) => (items.length ? new Date(items[0].raw.x).toLocaleString(locale) : ""),
            label: (item) =>
              `${item.dataset.label}: ${
                item.raw.y == null ? t("chart.tooltipNoData") : item.raw.y.toFixed(3)
              } | ${t("chart.tooltipCloud", { value: item.raw.cloud ?? "?" })}`
          }
        }
      }
    }
  });
}

function renderAdvice(recommendation) {
  state.recommendation = recommendation || null;
  const target = $("recommendation");
  if (!recommendation) {
    target.innerHTML = `<p class="muted">${escapeHtml(t("recommendation.placeholder"))}</p>`;
    return;
  }

  const groups = [
    ["red", t("recommendation.groupRedTitle"), t("recommendation.groupRedSub")],
    ["yellow", t("recommendation.groupYellowTitle"), t("recommendation.groupYellowSub")],
    ["green", t("recommendation.groupGreenTitle"), t("recommendation.groupGreenSub")]
  ];

  const cards = groups
    .filter(([key]) => recommendation.advice?.[key]?.length)
    .map(
      ([key, title, subtitle]) =>
        `<section class="advice-card ${key}"><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(
          subtitle
        )}</small></div><ul>${recommendation.advice[key]
          .slice(0, 3)
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("")}</ul></section>`
    )
    .join("");

  target.innerHTML = cards || `<p>${escapeHtml(recommendation.content || t("recommendation.noAdvice"))}</p>`;
}

function chatKey() {
  return `zamintahlil:chat:${state.fieldId}`;
}

function storedChat() {
  try {
    return JSON.parse(sessionStorage.getItem(chatKey()) || "[]")
      .filter((item) => ["user", "assistant"].includes(item.role) && typeof item.content === "string")
      .slice(-10);
  } catch {
    return [];
  }
}

function persistChat(messages) {
  sessionStorage.setItem(chatKey(), JSON.stringify(messages.slice(-10)));
}

function restoreChat() {
  $("chatLog").innerHTML = "";
  storedChat().forEach((item) => addBubble(item.content, item.role));
}

function addBubble(content, role) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;

  if (role === "assistant") {
    // AI javoblari markdown formatida keladi (**qalin**, ro'yxatlar, sarlavhalar
    // va h.k.) — shuning uchun HTML'ga aylantirib, xavfsizlashtirib chiqariladi.
    div.classList.add("markdown-content");
    div.innerHTML = renderMarkdown(content);
  } else {
    // Foydalanuvchi xabari oddiy matn sifatida, hech qanday HTML ishlanmasdan chiqadi.
    div.textContent = content;
  }

  $("chatLog").append(div);
  $("chatLog").scrollTop = $("chatLog").scrollHeight;
}

$("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.fieldId) return;

  const input = $("chatInput");
  const content = input.value.trim();
  if (!content) return;

  const messages = [...storedChat(), { role: "user", content }].slice(-10);
  persistChat(messages);
  addBubble(content, "user");
  input.value = "";

  try {
    const result = await api(`/api/fields/${state.fieldId}/chat`, {
      method: "POST",
      body: JSON.stringify({ messages })
    });

    addBubble(result.answer, "assistant");
    persistChat([...messages, { role: "assistant", content: result.answer }]);
  } catch (error) {
    addBubble(error.message, "assistant");
    persistChat([...messages, { role: "assistant", content: error.message }]);
  }
});

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;"
  }[char]));
}

window.addEventListener("resize", () => {
  map.invalidateSize();
  imageMap.invalidateSize();
});

/* ---------- Language switching ---------- */

function retranslateDynamic() {
  updateSummary();
  setStatus(state.statusKey, state.statusState);
  renderFieldHeader();
  renderAdvice(state.recommendation);
  if (state.fieldId) populateDateSelectors($("dateA").value || null);
  renderMeta(state.lastMetaInfo);
  if (state.lastChartSeries) renderChart(state.lastChartSeries);
}

$("langSwitch").addEventListener("change", (event) => {
  i18n.setLanguage(event.target.value);
  retranslateDynamic();
});

i18n.applyStatic();
$("langSwitch").value = i18n.current;

(async () => {
  try {
    setStatus("nav.statusLoading", "loading");
    await api("/api/health");
    setStatus("nav.statusOk", "ok");
    await loadFields(true);
  } catch (error) {
    setStatus("nav.statusError", "error");
    message($("formMessage"), error.message, true);
  } finally {
    updateSummary();
  }
})();