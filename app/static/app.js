/* global L, Chart */
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
  chartFromDate: null
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });

  if (!response.ok) {
    let messageText = `Xato (${response.status})`;
    try {
      const body = await response.json();
      if (Array.isArray(body.detail)) {
        messageText = body.detail
          .map((d) => `${(d.loc || []).join(".")}: ${d.msg}`)
          .join("; ");
      } else if (typeof body.detail === "string") {
        messageText = body.detail;
      }
    } catch {}
    throw new Error(messageText);
  }

  return response.status === 204 ? null : response.json();
}

const formatDate = (value) =>
  value
    ? new Intl.DateTimeFormat("uz-UZ", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
    : "-";

const formatShortDate = (value) =>
  value
    ? new Intl.DateTimeFormat("uz-UZ", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value))
    : "-";

function message(element, text, error = false) {
  element.textContent = text;
  element.classList.toggle("error", error);
}

function setOptionalText(id, text) {
  const element = $(id);
  if (element) element.textContent = text;
}

function setStatus(text, stateName) {
  const element = $("apiStatus");
  element.textContent = text;
  element.dataset.state = stateName;
}

function updateSummary() {
  setOptionalText("fieldCount", String(state.fields.length));
  setOptionalText("selectionState", state.field ? "Dala tanlandi" : "Dala tanlanmagan");
  setOptionalText("draftGuide", state.draft ? "Kontur tayyor, formani to'ldiring" : "Polygon chizishni boshlang");
  setOptionalText("selectedAreaStat", state.field ? `${state.field.area_hectares.toFixed(2)} ga` : "-");
  setOptionalText(
    "latestCaptureStat",
    state.acquisitions.length ? formatShortDate(state.acquisitions[0].acquired_at) : "Tahlil qilinmagan"
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
  $("draftArea").textContent = `${area.toFixed(3)} ga (server qayta hisoblaydi)`;
  updateSummary();
});

const imageMap = L.map("imageMap", { zoomControl: true, attributionControl: true, minZoom: 1 });

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Tasvirlar © Esri"
}).addTo(imageMap);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 20,
  attribution: "Nomlar © Esri"
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
    style: { color: "#1687ff", weight: 4, opacity: 1, fill: false }
  }).addTo(imageMap);
  state.overlays.field.bringToFront();
}

