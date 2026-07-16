const STAGE_LABELS = {
  mining: "Mining",
  processing: "Processing",
  refining: "Refining",
  pro_ref: "Intermediate",
  pcam: "PCAM",
  cathode: "Cathode",
  battery: "Battery",
};

const METALS = [
  { key: "Li", label: "Lithium" },
  { key: "Co", label: "Cobalt" },
  { key: "Ni", label: "Nickel" },
  { key: "Mn", label: "Manganese" },
];

const SOURCE_PRIORITY = {
  mining: ["usgs", "ma_2026", "scinsight", "benchmark"],
  default: ["ma_2026", "scinsight", "benchmark", "usgs"],
};

const row = (hsCode, factor, product = "") => ({ hsCode, factor, product });
const NICKEL_INTERMEDIATE = [row("750110", 0.75), row("750120", 0.55), row("750400", 0.995), row("750300", 0.5)];
const COBALT_INTERMEDIATE = [row("282200", 0.329), row("810520", 0.6), row("810530", 0.6)];

function presetRows(metal, source, target) {
  if (metal === "Li") {
    if (source === "mining" && ["processing", "pro_ref"].includes(target)) return [row("253090", 0.03)];
    if (["refining", "pro_ref"].includes(source) && target === "cathode") {
      return [row("282520", 0.165, "Lithium Hydroxide"), row("283691", 0.188, "Lithium Carbonate")];
    }
  }
  if (metal === "Ni") {
    if (source === "mining" && ["processing", "pro_ref"].includes(target)) return [row("260400", 0.015)];
    if (source === "processing" && target === "refining") return NICKEL_INTERMEDIATE.map((item) => ({ ...item }));
    if (source === "refining" && ["pcam", "cathode"].includes(target)) return [row("283324", 0.223)];
    if (source === "pro_ref" && ["pcam", "cathode"].includes(target)) return [...NICKEL_INTERMEDIATE.map((item) => ({ ...item })), row("283324", 0.223)];
  }
  if (metal === "Co") {
    if (source === "mining" && ["processing", "pro_ref"].includes(target)) return [row("260500", 0.15)];
    if (source === "processing" && target === "refining") return COBALT_INTERMEDIATE.map((item) => ({ ...item }));
    if (source === "refining" && ["pcam", "cathode"].includes(target)) return [row("283329", 0.03)];
    if (source === "pro_ref" && ["pcam", "cathode"].includes(target)) return [...COBALT_INTERMEDIATE.map((item) => ({ ...item })), row("283329", 0.03)];
  }
  if (metal === "Mn") {
    if (source === "mining" && target === "pro_ref") return [row("260200", 0.3)];
    if (source === "pro_ref" && ["pcam", "cathode"].includes(target)) return [row("283329", 0.02)];
  }
  return [];
}

const sessionId = (() => {
  const existing = sessionStorage.getItem("material_flow_session");
  if (existing) return existing;
  const value = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replaceAll("-", "_");
  sessionStorage.setItem("material_flow_session", value);
  return value;
})();

const state = {
  metal: "Ni",
  year: 2024,
  tradeYears: [],
  sources: [],
  productionSources: {},
  tradeByPair: {},
  generating: false,
  viewMode: "single",
  activeSlot: "a",
  results: { a: null, b: null },
  scenarios: { a: null, b: null },
  countries: [],
  preservedCountryIds: [],
  setupHidden: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const elements = {
  metalOptions: $("#metal-options"),
  yearSelect: $("#year-select"),
  mergeProcessing: $("#merge-processing"),
  showPcam: $("#show-pcam"),
  showBattery: $("#show-battery"),
  useProduction: $("#use-production"),
  chainPreview: $("#chain-preview"),
  stageSourceList: $("#stage-source-list"),
  statusAll: $("#status-all"),
  statusOptions: $("#status-options"),
  tradeStepList: $("#trade-step-list"),
  referenceQuantity: $("#reference-quantity"),
  labelFontSize: $("#label-font-size"),
  countryLabelMode: $("#country-label-mode"),
  flowTransparencyThreshold: $("#flow-transparency-threshold"),
  nodeTransparencyThreshold: $("#node-transparency-threshold"),
  preserveCountryInput: $("#preserve-country-input"),
  countryOptions: $("#country-options"),
  preservedCountryList: $("#preserved-country-list"),
  nodeView: $("#node-view"),
  chemistryOptions: $("#chemistry-options"),
  chemistryScope: $("#chemistry-scope"),
  mergeLmfp: $("#merge-lmfp"),
  generateButton: $("#generate-button"),
  readinessLabel: $("#readiness-label"),
  readinessDetail: $("#readiness-detail"),
  figureGrid: $("#figure-grid"),
  targetSlotControl: $("#target-slot-control"),
  viewModeOptions: $("#view-mode-options"),
  errorBanner: $("#error-banner"),
  errorMessage: $("#error-message"),
  sourceDrawer: $("#source-drawer"),
  sourceBackdrop: $("#source-backdrop"),
  sourceCatalog: $("#source-catalog"),
  toast: $("#toast"),
  dataStatus: $("#data-status"),
  dataStatusDot: $("#data-status-dot"),
  workspace: $("#workspace"),
  setupRail: $("#setup-rail"),
  toggleSetup: $("#toggle-setup"),
  canvasWorkspace: $(".canvas-workspace"),
};

function slotElements(slot) {
  return {
    panel: $(`[data-figure-panel="${slot}"]`),
    title: $(`#figure-title-${slot}`),
    runStatus: $(`#run-status-${slot}`),
    emptyState: $(`#empty-state-${slot}`),
    loadingState: $(`#loading-state-${slot}`),
    figureFrame: $(`#figure-frame-${slot}`),
    resultStrip: $(`#result-strip-${slot}`),
    resultSummaryTitle: $(`#result-summary-title-${slot}`),
    resultSummaryDetail: $(`#result-summary-detail-${slot}`),
    downloadLinks: $(`#download-links-${slot}`),
    openFigure: $(`#open-figure-${slot}`),
  };
}

function renderViewMode() {
  const compare = state.viewMode === "compare";
  elements.figureGrid.classList.toggle("is-compare", compare);
  slotElements("b").panel.hidden = !compare;
  elements.targetSlotControl.hidden = !compare;
  $$('[data-view-mode]').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.viewMode === state.viewMode);
  });
  $$('[data-target-slot]').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.targetSlot === state.activeSlot);
  });
  elements.generateButton.querySelector("span").textContent = compare
    ? `Generate scenario ${state.activeSlot.toUpperCase()}`
    : "Generate Sankey";
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function renderSetupVisibility() {
  elements.workspace.classList.toggle("is-setup-hidden", state.setupHidden);
  elements.setupRail.setAttribute("aria-hidden", String(state.setupHidden));
  elements.toggleSetup.setAttribute("aria-expanded", String(!state.setupHidden));
  elements.toggleSetup.textContent = state.setupHidden ? "Show setup" : "Hide setup";
}

function renderCountryPicker() {
  elements.countryOptions.innerHTML = state.countries.map((country) => {
    const value = country.iso3 || country.name;
    return `<option value="${escapeHtml(value)}">${escapeHtml(country.name)}</option>`;
  }).join("");
  elements.preservedCountryList.innerHTML = state.preservedCountryIds.map((countryId) => {
    const country = state.countries.find((item) => item.id === countryId);
    if (!country) return "";
    const label = country.iso3 ? `${country.iso3} · ${country.name}` : country.name;
    return `<span class="country-chip">${escapeHtml(label)}<button type="button" data-remove-preserved-country="${country.id}" aria-label="Stop keeping ${escapeHtml(country.name)}">×</button></span>`;
  }).join("");
  $$('[data-remove-preserved-country]').forEach((button) => button.addEventListener("click", () => {
    const countryId = Number(button.dataset.removePreservedCountry);
    state.preservedCountryIds = state.preservedCountryIds.filter((value) => value !== countryId);
    renderCountryPicker();
  }));
}

function addPreservedCountry() {
  const query = elements.preserveCountryInput.value.trim().toLowerCase();
  if (!query) return;
  const country = state.countries.find((item) => (
    String(item.id) === query
    || item.name.toLowerCase() === query
    || String(item.iso3 || "").toLowerCase() === query
    || `${item.iso3} · ${item.name}`.toLowerCase() === query
  ));
  if (!country) {
    showToast("Choose a country name or ISO3 code from the list.");
    return;
  }
  if (!state.preservedCountryIds.includes(country.id)) state.preservedCountryIds.push(country.id);
  elements.preserveCountryInput.value = "";
  renderCountryPicker();
}