async function loadFields(fit = false) {
  state.fields = await api("/api/fields");
  savedLayer.clearLayers();
  const bounds = [];

  state.fields.forEach((field) => {
    const layer = L.geoJSON(field.geometry, {
      style: { color: "#2b79ad", weight: 2, fillColor: "#4f9bc6", fillOpacity: 0.26 }
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
    return message($("formMessage"), "Avval xaritada polygon chizing.", true);
  }

  message($("formMessage"), "Dala saqlanmoqda...");

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
    $("draftArea").textContent = "Avval xaritada polygon chizing";
    await loadFields();
    message($("formMessage"), `Dala saqlandi: ${field.area_hectares.toFixed(3)} ga`);
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
  message($("analysisMessage"), "Dala ma'lumotlari yuklanmoqda...");

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

    $("fieldTitle").textContent = field.crop_name;
    $("fieldMeta").textContent = `${field.area_hectares.toFixed(3)} ga | Ekilgan: ${field.planted_on} | ${field.growth_stage}`;

    renderAdvice(field.recommendation);
    populateDateSelectors();
    restoreChat();
    await refreshViewer();
    await refreshChart();
    updateSummary();

    message(
      $("analysisMessage"),
      state.acquisitions.length ? `${state.acquisitions.length} ta kuzatuv mavjud.` : "Hali tahlil qilinmagan."
    );
  } catch (error) {
    message($("analysisMessage"), error.message, true);
  }
}

$("analyzeButton").addEventListener("click", async () => {
  if (!state.fieldId) return;

  const button = $("analyzeButton");
  button.disabled = true;
  message($("analysisMessage"), "Sentinel Hub'dan oxirgi 5 ta tasvir tekshirilmoqda...");

  try {
    const result = await api(`/api/fields/${state.fieldId}/analyze`, {
      method: "POST",
      body: JSON.stringify({ mode: $("analysisMode").value })
    });

    renderAdvice(result.recommendation);
    state.acquisitions = await api(`/api/fields/${state.fieldId}/acquisitions`);
    state.acquisitions.sort((a, b) => new Date(b.acquired_at).getTime() - new Date(a.acquired_at).getTime());
    state.artifacts.clear();
    populateDateSelectors(result.selected_acquisition.id);
    await refreshViewer();
    await refreshChart();
    updateSummary();

    const cloud = result.selected_acquisition.cloud_coverage;
    const suffix = result.recommendation_error ? ` ${result.recommendation_error}` : "";
    message(
      $("analysisMessage"),
      `${result.new_acquisitions_processed} ta yangi kuzatuv qayta ishlandi. Tanlangan sana: ${formatDate(
        result.selected_acquisition.acquired_at
      )}, bulut: ${cloud == null ? "mavjud emas" : `${cloud}%`}.${suffix}`,
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
    `${formatDate(item.acquired_at)} | ${item.cloud_coverage == null ? "?" : `${item.cloud_coverage}%`}`
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

  overlay.on("error", () => showViewerState("Tasvirni yuklashda xato yuz berdi"));
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
  showViewerState("Tasvir yuklanmoqda...");
  drawFieldBoundary();

  if (!state.acquisitions.length) {
    showViewerState("Acquisition mavjud emas. Tahlil tugmasini bosing.");
    renderMeta(null);
    updateSummary();
    return;
  }

  try {
    const a = await makeOverlay("A");
    if (!a) {
      const fallback =
        selectedAcquisition("A")?.fully_cloudy && selectedLayer("A") !== "RGB"
          ? "To'liq bulutli: indeks uchun yaroqli piksel yo'q"
          : "Bu qatlam uchun artifact mavjud emas";
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
  if (!info) {
    $("imageMeta").innerHTML = "";
    $("legend").classList.add("hidden");
    return;
  }

  const acquisition = info.acquisition;
  const data = [
    ["Qatlam", info.layer],
    ["Sana", formatDate(acquisition.acquired_at)],
    ["Product ID", acquisition.product_id],
    ["Bulut", acquisition.cloud_coverage == null ? "Mavjud emas" : `${acquisition.cloud_coverage}%`],
    ["Yaroqli piksel", acquisition.valid_pixel_count ?? "Mavjud emas"]
  ];

  $("imageMeta").innerHTML = data
    .map(([key, value]) => `<div class="datum">${key}<strong>${escapeHtml(String(value))}</strong></div>`)
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
    message($("chartMessage"), "Boshlanish sanasini tanlang.", true);
    return;
  }

  const button = $("loadHistoryButton");
  button.disabled = true;
  message($("chartMessage"), `${fromDate} sanasidan hozirgacha ma'lumotlar yuklanmoqda...`);
  try {
    const result = await api(`/api/fields/${state.fieldId}/historical-metrics`, {
      method: "POST",
      body: JSON.stringify({ from_date: fromDate })
    });
    state.chartFromDate = fromDate;
    renderChart(result.series);
    message(
      $("chartMessage"),
      `${result.acquisitions_found} ta kuzatuv topildi, ${result.new_acquisitions_processed} tasi yangi qayta ishlandi.`
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
            callback: (value) => new Date(value).toLocaleDateString("uz-UZ")
          }
        },
        y: {
          min: -1,
          max: 1,
          title: { display: true, text: "Indeks qiymati" }
        }
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            title: (items) => (items.length ? new Date(items[0].raw.x).toLocaleString("uz-UZ") : ""),
            label: (item) =>
              `${item.dataset.label}: ${item.raw.y == null ? "bulut yoki no-data" : item.raw.y.toFixed(3)} | bulut ${
                item.raw.cloud ?? "?"
              }%`
          }
        }
      }
    }
  });
}

function renderAdvice(recommendation) {
  const target = $("recommendation");
  if (!recommendation) {
    target.innerHTML = '<p class="muted">Tahlildan keyin tavsiya shu yerda chiqadi.</p>';
    return;
  }

  const groups = [
    ["red", "Qilinishi shart", "Eng ustuvor ishlar"],
    ["yellow", "Chora ko'rilishi kerak", "Nazorat va ehtiyot chorasi"],
    ["green", "Yaxshi jarayonlar", "Ijobiy holatlar"]
  ];

  const cards = groups
    .filter(([key]) => recommendation.advice?.[key]?.length)
    .map(
      ([key, title, subtitle]) =>
        `<section class="advice-card ${key}"><div><strong>${title}</strong><small>${subtitle}</small></div><ul>${recommendation.advice[
          key
        ]
          .slice(0, 3)
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("")}</ul></section>`
    )
    .join("");

  target.innerHTML = cards || `<p>${escapeHtml(recommendation.content || "Alohida tavsiya aniqlanmadi.")}</p>`;
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
  div.textContent = content;
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
  return value.replace(/[&<>'"]/g, (char) => ({
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

(async () => {
  try {
    setStatus("Server tekshirilmoqda...", "loading");
    await api("/api/health");
    setStatus("Server ishlayapti", "ok");
    await loadFields(true);
  } catch (error) {
    setStatus("Server bilan aloqa yo'q", "error");
    message($("formMessage"), error.message, true);
  } finally {
    updateSummary();
  }
})();