function captureScenario(payload) {
  return { payload: deepClone(payload), tradeByPair: deepClone(state.tradeByPair) };
}

function restoreScenario(slot) {
  const snapshot = state.scenarios[slot];
  if (!snapshot) return false;
  const payload = snapshot.payload;
  state.metal = payload.metal;
  state.year = Number(payload.year);
  state.productionSources = { ...payload.productionSources };
  state.tradeByPair = deepClone(snapshot.tradeByPair);
  state.preservedCountryIds = [...(payload.preservedCountryIds || [])];
  elements.mergeProcessing.checked = Boolean(payload.mergeProcessingRefining);
  elements.showPcam.checked = Boolean(payload.showPcam);
  elements.showBattery.checked = Boolean(payload.showBattery);
  elements.useProduction.checked = Boolean(payload.useProductionData);
  elements.referenceQuantity.value = payload.referenceQuantity;
  elements.labelFontSize.value = payload.labelFontSize;
  elements.countryLabelMode.value = payload.countryLabelMode || "full";
  elements.flowTransparencyThreshold.value = payload.flowTransparencyThreshold ?? 0;
  elements.nodeTransparencyThreshold.value = payload.nodeTransparencyThreshold ?? 0;
  elements.nodeView.value = payload.nodeView || "country";
  elements.chemistryScope.value = payload.chemistryStageScope || "both";
  elements.mergeLmfp.checked = payload.mergeLmfpIntoLfp !== false;
  const statusValues = payload.productionStatuses;
  elements.statusAll.checked = statusValues === "all";
  elements.statusOptions.querySelectorAll("input").forEach((input) => {
    input.checked = Array.isArray(statusValues) && statusValues.includes(input.value);
  });
  elements.chemistryOptions.hidden = elements.nodeView.value === "country";
  renderAll();
  showToast(`Scenario ${slot.toUpperCase()} setup restored.`);
  return true;
}

function routeDefinition() {
  const stages = ["mining"];
  if (elements.mergeProcessing.checked) stages.push("pro_ref");
  else stages.push("processing", "refining");
  if (elements.showPcam.checked) stages.push("pcam");
  stages.push("cathode");
  if (elements.showBattery.checked) stages.push("battery");
  return {
    stages,
    transitions: stages.slice(0, -1).map((source, index) => ({
      key: `post_trade_${index + 1}`,
      label: `${ordinal(index + 1)} Post Trade`,
      source,
      target: stages[index + 1],
      pair: `${source}>${stages[index + 1]}`,
    })),
  };
}

function ordinal(number) {
  if (number === 1) return "1st";
  if (number === 2) return "2nd";
  if (number === 3) return "3rd";
  return `${number}th`;
}

function sourceByKey(key) {
  return state.sources.find((source) => source.key === key);
}

function coverageFor(source, stage) {
  return source?.coverage?.[state.metal]?.[stage] || null;
}

function sourceCovers(source, stage) {
  const coverage = coverageFor(source, stage);
  return Boolean(source?.available && coverage && coverage.years.includes(Number(state.year)));
}

function sourceOptionReason(source, stage) {
  if (!source.available) return "upload required";
  const coverage = coverageFor(source, stage);
  if (!coverage) return `no ${state.metal} ${STAGE_LABELS[stage]}`;
  if (!coverage.years.includes(Number(state.year))) return `not available for ${state.year}`;
  return `${Math.min(...coverage.years)}–${Math.max(...coverage.years)}`;
}

function renderMetalOptions() {
  elements.metalOptions.innerHTML = METALS.map((metal) => `
    <button type="button" data-metal="${metal.key}" class="${state.metal === metal.key ? "is-active" : ""}">${metal.key}</button>
  `).join("");
  elements.metalOptions.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.metal === button.dataset.metal) return;
      state.metal = button.dataset.metal;
      if (state.metal === "Mn") elements.mergeProcessing.checked = true;
      state.productionSources = {};
      state.tradeByPair = {};
      applyMetalPreset(false);
      renderAll();
      showToast(`${METALS.find((item) => item.key === state.metal).label} preset applied.`);
    });
  });
}

function renderYears() {
  elements.yearSelect.innerHTML = state.tradeYears.map((year) => `<option value="${year}">${year}</option>`).join("");
  if (!state.tradeYears.includes(Number(state.year))) state.year = state.tradeYears.at(-1) || 2024;
  elements.yearSelect.value = state.year;
}

function renderChain() {
  const route = routeDefinition();
  elements.chainPreview.innerHTML = route.stages.map((stage, index) => `
    ${index ? '<i class="chain-arrow"></i>' : ""}<span class="chain-node">${STAGE_LABELS[stage]}</span>
  `).join("");
}

function pickDefaultSource(stage) {
  const priority = SOURCE_PRIORITY[stage] || SOURCE_PRIORITY.default;
  return priority.find((key) => sourceCovers(sourceByKey(key), stage)) || "";
}

function renderStageSources() {
  const { stages } = routeDefinition();
  const activeStageSet = new Set(stages);
  Object.keys(state.productionSources).forEach((stage) => {
    if (!activeStageSet.has(stage)) delete state.productionSources[stage];
  });
  stages.forEach((stage) => {
    if (!sourceCovers(sourceByKey(state.productionSources[stage]), stage)) {
      state.productionSources[stage] = pickDefaultSource(stage);
    }
  });

  elements.stageSourceList.innerHTML = stages.map((stage) => {
    const selected = state.productionSources[stage] || "";
    const options = [
      `<option value="">Choose source</option>`,
      ...state.sources.map((source) => {
        const enabled = sourceCovers(source, stage);
        const reason = sourceOptionReason(source, stage);
        return `<option value="${source.key}" ${selected === source.key ? "selected" : ""} ${enabled ? "" : "disabled"}>${source.label} · ${reason}</option>`;
      }),
    ].join("");
    const missing = !selected;
    return `
      <div class="stage-source-row">
        <label for="source-${stage}">${STAGE_LABELS[stage]}</label>
        <select id="source-${stage}" class="field-input ${missing ? "is-missing" : ""}" data-stage-source="${stage}">${options}</select>
        ${missing ? `<span class="source-note">No available source covers ${state.metal} ${stage} in ${state.year}. Upload a compatible workbook or change the chain/year.</span>` : ""}
      </div>`;
  }).join("");

  elements.stageSourceList.querySelectorAll("select").forEach((select) => {
    select.addEventListener("change", () => {
      state.productionSources[select.dataset.stageSource] = select.value;
      renderStageSources();
      updateReadiness();
    });
  });
}

function renderTradeSteps() {
  const route = routeDefinition();
  route.transitions.forEach((transition) => {
    if (!Object.prototype.hasOwnProperty.call(state.tradeByPair, transition.pair)) {
      state.tradeByPair[transition.pair] = presetRows(
        state.metal,
        transition.source,
        transition.target,
      ).map((item) => ({ ...item }));
    }
  });
  elements.tradeStepList.innerHTML = route.transitions.map((transition) => {
    const rows = state.tradeByPair[transition.pair] || [];
    return `
      <section class="trade-step" data-pair="${transition.pair}">
        <div class="trade-step-head">
          <span><strong>${transition.label}</strong><small>${STAGE_LABELS[transition.source]} → ${STAGE_LABELS[transition.target]}</small></span>
          <button type="button" class="add-trade-row" data-add-row="${transition.pair}">+ Add HS code</button>
        </div>
        <div class="trade-rows">
          ${rows.map((row, index) => tradeRowMarkup(transition.pair, row, index)).join("")}
          ${rows.length ? "" : '<p class="empty-trade">No trade data participates in this step; imports and exports are treated as zero.</p>'}
        </div>
      </section>`;
  }).join("");
  bindTradeEvents();
}

function tradeRowMarkup(pair, row, index) {
  return `
    <div class="trade-row" data-trade-row="${pair}" data-index="${index}">
      <input type="text" inputmode="numeric" value="${escapeHtml(row.hsCode || "")}" placeholder="HS code" aria-label="HS code" data-field="hsCode" />
      <input type="number" min="0" step="any" value="${row.factor ?? ""}" placeholder="Factor" aria-label="Conversion factor" data-field="factor" />
      <button type="button" class="remove-row" aria-label="Remove trade code" data-remove-row>×</button>
      <input class="trade-product" type="text" value="${escapeHtml(row.product || "")}" placeholder="Target product (optional, e.g. Lithium Hydroxide)" aria-label="Target product" data-field="product" />
    </div>`;
}

function bindTradeEvents() {
  $$('[data-add-row]').forEach((button) => button.addEventListener("click", () => {
    const pair = button.dataset.addRow;
    state.tradeByPair[pair] ||= [];
    state.tradeByPair[pair].push({ hsCode: "", factor: "", product: "" });
    renderTradeSteps();
  }));
  $$('[data-trade-row]').forEach((rowElement) => {
    const pair = rowElement.dataset.tradeRow;
    const index = Number(rowElement.dataset.index);
    rowElement.querySelectorAll("input").forEach((input) => input.addEventListener("input", () => {
      state.tradeByPair[pair][index][input.dataset.field] = input.value;
      updateReadiness();
    }));
    rowElement.querySelector("[data-remove-row]").addEventListener("click", () => {
      state.tradeByPair[pair].splice(index, 1);
      renderTradeSteps();
      updateReadiness();
    });
  });
}

function applyMetalPreset(announce = true) {
  const route = routeDefinition();
  route.transitions.forEach((transition) => {
    state.tradeByPair[transition.pair] = presetRows(
      state.metal,
      transition.source,
      transition.target,
    ).map((item) => ({ ...item }));
  });
  renderTradeSteps();
  updateReadiness();
  if (announce) showToast(`${state.metal} conversion preset applied to active steps.`);
}

function renderSourceCatalog() {
  elements.sourceCatalog.innerHTML = state.sources.map((source) => {
    const yearSpan = source.years?.length
      ? `${Math.min(...source.years)}–${Math.max(...source.years)}`
      : "coverage unavailable";
    const coverage = Object.entries(source.coverage || {}).map(([metal, stages]) => `
      <div class="coverage-metal"><span>${metal}</span><div class="stage-chip-list">${Object.keys(stages).map((stage) => `<span class="stage-chip" title="${stages[stage].years.join(", ")}">${STAGE_LABELS[stage] || stage}</span>`).join("")}</div></div>
    `).join("");
    const uploadControl = source.uploadRequired ? `
      <div class="upload-control">
        <label class="upload-label">${source.available ? "Replace workbook" : "Upload .xlsx"}<input type="file" accept=".xlsx" data-upload-source="${source.key}" /></label>
        ${source.available ? `<button type="button" class="remove-upload" data-remove-upload="${source.key}">Remove</button>` : ""}
        <span class="upload-progress" data-upload-progress="${source.key}"></span>
      </div>` : "";
    return `
      <section class="source-entry">
        <div class="source-entry-head">
          <div><strong>${source.label}</strong><small>${source.available ? `${source.fileName} · ${source.sheetCount} sheets · ${yearSpan}` : source.description}</small></div>
          <span class="availability-badge ${source.available ? "" : "needs-upload"}">${source.available ? "Available" : "Upload needed"}</span>
        </div>
        <div class="coverage-list">${coverage || '<span class="field-help">No workbook loaded for this tab.</span>'}</div>
        ${uploadControl}
      </section>`;
  }).join("");
  bindUploadEvents();
}

function bindUploadEvents() {
  $$('[data-upload-source]').forEach((input) => input.addEventListener("change", async () => {
    if (!input.files?.[0]) return;
    const sourceKey = input.dataset.uploadSource;
    const progress = $(`[data-upload-progress="${sourceKey}"]`);
    progress.textContent = "Validating…";
    const form = new FormData();
    form.append("sessionId", sessionId);
    form.append("file", input.files[0]);
    try {
      const response = await fetch(`/api/uploads/${sourceKey}`, { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Upload failed.");
      state.sources = result.sources;
      state.productionSources = {};
      renderAll();
      showToast(`${sourceByKey(sourceKey).label} validated for this tab.`);
    } catch (error) {
      progress.textContent = "";
      showError(error.message);
    }
  }));
  $$('[data-remove-upload]').forEach((button) => button.addEventListener("click", async () => {
    const sourceKey = button.dataset.removeUpload;
    const response = await fetch(`/api/uploads/${sourceKey}?sessionId=${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    const result = await response.json();
    if (!response.ok || !result.ok) return showError(result.error || "Could not remove upload.");
    state.sources = result.sources;
    state.productionSources = {};
    renderAll();
    showToast("Uploaded workbook removed from this tab.");
  }));
}

function selectedStatuses() {
  if (elements.statusAll.checked) return "all";
  const values = elements.statusOptions.querySelectorAll('input:checked');
  return [...values].map((input) => input.value);
}

function updateStatusControls() {
  elements.statusOptions.querySelectorAll("input").forEach((input) => {
    input.disabled = elements.statusAll.checked;
  });
}

function readiness() {
  const route = routeDefinition();
  const missing = route.stages.filter((stage) => !sourceCovers(sourceByKey(state.productionSources[stage]), stage));
  if (missing.length) return {
    ready: false,
    label: `${missing.length} source ${missing.length === 1 ? "gap" : "gaps"}`,
    detail: `Missing ${missing.map((stage) => STAGE_LABELS[stage]).join(", ")} for ${state.metal} ${state.year}.`,
  };
  const invalidRows = route.transitions.flatMap((transition) => state.tradeByPair[transition.pair] || []).filter((row) => {
    if (!String(row.hsCode || "").trim()) return false;
    return !/^\d+$/.test(String(row.hsCode).trim()) || row.factor === "" || Number(row.factor) < 0 || !Number.isFinite(Number(row.factor));
  });
  if (invalidRows.length) return { ready: false, label: "Check trade codes", detail: "HS codes must use digits and every populated row needs a non-negative factor." };
  if (!(Number(elements.referenceQuantity.value) > 0)) return { ready: false, label: "Check reference", detail: "Reference quantity must be greater than zero." };
  const thresholds = [elements.flowTransparencyThreshold.value, elements.nodeTransparencyThreshold.value].map(Number);
  if (thresholds.some((value) => !Number.isFinite(value) || value < 0)) {
    return { ready: false, label: "Check filters", detail: "Flow and node transparency thresholds must be non-negative numbers." };
  }
  return { ready: true, label: "Ready to generate", detail: `${route.stages.length} production stages · ${route.transitions.length} post-trade steps` };
}

function updateReadiness() {
  const status = readiness();
  elements.readinessLabel.textContent = status.label;
  elements.readinessDetail.textContent = status.detail;
  elements.generateButton.disabled = !status.ready || state.generating;
}

function collectPayload() {
  const route = routeDefinition();
  return {
    sessionId,
    metal: state.metal,
    year: Number(state.year),
    mergeProcessingRefining: elements.mergeProcessing.checked,
    showPcam: elements.showPcam.checked,
    showBattery: elements.showBattery.checked,
    useProductionData: elements.useProduction.checked,
    productionSources: { ...state.productionSources },
    productionStatuses: selectedStatuses(),
    tradeRows: route.transitions.flatMap((transition) => (state.tradeByPair[transition.pair] || []).map((row) => ({
      transition: transition.key,
      hsCode: String(row.hsCode || "").trim(),
      factor: row.factor,
      product: String(row.product || "").trim(),
    }))),
    referenceQuantity: Number(elements.referenceQuantity.value),
    labelFontSize: Number(elements.labelFontSize.value),
    countryLabelMode: elements.countryLabelMode.value,
    flowTransparencyThreshold: Number(elements.flowTransparencyThreshold.value),
    nodeTransparencyThreshold: Number(elements.nodeTransparencyThreshold.value),
    preservedCountryIds: [...state.preservedCountryIds],
    nodeView: elements.nodeView.value,
    chemistryStageScope: elements.chemistryScope.value,
    mergeLmfpIntoLfp: elements.mergeLmfp.checked,
    sharedHsTradeOwner: "downstream",
    chemistryFactors: {},
    sortMode: "size",
    imageWidth: 2200,
    imageScale: 1,
  };
}

async function generateFigure(event) {
  event.preventDefault();
  if (!readiness().ready || state.generating) return;
  const slot = state.viewMode === "compare" ? state.activeSlot : "a";
  const target = slotElements(slot);
  const payload = collectPayload();
  const scenarioSnapshot = captureScenario(payload);
  state.generating = true;
  updateReadiness();
  hideError();
  setRunStatus(slot, "is-running", "Generating");
  target.emptyState.hidden = true;
  target.figureFrame.hidden = true;
  target.figureFrame.classList.remove("is-visible");
  target.loadingState.hidden = false;
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Generation failed.");
    state.results[slot] = result;
    state.scenarios[slot] = scenarioSnapshot;
    showResult(result, slot);
  } catch (error) {
    target.loadingState.hidden = true;
    if (state.results[slot]) {
      target.figureFrame.hidden = false;
      requestAnimationFrame(() => target.figureFrame.classList.add("is-visible"));
    } else target.emptyState.hidden = false;
    setRunStatus(slot, "is-error", "Generation failed");
    showError(error.message);
  } finally {
    state.generating = false;
    updateReadiness();
  }
}

function showResult(result, slot) {
  const target = slotElements(slot);
  const artifacts = result.artifacts;
  target.loadingState.hidden = true;
  target.figureFrame.onload = null;
  target.figureFrame.style.height = "620px";
  target.figureFrame.hidden = false;
  target.figureFrame.onload = () => {
    requestAnimationFrame(() => {
      resizeFigureFrame(slot);
      target.figureFrame.classList.add("is-visible");
    });
  };
  target.figureFrame.src = artifacts.html;
  target.openFigure.href = artifacts.html;
  target.openFigure.classList.remove("is-disabled");
  setRunStatus(slot, "is-success", `Generated in ${result.elapsedSeconds}s`);
  target.resultStrip.hidden = false;
  const chain = result.route.stages.map((stage) => stage.label).join(" → ");
  target.title.textContent = `${result.manifest.metal} ${result.manifest.year} · ${chain}`;
  target.resultSummaryTitle.textContent = `${result.manifest.metal} ${result.manifest.year} · ${chain}`;
  const filters = [];
  if (result.manifest.flow_transparency_threshold > 0) filters.push(`flows < ${result.manifest.flow_transparency_threshold.toLocaleString()} t transparent`);
  if (result.manifest.node_transparency_threshold > 0) filters.push(`nodes < ${result.manifest.node_transparency_threshold.toLocaleString()} t transparent`);
  target.resultSummaryDetail.textContent = `${result.manifest.nodes} nodes · ${result.manifest.conversion_rows} trade rows · ${result.manifest.country_label_mode === "iso3" ? "ISO3 labels" : "full country names"}${filters.length ? ` · ${filters.join(" · ")}` : ""}`;
  const names = { image: "PNG", html: "HTML", conversion: "Conversion factors", balance: "Balance audit", stage: "Stage flow", production_sheets: "Production sources", manifest: "Manifest" };
  target.downloadLinks.innerHTML = Object.entries(names).filter(([key]) => artifacts[key]).map(([key, label]) => `<a href="${artifacts[key]}?download=1">${label}</a>`).join("");
}

function resizeFigureFrame(slot) {
  const frame = slotElements(slot).figureFrame;
  try {
    const documentHeight = Math.max(
      frame.contentDocument?.documentElement?.scrollHeight || 0,
      frame.contentDocument?.body?.scrollHeight || 0,
      620,
    );
    frame.style.height = `${documentHeight}px`;
  } catch (_) {
    frame.style.minHeight = "720px";
  }
}

function setRunStatus(slot, className, text) {
  const runStatus = slotElements(slot).runStatus;
  runStatus.className = `run-status ${className}`;
  runStatus.innerHTML = `<i></i>${escapeHtml(text)}`;
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorBanner.hidden = false;
  elements.errorBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideError() { elements.errorBanner.hidden = true; }

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  toastTimer = setTimeout(() => elements.toast.classList.remove("is-visible"), 2800);
}

function openSourceDrawer() {
  elements.sourceBackdrop.hidden = false;
  elements.sourceDrawer.classList.add("is-open");
  elements.sourceDrawer.setAttribute("aria-hidden", "false");
}

function closeSourceDrawer() {
  elements.sourceDrawer.classList.remove("is-open");
  if (elements.sourceDrawer.contains(document.activeElement)) {
    $("#open-source-drawer").focus();
  }
  elements.sourceDrawer.setAttribute("aria-hidden", "true");
  setTimeout(() => { elements.sourceBackdrop.hidden = true; }, 240);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}

function renderAll() {
  renderMetalOptions();
  renderYears();
  renderChain();
  renderStageSources();
  renderTradeSteps();
  renderSourceCatalog();
  renderCountryPicker();
  updateStatusControls();
  renderViewMode();
  updateReadiness();
  const uploadCount = state.sources.filter((source) => source.uploadRequired && source.available).length;
  elements.dataStatus.textContent = `${state.sources.filter((source) => source.available).length} sources available · ${uploadCount} uploaded this tab`;
  elements.dataStatusDot.className = `status-dot ${uploadCount ? "is-ready" : "is-warning"}`;
}

function bindStaticEvents() {
  $$(".section-trigger").forEach((button) => button.addEventListener("click", () => {
    const body = document.getElementById(button.getAttribute("aria-controls"));
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    body.hidden = expanded;
  }));
  [elements.mergeProcessing, elements.showPcam, elements.showBattery].forEach((input) => input.addEventListener("change", () => {
    renderChain();
    renderStageSources();
    renderTradeSteps();
    updateReadiness();
  }));
  elements.yearSelect.addEventListener("change", () => {
    state.year = Number(elements.yearSelect.value);
    state.productionSources = {};
    renderAll();
  });
  elements.statusAll.addEventListener("change", () => { updateStatusControls(); updateReadiness(); });
  elements.statusOptions.addEventListener("change", updateReadiness);
  elements.nodeView.addEventListener("change", () => { elements.chemistryOptions.hidden = elements.nodeView.value === "country"; });
  elements.referenceQuantity.addEventListener("input", updateReadiness);
  elements.labelFontSize.addEventListener("input", updateReadiness);
  elements.flowTransparencyThreshold.addEventListener("input", updateReadiness);
  elements.nodeTransparencyThreshold.addEventListener("input", updateReadiness);
  elements.toggleSetup.addEventListener("click", () => {
    state.setupHidden = !state.setupHidden;
    renderSetupVisibility();
    if (state.setupHidden) elements.canvasWorkspace.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => ["a", "b"].forEach((slot) => {
      if (!slotElements(slot).figureFrame.hidden) resizeFigureFrame(slot);
    }), 260);
  });
  $("#add-preserved-country").addEventListener("click", addPreservedCountry);
  elements.preserveCountryInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addPreservedCountry();
  });
  $$('[data-view-mode]').forEach((button) => button.addEventListener("click", () => {
    state.viewMode = button.dataset.viewMode;
    if (state.viewMode === "single") {
      state.activeSlot = "a";
      restoreScenario("a");
    }
    renderViewMode();
  }));
  $$('[data-target-slot]').forEach((button) => button.addEventListener("click", () => {
    state.activeSlot = button.dataset.targetSlot;
    restoreScenario(state.activeSlot);
    renderViewMode();
  }));
  $("#apply-preset").addEventListener("click", () => applyMetalPreset(true));
  $("#scenario-form").addEventListener("submit", generateFigure);
  $("#open-source-drawer").addEventListener("click", openSourceDrawer);
  $("#close-source-drawer").addEventListener("click", closeSourceDrawer);
  elements.sourceBackdrop.addEventListener("click", closeSourceDrawer);
  $("#dismiss-error").addEventListener("click", hideError);
  window.addEventListener("resize", () => {
    ["a", "b"].forEach((slot) => {
      if (!slotElements(slot).figureFrame.hidden) resizeFigureFrame(slot);
    });
  });
}

async function bootstrap() {
  bindStaticEvents();
  try {
    const response = await fetch(`/api/bootstrap?sessionId=${encodeURIComponent(sessionId)}`);
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Could not load local data inventory.");
    state.tradeYears = result.tradeYears;
    state.sources = result.sources;
    state.countries = result.countries || [];
    state.metal = result.defaults.metal;
    state.year = result.defaults.year;
    elements.referenceQuantity.value = result.defaults.referenceQuantity;
    elements.labelFontSize.value = result.defaults.labelFontSize;
    renderSetupVisibility();
    applyMetalPreset(false);
    renderAll();
  } catch (error) {
    elements.dataStatus.textContent = "Local data unavailable";
    elements.dataStatusDot.className = "status-dot is-warning";
    showError(error.message);
  }
}

bootstrap();
