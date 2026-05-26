import { hydrateStateFromUrl, syncStateToUrl } from "./app_state.js";
import { ApiClient } from "./api_client.js";
import { FigureController } from "./figure_controller.js";
import { debounce, setShellBusy } from "./ui_shell.js";
import { VULNERABILITY_DASHBOARD_DATA } from "./vulnerability_data.js?v=2427";

const state = {
  theme: "light",
  themes: [],
  metal: "Ni",
  metals: [],
  cobaltMode: "mid",
  cobaltModes: [],
  cobaltModeLabels: {},
  year: 2024,
  resultMode: "baseline",
  resultModes: [],
  resultLabels: {},
  tableView: "compare",
  tableViews: [],
  tableViewLabels: {},
  referenceQty: 1000000,
  referenceQtyDefaults: { Ni: 1000000, Li: 50000, Co: 50000 },
  accessMode: "guest",
  accessPassword: "",
  accessUnlocked: false,
  currentTables: null,
  diagnosticFilters: {
    coefficientSearch: "",
    coefficientStage: "all",
    coefficientClass: "all",
    coefficientBound: "all",
    selectedCoefficientKey: "",
    tradeSearch: "",
    tradeStage: "all",
    tradeStatus: "all",
  },
  vulnerabilityCountry: "",
  vulnerabilityMetal: "",
  vulnerabilityMaterial: "",
  vulnerabilityCompareCountries: [],
  vulnerabilityTrendCountry: "",
  vulnerabilityTrendPair: "",
  vulnerabilityTrendCompareCountries: [],
  vulnerabilityCountryVisible: {},
  vulnerabilityStageProfileYear: null,
  vulnerabilityStageProfilePair: "",
  vulnerabilityStageProfileResultMode: "",
  vulnerabilityTrendVisible: {
    baseline: true,
    pareto_optimal: true,
    sn_minimum: true,
    deviation_minimum: true,
  },
  vulnerabilityStageProfile: {
    key: "",
    data: null,
    loading: false,
    error: "",
  },
  vulnerabilityCountryVi: {
    key: "",
    data: null,
    loading: false,
    error: "",
  },
  vulnerabilitySensitivity: {
    resultMode: "",
    selectedMetal: "",
    selectedMaterial: "",
    selectedPair: "",
    draftCountry: "",
    draftStep: "refining",
    draftScenarioProduction: "",
    edits: [],
    options: null,
    optionsKey: "",
    optionsLoading: false,
    optionsError: "",
    reportCountry: "",
    outputCountry: "",
    resultLoading: false,
    resultError: "",
    result: null,
  },
  years: [],
  stageLabels: {},
  stageOrder: [],
  sortModes: [],
  specialNodePositions: [],
  defaultSpecialNodePosition: "first",
  s7Display: {
    country: true,
    chemistry: false,
    aggregateNmcNca: false,
  },
  workspaceView: "sankey",
  selectedOrderStage: "S1",
  layoutState: {},
  lastChartHeight: 0,
  lastStageControls: {},
};

const dragState = {
  stage: null,
  label: null,
};

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const PLOTLY_CONFIG = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};

const apiClient = new ApiClient();
const figureController = new FigureController({
  chartId: "chart",
  frameSelector: ".chart-frame",
  config: PLOTLY_CONFIG,
});

let layoutSyncToken = 0;
let figureRenderToken = 0;
let loadDebounceTimer = 0;
let diagnosticSearchTimer = 0;
let orderLayoutShell = null;
let orderLayoutRail = null;
let selectionMenuOpen = null;
let vulnerabilityTrendPlotFrame = 0;
let vulnerabilityStageProfilePlotFrame = 0;
let vulnerabilitySensitivityStageProfilePlotFrame = 0;

function syncWorkspaceLayout(chartHeightHint = state.lastChartHeight || 0) {
  const chartFrame = document.querySelector(".chart-frame");
  const chartHost = document.getElementById("chart");
  if (!chartFrame || !chartHost) {
    return;
  }

  chartFrame.style.minHeight = "";

  const intrinsicHeight = Math.max(Number(chartHeightHint) || 0, chartHost.offsetHeight || 0, 860);
  const token = ++layoutSyncToken;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (token !== layoutSyncToken) {
        return;
      }
      const refreshedIntrinsicHeight = Math.max(Number(chartHeightHint) || 0, chartHost.offsetHeight || 0, 860);
      chartFrame.style.minHeight = `${Math.ceil(refreshedIntrinsicHeight + 48)}px`;
    });
  });
}


function currentS7ViewMode() {
  if (state.s7Display.country && state.s7Display.chemistry) {
    return "chemistry";
  }
  if (state.s7Display.chemistry) {
    return "chemistry_only";
  }
  return "country";
}

function layoutVariantKey(
  metal = state.metal,
  resultMode = state.resultMode,
  cobaltMode = state.cobaltMode,
  s7ViewMode = currentS7ViewMode(),
  aggregateNmcNca = state.s7Display.aggregateNmcNca,
) {
  const s7Key = `${s7ViewMode}:${aggregateNmcNca ? "merged" : "split"}`;
  return metal === "Co" ? `${metal}:${resultMode}:${cobaltMode}:${s7Key}` : `${metal}:${resultMode}:${s7Key}`;
}

function ensureLayoutState(metal, resultMode, cobaltMode = state.cobaltMode) {
  const variantKey = layoutVariantKey(metal, resultMode, cobaltMode);
  if (!state.layoutState[variantKey]) {
    state.layoutState[variantKey] = {
      sortModes: {},
      orders: {},
      specialPositions: {},
      aggregateCounts: {},
      aggregatePreserve: {},
    };
  }
  return state.layoutState[variantKey];
}

function currentLayoutState() {
  return ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
}

const RESULT_LABEL_OVERRIDES = {
  pareto_optimal: "Multiobjective",
};

function resultModeLabel(value) {
  return RESULT_LABEL_OVERRIDES[value] || state.resultLabels[value] || value;
}

function optimizationModes() {
  return state.resultModes.filter((mode) => mode !== "baseline");
}

function isOptimizationMode(mode = state.resultMode) {
  return optimizationModes().includes(mode);
}

function cobaltModeLabel(value) {
  return state.cobaltModeLabels[value] || value;
}

function setStatus(text, kind = "ok") {
  const pill = document.getElementById("status-pill");
  pill.textContent = text;
  pill.classList.remove("ok", "warn");
  pill.classList.add(kind);
}

const WORKSPACE_VIEW_TARGETS = {
  sankey: "diagram-board",
  analysis: "data-board",
  vulnerability: "vulnerability-board",
};

const ANALYSIS_WORKSPACE_LABELS = {
  analysis: "Optimization",
  vulnerability: "Vulnerability Index",
};

const VULNERABILITY_RESULT_SERIES = [
  { key: "baseline", label: "Original", className: "baseline", color: "#496d9b", symbol: "circle" },
  { key: "pareto_optimal", label: "Multiobjective", className: "pareto", color: "#6fa27b", symbol: "square" },
  { key: "sn_minimum", label: "SN Minimum", className: "sn-minimum", color: "#bd7143", symbol: "diamond" },
  { key: "deviation_minimum", label: "Deviation Minimum", className: "deviation", color: "#7b6ab0", symbol: "triangle-up" },
];

const VULNERABILITY_CASE_GUIDE = [
  {
    key: "proportional",
    label: "Base VI",
    eyebrow: "Default exposure",
    description: "Share of cathode material whose supply-chain path includes the focal country while unknown cathode destinations remain separate.",
  },
  {
    key: "minimum",
    label: "Minimum",
    eyebrow: "Lower bound",
    description: "Optimistic treatment of ambiguous paths that assigns uncertain flows away from the focal country whenever the data allow it.",
  },
  {
    key: "maximumKnown",
    label: "Maximum A",
    eyebrow: "Known-flow upper bound",
    description: "Upper-bound exposure using known trade and production links, before adding the broadest unknown-destination assumption.",
  },
  {
    key: "maximumWithUnknown",
    label: "Maximum B",
    eyebrow: "Unknown-inclusive upper bound",
    description: "Most conservative case that also lets eligible unknown destinations count toward exposure, so values can saturate near 100%.",
  },
];

const VULNERABILITY_TREND_CASES = VULNERABILITY_CASE_GUIDE.map(({ key, label }) => ({ key, label }));

const VULNERABILITY_COUNTRY_LINE_STYLES = [
  { dash: "solid", symbol: "circle" },
  { dash: "dash", symbol: "square" },
  { dash: "dot", symbol: "diamond" },
  { dash: "dashdot", symbol: "triangle-up" },
];

const VULNERABILITY_SENSITIVITY_STEPS = [
  { key: "mining", label: "Mining", weight: 0.28 },
  { key: "processing", label: "Processing", weight: 0.24 },
  { key: "refining", label: "Refining", weight: 0.3 },
  { key: "cathode", label: "Cathode", weight: 0.18 },
];

function workspaceViewFromHash(hash = window.location.hash) {
  if (hash === "#data-board") {
    return "analysis";
  }
  if (hash === "#vulnerability-board") {
    return "vulnerability";
  }
  return "sankey";
}

function setSectionVisible(element, isVisible) {
  if (!element) {
    return;
  }
  element.hidden = !isVisible;
  element.classList.toggle("workspace-view-hidden", !isVisible);
}

function updateWorkspaceNavigationState() {
  document.querySelectorAll("[data-workspace-view]").forEach((link) => {
    const isActive = link.dataset.workspaceView === state.workspaceView;
    link.classList.toggle("active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  const analysisMenu = document.getElementById("analysis-workspace-menu");
  const analysisValue = document.getElementById("analysis-workspace-value");
  const isAnalysisSubView = state.workspaceView === "analysis" || state.workspaceView === "vulnerability";
  document.getElementById("top-nav-details")?.classList.toggle("is-analysis-controls", isAnalysisSubView);
  analysisMenu?.classList.toggle("active", isAnalysisSubView);
  if (analysisValue) {
    analysisValue.textContent = ANALYSIS_WORKSPACE_LABELS[state.workspaceView] || "Choose";
  }
}

function applyWorkspaceView() {
  const isSankey = state.workspaceView === "sankey";
  setSectionVisible(document.getElementById("diagram-board"), isSankey);
  setSectionVisible(document.getElementById("order-board"), isSankey);
  setSectionVisible(document.getElementById("data-board"), state.workspaceView === "analysis");
  setSectionVisible(document.getElementById("vulnerability-board"), state.workspaceView === "vulnerability");
  document.body.dataset.workspaceView = state.workspaceView;
  updateWorkspaceNavigationState();
  if (state.workspaceView === "vulnerability") {
    // The VI workspace can be activated from a previously hidden section. Plotly
    // measures the host element at draw time, so every chart family needs a
    // fresh draw pass after the section becomes visible.
    scheduleVulnerabilityStageProfilePlot();
    scheduleVulnerabilityTrendPlots();
    scheduleVulnerabilitySensitivityStageProfilePlot();
  }
}

function showWorkspaceView(view, options = {}) {
  state.workspaceView = Object.prototype.hasOwnProperty.call(WORKSPACE_VIEW_TARGETS, view) ? view : "sankey";
  applyWorkspaceView();
  closeSelectionMenus();
  const targetId = options.targetId || WORKSPACE_VIEW_TARGETS[state.workspaceView];
  if (options.updateHash) {
    const nextHash = `#${targetId}`;
    if (window.location.hash !== nextHash) {
      window.history.pushState(null, "", `${window.location.pathname}${window.location.search}${nextHash}`);
    }
  }
  if (options.scroll) {
    document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function setControlsCollapsed(isCollapsed) {
  const nav = document.getElementById("top-nav-details");
  const panel = document.getElementById("top-nav-panel");
  const toggle = document.getElementById("top-nav-controls-toggle");
  nav?.classList.toggle("is-controls-collapsed", Boolean(isCollapsed));
  if (panel) {
    panel.hidden = Boolean(isCollapsed);
  }
  toggle?.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
}

function bindControlsToggle() {
  const toggle = document.getElementById("top-nav-controls-toggle");
  if (!toggle) {
    return;
  }
  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    closeSelectionMenus();
    const nav = document.getElementById("top-nav-details");
    setControlsCollapsed(!nav?.classList.contains("is-controls-collapsed"));
  });
}

function bindWorkspaceNavigation() {
  document.querySelectorAll("[data-workspace-view]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      showWorkspaceView(link.dataset.workspaceView, {
        updateHash: true,
        scroll: true,
        targetId: WORKSPACE_VIEW_TARGETS[link.dataset.workspaceView] || "diagram-board",
      });
    });
  });
  document.getElementById("order-studio-jump")?.addEventListener("click", (event) => {
    event.preventDefault();
    showWorkspaceView("sankey", { updateHash: true, scroll: true, targetId: "order-board" });
  });
  window.addEventListener("hashchange", () => {
    const nextView = workspaceViewFromHash(window.location.hash);
    if (nextView !== state.workspaceView) {
      state.workspaceView = nextView;
      applyWorkspaceView();
    }
  });
  window.addEventListener("popstate", () => {
    const nextView = workspaceViewFromHash(window.location.hash);
    if (nextView !== state.workspaceView) {
      state.workspaceView = nextView;
      applyWorkspaceView();
    }
  });
}

function renderPills(container, items, activeValue, onSelect, formatter) {
  container.innerHTML = "";
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill-btn";
    button.textContent = formatter(item);
    button.setAttribute("aria-pressed", item === activeValue ? "true" : "false");
    if (item === activeValue) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => onSelect(item));
    container.appendChild(button);
  });
}

function renderSelectionMenuStates() {
  document.querySelectorAll("[data-selection-menu-trigger]").forEach((trigger) => {
    const menuName = trigger.dataset.selectionMenuTrigger;
    const menu = trigger.closest(".selection-menu");
    const isOpen = selectionMenuOpen === menuName;
    menu?.classList.toggle("is-open", isOpen);
    trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });
}

function closeSelectionMenus() {
  if (!selectionMenuOpen) {
    return;
  }
  selectionMenuOpen = null;
  renderSelectionMenuStates();
}

function setSelectionValue(id, value) {
  const host = document.getElementById(id);
  if (host) {
    host.textContent = value;
  }
}

function updateStateChips(payload = {}) {
  const metal = payload.metal || state.metal;
  const year = payload.year || state.year;
  const resultLabel = resultModeLabel(payload.resultMode || state.resultMode);
  const cobaltLabel = metal === "Co" ? cobaltModeLabel(state.cobaltMode) : "";
  setSelectionValue("metal-selection-value", metal);
  setSelectionValue("year-selection-value", String(year));
  setSelectionValue("result-selection-value", resultLabel);
  setSelectionValue("cobalt-selection-value", cobaltLabel);
  renderSelectionMenuStates();
}

function syncS7DisplayFromPayload(payload = {}) {
  const viewMode = payload.s7ViewMode || payload.viewMode || currentS7ViewMode();
  state.s7Display.country = viewMode === "country" || viewMode === "chemistry";
  state.s7Display.chemistry = viewMode === "chemistry" || viewMode === "chemistry_only";
  if (!state.s7Display.country && !state.s7Display.chemistry) {
    state.s7Display.country = true;
  }
  state.s7Display.aggregateNmcNca = Boolean(payload.s7AggregateNmcNca);
}

function renderS7DisplayControls() {
  const countryButton = document.getElementById("s7-country-btn");
  const chemistryButton = document.getElementById("s7-chemistry-btn");
  const aggregateButton = document.getElementById("s7-aggregate-btn");
  if (!countryButton || !chemistryButton || !aggregateButton) {
    return;
  }
  [
    [countryButton, state.s7Display.country],
    [chemistryButton, state.s7Display.chemistry],
    [aggregateButton, state.s7Display.aggregateNmcNca],
  ].forEach(([button, isActive]) => {
    button.classList.toggle("active", Boolean(isActive));
    button.setAttribute("aria-pressed", Boolean(isActive) ? "true" : "false");
  });
  aggregateButton.disabled = !state.s7Display.chemistry;
  aggregateButton.classList.toggle("disabled", !state.s7Display.chemistry);
}

async function updateS7Display(nextDisplay) {
  state.s7Display = {
    ...state.s7Display,
    ...nextDisplay,
  };
  if (!state.s7Display.country && !state.s7Display.chemistry) {
    state.s7Display.country = true;
  }
  if (!state.s7Display.chemistry) {
    state.s7Display.aggregateNmcNca = false;
  }
  renderS7DisplayControls();
  ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
  await loadFigure();
}

function applyTheme(theme) {
  state.theme = theme;
  document.body.dataset.theme = theme;
}

function renderThemeButtons() {
  const container = document.getElementById("theme-buttons");
  container.innerHTML = "";
  state.themes.forEach((theme) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill-btn";
    button.textContent = theme === "light" ? "Light" : "Dark";
    button.setAttribute("aria-pressed", theme === state.theme ? "true" : "false");
    if (theme === state.theme) {
      button.classList.add("active");
    }
    button.addEventListener("click", async () => {
      applyTheme(theme);
      renderThemeButtons();
      await loadFigure();
    });
    container.appendChild(button);
  });
}

function renderMetalButtons() {
  const container = document.getElementById("metal-buttons");
  container.innerHTML = "";
  setSelectionValue("metal-selection-value", state.metal);
  state.metals.forEach((metal) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill-btn";
    button.textContent = metal.label;
    button.disabled = !metal.available;
    button.setAttribute("aria-pressed", metal.id === state.metal ? "true" : "false");
    if (!metal.available) {
      button.title = "Dataset is not connected in this runtime snapshot.";
    }
    if (metal.id === state.metal) {
      button.classList.add("active");
    }
    button.addEventListener("click", async () => {
      if (!metal.available) return;
      state.metal = metal.id;
      state.referenceQty = state.referenceQtyDefaults[metal.id] || state.referenceQty;
      ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
      document.getElementById("reference-qty-input").value = Math.round(state.referenceQty);
      closeSelectionMenus();
      renderMetalButtons();
      renderCobaltModeButtons();
      await loadFigure();
    });
    container.appendChild(button);
  });
  renderSelectionMenuStates();
}

function renderCobaltModeButtons() {
  const block = document.getElementById("cobalt-mode-block");
  const container = document.getElementById("cobalt-mode-buttons");
  const note = document.getElementById("cobalt-mode-note");
  const isVisible = state.metal === "Co";
  block.classList.toggle("is-hidden", !isVisible);
  setSelectionValue("cobalt-selection-value", isVisible ? cobaltModeLabel(state.cobaltMode) : "");
  if (!isVisible) {
    container.innerHTML = "";
    if (selectionMenuOpen === "cobalt") {
      closeSelectionMenus();
    }
    return;
  }
  renderPills(
    container,
    state.cobaltModes,
    state.cobaltMode,
    async (mode) => {
      state.cobaltMode = mode;
      ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
      closeSelectionMenus();
      renderCobaltModeButtons();
      await loadFigure();
    },
    cobaltModeLabel,
  );
  if (note) {
    note.textContent = "Cobalt reads three frozen scenario exports. Middle, Max, and Min are all served from precomputed files rather than rebuilt on the fly.";
  }
  renderSelectionMenuStates();
}

function renderAccessControls() {
  const modeContainer = document.getElementById("access-mode-buttons");
  const passwordWrap = document.getElementById("access-password-wrap");
  const note = document.getElementById("access-note");
  renderPills(
    modeContainer,
    ["guest", "analyst"],
    state.accessMode,
    async (mode) => {
      state.accessMode = mode;
      if (mode === "guest") {
        state.accessPassword = "";
        state.accessUnlocked = false;
        document.getElementById("access-password-input").value = "";
        renderAccessControls();
        await loadFigure();
        return;
      }
      renderAccessControls();
    },
    (value) => (value === "guest" ? "Guest Login" : "Non-Guest Login"),
  );
  const needsPassword = state.accessMode === "analyst" && !state.accessUnlocked;
  passwordWrap.classList.toggle("is-hidden", !needsPassword);
  note.textContent =
    state.accessMode === "guest"
      ? "Guest mode hides stage totals, country production values, and Analysis."
      : state.accessUnlocked
        ? "Non-guest mode is unlocked. Full analysis and production values are visible."
        : "Enter the password to unlock non-guest mode.";
}

async function unlockAnalystMode() {
  const input = document.getElementById("access-password-input");
  state.accessPassword = input.value || "";
  try {
    await loadFigure({ immediate: true, force: true });
    state.accessUnlocked = true;
    renderAccessControls();
    renderVulnerabilitySensitivityPanel();
  } catch (error) {
    state.accessUnlocked = false;
    renderAccessControls();
    throw error;
  }
}

function renderSummary(summary) {
  const grid = document.getElementById("summary-grid");
  grid.innerHTML = "";
  grid.classList.toggle("is-hidden", !summary || !summary.length);
  if (!summary || !summary.length) {
    return;
  }
  summary.forEach((item) => {
    const entry = document.createElement("article");
    entry.className = "summary-item";
    entry.innerHTML = `
      <span>${item.label}</span>
      <strong>${numberFormatter.format(item.total)} t</strong>
      <span>${item.nodeCount} display nodes</span>
    `;
    grid.appendChild(entry);
  });
}

function renderNotes(notes) {
  const host = document.getElementById("notes-list");
  if (!host) {
    return;
  }
  host.innerHTML = "";
  notes.forEach((note) => {
    const item = document.createElement("div");
    item.className = "note-item";
    item.textContent = note;
    host.appendChild(item);
  });
}

function renderDatasetStatus(datasetStatus) {
  const host = document.getElementById("dataset-status");
  if (!host) {
    return;
  }
  host.innerHTML = "";
  Object.entries(datasetStatus).forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "dataset-item";
    const detail = value.label || value.path || "";
    item.innerHTML = `
      <strong>${escapeHtml(key)}</strong>
      <span class="${value.exists ? "ok" : "warn"}">${value.exists ? "Available" : "Missing"}</span>
      <div>${escapeHtml(String(detail))}</div>
    `;
    host.appendChild(item);
  });
}

function showUiError(message, statusText = "Error") {
  setStatus(statusText, "warn");
  const host = document.getElementById("notes-list");
  if (host) {
    host.innerHTML = `<div class="note-item">${escapeHtml(message)}</div>`;
  }
}

function syncManualOrder(stage, items) {
  const layout = currentLayoutState();
  const labels = items.map((item) => item.label);
  if (!layout.orders[stage]) {
    layout.orders[stage] = [...labels];
    return;
  }
  const kept = layout.orders[stage].filter((label) => labels.includes(label));
  labels.forEach((label) => {
    if (!kept.includes(label)) {
      kept.push(label);
    }
  });
  layout.orders[stage] = kept;
}

function clampAggregateCount(rawValue, maxCount) {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.min(Math.max(Math.round(parsed), 0), Math.max(maxCount, 0));
}

function getAggregateCount(stage, config) {
  const layout = currentLayoutState();
  const mode = layout.sortModes[stage] || config.sortMode || "size";
  if (mode === "continent") {
    layout.aggregateCounts[stage] = 0;
    return 0;
  }
  const stored = layout.aggregateCounts[stage];
  const fallback = Number.isFinite(config.aggregateCount) ? config.aggregateCount : 0;
  const resolved = clampAggregateCount(
    Number.isFinite(stored) ? stored : fallback,
    config.maxAggregateCount || 0,
  );
  layout.aggregateCounts[stage] = resolved;
  return resolved;
}

function itemIdentity(item) {
  return String(item?.key || item?.label || "");
}

function getAggregatePreserveList(stage) {
  const layout = currentLayoutState();
  const values = Array.isArray(layout.aggregatePreserve?.[stage])
    ? layout.aggregatePreserve[stage]
    : [];
  const resolved = Array.from(new Set(values.map((value) => String(value)).filter(Boolean)));
  layout.aggregatePreserve[stage] = resolved;
  return resolved;
}

function syncAggregatePreserve(stage, items) {
  const validKeys = new Set(items.map((item) => itemIdentity(item)).filter(Boolean));
  const filtered = getAggregatePreserveList(stage).filter((key) => validKeys.has(key));
  currentLayoutState().aggregatePreserve[stage] = filtered;
  return filtered;
}

function setAggregatePreserveList(stage, keys) {
  currentLayoutState().aggregatePreserve[stage] = Array.from(new Set(keys.map((key) => String(key)).filter(Boolean)));
}

function aggregateTailKeySet(items, aggregateCount, preserveSet = new Set()) {
  if (!aggregateCount || aggregateCount <= 0) {
    return new Set();
  }
  const tailKeys = [];
  for (let index = items.length - 1; index >= 0 && tailKeys.length < aggregateCount; index -= 1) {
    const key = itemIdentity(items[index]);
    if (!key || preserveSet.has(key)) {
      continue;
    }
    tailKeys.push(key);
  }
  return new Set(tailKeys);
}

function getSpecialPosition(stage, config) {
  const layout = currentLayoutState();
  const fallback = config.specialPosition || state.defaultSpecialNodePosition || "first";
  const resolved = layout.specialPositions[stage] || fallback;
  layout.specialPositions[stage] = resolved;
  return resolved;
}

function getRenderedItems(stage, config) {
  const layout = currentLayoutState();
  const mode = layout.sortModes[stage] || config.sortMode || "size";
  layout.sortModes[stage] = mode;
  syncManualOrder(stage, config.items);
  if (mode === "manual") {
    const byLabel = Object.fromEntries(config.items.map((item) => [item.label, item]));
    return layout.orders[stage].map((label) => byLabel[label]).filter(Boolean);
  }
  return config.items;
}

async function renderChartFigure(figure) {
  await figureController.render(figure);
}

function buildFigureRequest() {
  const layout = currentLayoutState();
  return {
    metal: state.metal,
    cobaltMode: state.cobaltMode,
    theme: state.theme,
    year: state.year,
    resultMode: state.resultMode,
    tableView: state.tableView,
    referenceQuantity: state.referenceQty,
    accessMode: state.accessMode,
    accessPassword: state.accessPassword,
    sortModes: layout.sortModes,
    stageOrders: layout.orders,
    specialPositions: layout.specialPositions,
    aggregateCounts: layout.aggregateCounts,
    aggregatePreserve: layout.aggregatePreserve,
    s7ViewMode: currentS7ViewMode(),
    s7AggregateNmcNca: state.s7Display.aggregateNmcNca,
  };
}

async function runFigureLoad(options = {}) {
  const renderToken = ++figureRenderToken;
  setStatus("Updating", "warn");
  setShellBusy(true, "Updating Sankey diagram");
  figureController.setLoading("Updating Sankey diagram");
  let payload;
  try {
    payload = await apiClient.requestFigure(buildFigureRequest(), {
      cacheable: state.accessMode === "guest",
      force: Boolean(options.force),
    });
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }
    if (renderToken === figureRenderToken) {
      figureController.setError("Chart update failed");
      showUiError(error.message || "Chart update failed.");
      setShellBusy(false, "Chart update failed");
    }
    throw error;
  }
  if (renderToken !== figureRenderToken) {
    return;
  }
  try {
    state.metal = payload.metal;
    state.cobaltMode = payload.cobaltMode || state.cobaltMode;
    state.resultMode = payload.resultMode;
    state.accessMode = payload.accessMode || state.accessMode;
    syncS7DisplayFromPayload(payload);
    renderThemeButtons();
    renderMetalButtons();
    renderCobaltModeButtons();
    renderAccessControls();
    renderResultButtons();
    renderS7DisplayControls();
    const layoutState = currentLayoutState();
    layoutState.sortModes = {
      ...layoutState.sortModes,
      ...(payload.sortModes || {}),
    };
    layoutState.specialPositions = {
      ...layoutState.specialPositions,
      ...(payload.specialPositions || {}),
    };
    layoutState.aggregateCounts = {
      ...layoutState.aggregateCounts,
      ...(payload.aggregateCounts || {}),
    };
    layoutState.aggregatePreserve = {
      ...layoutState.aggregatePreserve,
      ...(payload.aggregatePreserve || {}),
    };
    state.referenceQty = payload.referenceQuantity;
    state.lastStageControls = payload.stageControls || {};
    document.getElementById("reference-qty-input").value = Math.round(payload.referenceQuantity);
    const payloadResultLabel = resultModeLabel(payload.resultMode || state.resultMode);
    const optimizationLabel = isOptimizationMode(payload.resultMode)
      ? `with ${payloadResultLabel} flow optimization`
      : "without flow optimization";
    const cobaltSuffix = payload.metal === "Co" ? ` (${cobaltModeLabel(state.cobaltMode)} scenario)` : "";
    document.getElementById("chart-title").textContent =
      `The Sankey Diagram for ${payload.metal} in ${payload.year} ${optimizationLabel}${cobaltSuffix}`;
    updateStateChips(payload);
    renderSummary(payload.stageSummary);
    renderNotes(payload.notes);
    renderDatasetStatus(payload.datasetStatus);
    renderOrderBoard(payload.stageControls);
    renderTables(payload.tables);
    renderVulnerabilityDashboard();
    document.getElementById("table-status").textContent =
      state.accessMode === "guest"
          ? "Guest view: analysis preview is locked. Unlock Analyst mode for values and drilldowns."
        : state.resultMode === "baseline"
          ? "Analysis: Original only. Choose Optimization for optimizer-stage summaries."
          : `Analysis: ${payloadResultLabel} stage summaries, source scaling, and optimization explorers.`;
    applyWorkspaceView();
    state.lastChartHeight = Number(payload.figure?.layout?.height || 0);
    await renderChartFigure(payload.figure);
    if (renderToken !== figureRenderToken) {
      return;
    }
    syncWorkspaceLayout(state.lastChartHeight);
    syncStateToUrl(state);
    setStatus("Ready", "ok");
  } catch (error) {
    if (renderToken === figureRenderToken) {
      figureController.setError("Chart render failed");
      showUiError(error.message || "Chart render failed.");
      setStatus("Error", "warn");
    }
    throw error;
  } finally {
    if (renderToken === figureRenderToken) {
      setShellBusy(false, "Sankey diagram ready");
    }
  }
}

async function loadFigure(options = {}) {
  if (options.immediate) {
    window.clearTimeout(loadDebounceTimer);
    return runFigureLoad(options);
  }
  window.clearTimeout(loadDebounceTimer);
  return new Promise((resolve, reject) => {
    loadDebounceTimer = window.setTimeout(() => {
      runFigureLoad(options).then(resolve).catch(reject);
    }, options.delayMs ?? 180);
  });
}

function parseReferenceQuantity() {
  const input = document.getElementById("reference-qty-input");
  const nextValue = Number(input.value);
  if (!Number.isFinite(nextValue) || nextValue <= 0) {
    input.value = Math.round(state.referenceQty);
    return false;
  }
  state.referenceQty = nextValue;
  return true;
}

function moveLabel(order, draggedLabel, targetLabel) {
  if (draggedLabel === targetLabel) {
    return [...order];
  }
  const next = order.filter((label) => label !== draggedLabel);
  const targetIndex = next.indexOf(targetLabel);
  if (targetIndex === -1) {
    next.push(draggedLabel);
    return next;
  }
  next.splice(targetIndex, 0, draggedLabel);
  return next;
}

function addManualDragHandlers(entry, stage, label, layout, grid) {
  entry.addEventListener("dragstart", () => {
    dragState.stage = stage;
    dragState.label = label;
    entry.classList.add("dragging");
  });
  entry.addEventListener("dragend", () => {
    dragState.stage = null;
    dragState.label = null;
    entry.classList.remove("dragging");
    grid.querySelectorAll(".drop-target").forEach((node) => node.classList.remove("drop-target"));
  });
  entry.addEventListener("dragover", (event) => {
    event.preventDefault();
    entry.classList.add("drop-target");
  });
  entry.addEventListener("dragleave", () => {
    entry.classList.remove("drop-target");
  });
  entry.addEventListener("drop", async (event) => {
    event.preventDefault();
    entry.classList.remove("drop-target");
    if (dragState.stage !== stage || !dragState.label) {
      return;
    }
    layout.orders[stage] = moveLabel(layout.orders[stage], dragState.label, label);
    layout.sortModes[stage] = "manual";
    await loadFigure();
  });
}

function buildOrderEntry({ stage, item, mode, layout, grid, aggregateActive = false, isAggregatedTail = false, isPreserved = false, isPreservedTail = false }) {
  const entry = document.createElement("div");
  entry.className = "order-item";
  if (isAggregatedTail) {
    entry.classList.add("tail-item");
  }
  if (isPreserved) {
    entry.classList.add("preserved-item");
  }
  entry.draggable = mode === "manual";
  entry.dataset.stage = stage;
  entry.dataset.label = item.label;
  entry.dataset.key = itemIdentity(item);
  const valueMarkup =
    state.accessMode === "analyst"
      ? `<span class="order-item-value">${numberFormatter.format(item.value)} t</span>`
      : "";
  const rankNumber = Number(item.rank);
  const rankMarkup = Number.isFinite(rankNumber)
    ? `<span class="order-item-rank">#${numberFormatter.format(rankNumber)}</span>`
    : "";
  entry.innerHTML = `
    <div class="order-item-main">
      <div class="order-item-title">
        ${rankMarkup}
        <span class="order-item-label">${escapeHtml(item.label)}</span>
      </div>
      ${isPreservedTail ? '<span class="preserve-badge">Kept from tail</span>' : ""}
      ${isPreserved && !isPreservedTail ? '<span class="preserve-badge">Kept</span>' : ""}
      ${isAggregatedTail ? '<span class="tail-badge">Aggregated tail</span>' : ""}
    </div>
    <div class="order-item-actions">
      ${valueMarkup}
    </div>
  `;
  if (aggregateActive) {
    const actionHost = entry.querySelector(".order-item-actions");
    const keepButton = document.createElement("button");
    keepButton.type = "button";
    keepButton.className = "order-keep-toggle";
    keepButton.textContent = isPreserved ? "Kept" : "Keep";
    keepButton.setAttribute("aria-pressed", isPreserved ? "true" : "false");
    keepButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const key = itemIdentity(item);
      const current = new Set(getAggregatePreserveList(stage));
      if (current.has(key)) {
        current.delete(key);
      } else {
        current.add(key);
      }
      setAggregatePreserveList(stage, Array.from(current));
      await loadFigure();
    });
    actionHost?.prepend(keepButton);
  }
  if (mode === "manual") {
    addManualDragHandlers(entry, stage, item.label, layout, grid);
  }
  return entry;
}

function renderGroupedItems(list, items, stage, mode, layout, grid, aggregateCount) {
  const preservedKeys = new Set(syncAggregatePreserve(stage, items));
  const aggregateActive = mode !== "continent" && aggregateCount > 0;
  const tailKeys = aggregateActive ? aggregateTailKeySet(items, aggregateCount, preservedKeys) : new Set();
  const naturalTailKeys = aggregateActive ? aggregateTailKeySet(items, aggregateCount, new Set()) : new Set();
  let currentGroup = null;
  items.forEach((item) => {
    const key = itemIdentity(item);
    const group = item.group || "Unknown";
    if (group !== currentGroup) {
      currentGroup = group;
      const heading = document.createElement("div");
      heading.className = "group-heading";
      heading.textContent = group;
      if (item.groupColor) {
        heading.style.borderColor = item.groupColor;
        heading.style.color = item.groupColor;
      }
      list.appendChild(heading);
    }
    list.appendChild(
      buildOrderEntry({
        stage,
        item,
        mode,
        layout,
        grid,
        aggregateActive,
        isAggregatedTail: tailKeys.has(key),
        isPreserved: preservedKeys.has(key),
        isPreservedTail: preservedKeys.has(key) && naturalTailKeys.has(key),
      }),
    );
  });
}

function sortModeLabel(mode) {
  return {
    size: "By Size",
    manual: "Manual",
    continent: "By Continent",
  }[mode] || mode;
}

function buildOrderStageEditor(stage, config, grid) {
  const layout = currentLayoutState();
  const mode = layout.sortModes[stage] || config.sortMode || "size";
  layout.sortModes[stage] = mode;
  const items = getRenderedItems(stage, config);
  const specialPosition = getSpecialPosition(stage, config);
  const aggregateCount = getAggregateCount(stage, config);
  const aggregateDisabled = mode === "continent" || (config.maxAggregateCount || 0) === 0;
  const aggregateActive = !aggregateDisabled && aggregateCount > 0;
  const preservedKeys = new Set(syncAggregatePreserve(stage, items));
  const preservedItems = items.filter((item) => preservedKeys.has(itemIdentity(item)));

  const card = document.createElement("article");
  card.className = "order-card order-card-active";

  const head = document.createElement("div");
  head.className = "order-card-head order-card-head-static";
  head.innerHTML = `
    <div>
      <strong>${stage}</strong>
      <span>${escapeHtml(config.label.replace(`${stage} `, ""))}</span>
    </div>
    <span>${items.length} items</span>
  `;
  card.appendChild(head);

  const body = document.createElement("div");
  body.className = "order-card-body";

  const toggle = document.createElement("div");
  toggle.className = "sort-toggle";
  ["size", "manual", "continent"].forEach((sortMode) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill-btn";
    button.textContent = sortModeLabel(sortMode);
    if (mode === sortMode) {
      button.classList.add("active");
    }
    button.addEventListener("click", async () => {
      layout.sortModes[stage] = sortMode;
      if (sortMode === "manual") {
        syncManualOrder(stage, config.items);
      }
      if (sortMode === "continent") {
        layout.aggregateCounts[stage] = 0;
      }
      await loadFigure();
    });
    toggle.appendChild(button);
  });
  body.appendChild(toggle);

  const specialControl = document.createElement("div");
  specialControl.className = "special-control";
  specialControl.innerHTML = `<div class="aggregate-label">Special nodes</div>`;
  const specialToggle = document.createElement("div");
  specialToggle.className = "sort-toggle compact-toggle";
  ["first", "last"].forEach((position) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pill-btn";
    button.textContent = position === "first" ? "Place First" : "Place Last";
    button.disabled = !config.hasSpecialNodes;
    if (specialPosition === position) {
      button.classList.add("active");
    }
    button.addEventListener("click", async () => {
      layout.specialPositions[stage] = position;
      await loadFigure();
    });
    specialToggle.appendChild(button);
  });
  specialControl.appendChild(specialToggle);
  const specialNote = document.createElement("div");
  specialNote.className = "aggregate-note";
  specialNote.textContent = config.hasSpecialNodes
    ? `${config.specialNodeCount} special-case node${config.specialNodeCount === 1 ? "" : "s"} stay together at the ${
        specialPosition === "first" ? "start" : "end"
      } of this stage.`
    : "This stage has no special-case nodes in the current view.";
  specialControl.appendChild(specialNote);
  body.appendChild(specialControl);

  const aggregateControl = document.createElement("div");
  aggregateControl.className = "aggregate-control";
  aggregateControl.innerHTML = `
    <div class="aggregate-count-panel">
      <label class="aggregate-label" for="aggregate-${stage}">Aggregate tail count</label>
      <input
        id="aggregate-${stage}"
        class="aggregate-input"
        type="number"
        min="0"
        max="${config.maxAggregateCount || 0}"
        step="1"
        value="${aggregateCount}"
        ${aggregateDisabled ? "disabled" : ""}
      />
      <div class="aggregate-note">${
        mode === "continent"
          ? "This mode consolidates the chart into one continent node for this stage."
          : config.maxAggregateCount > 0
            ? `Collapse the last 0-${config.maxAggregateCount} items into one node after sorting.`
            : "This stage does not have enough standalone nodes to aggregate."
      }</div>
    </div>
    <div class="aggregate-preserve-panel ${aggregateActive ? "" : "is-muted"}">
      <div class="aggregate-label">Preserved countries</div>
      <div class="preserve-chip-row">
        ${
          preservedItems.length
            ? preservedItems
                .map((item) => {
                  const key = itemIdentity(item);
                  return `
                    <span class="preserve-chip">
                      ${escapeHtml(item.label)}
                      <button type="button" data-preserve-key="${escapeHtml(key)}" aria-label="Remove ${escapeHtml(item.label)} from preserved countries">x</button>
                    </span>
                  `;
                })
                .join("")
            : `<span class="preserve-empty">${aggregateActive ? "No preserved countries" : "Set tail count to enable preserves"}</span>`
        }
      </div>
    </div>
  `;
  const aggregateInput = aggregateControl.querySelector("input");
  if (aggregateInput) {
    aggregateInput.disabled = aggregateDisabled;
    if (!aggregateDisabled) {
      aggregateInput.removeAttribute("disabled");
      aggregateInput.addEventListener("change", async () => {
        layout.aggregateCounts[stage] = clampAggregateCount(aggregateInput.value, config.maxAggregateCount || 0);
        await loadFigure();
      });
      aggregateInput.addEventListener("keydown", async (event) => {
        if (event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        layout.aggregateCounts[stage] = clampAggregateCount(aggregateInput.value, config.maxAggregateCount || 0);
        await loadFigure();
      });
    }
  }
  aggregateControl.querySelectorAll("[data-preserve-key]").forEach((button) => {
    button.addEventListener("click", async () => {
      const key = String(button.getAttribute("data-preserve-key") || "");
      if (!key) {
        return;
      }
      const next = getAggregatePreserveList(stage).filter((value) => value !== key);
      setAggregatePreserveList(stage, next);
      await loadFigure();
    });
  });
  body.appendChild(aggregateControl);

  const list = document.createElement("div");
  list.className = "order-list";
  if (!items.length) {
    list.innerHTML = `<div class="order-empty">No standalone nodes in this stage for the current view.</div>`;
  } else if (mode === "continent") {
    renderGroupedItems(list, items, stage, mode, layout, grid, 0);
  } else {
    const tailKeys = aggregateActive ? aggregateTailKeySet(items, aggregateCount, preservedKeys) : new Set();
    const naturalTailKeys = aggregateActive ? aggregateTailKeySet(items, aggregateCount, new Set()) : new Set();
    items.forEach((item) => {
      const key = itemIdentity(item);
      list.appendChild(
        buildOrderEntry({
          stage,
          item,
          mode,
          layout,
          grid,
          aggregateActive,
          isAggregatedTail: tailKeys.has(key),
          isPreserved: preservedKeys.has(key),
          isPreservedTail: preservedKeys.has(key) && naturalTailKeys.has(key),
        }),
      );
    });
  }
  body.appendChild(list);
  card.appendChild(body);
  return card;
}

function syncOrderStudioDetailHeight(shell = orderLayoutShell, rail = orderLayoutRail) {
  if (!shell || !rail || !shell.isConnected || !rail.isConnected) {
    return;
  }

  const applyHeight = () => {
    if (!shell.isConnected || !rail.isConnected) {
      return;
    }
    if (window.matchMedia("(max-width: 1180px)").matches) {
      shell.style.removeProperty("--order-rail-height");
      return;
    }
    const railHeight = Math.ceil(rail.getBoundingClientRect().height || 0);
    if (railHeight > 0) {
      shell.style.setProperty("--order-rail-height", `${railHeight}px`);
    }
  };

  window.requestAnimationFrame(() => {
    applyHeight();
    window.requestAnimationFrame(applyHeight);
  });
}

function renderOrderBoard(stageControls) {
  const grid = document.getElementById("order-grid");
  grid.innerHTML = "";
  const availableStages = state.stageOrder.filter((stage) => stageControls[stage]);
  if (!availableStages.length) {
    grid.innerHTML = `<div class="order-empty">No stage controls are available for the current view.</div>`;
    return;
  }
  if (!availableStages.includes(state.selectedOrderStage)) {
    state.selectedOrderStage = availableStages[0];
  }

  const shell = document.createElement("div");
  shell.className = "order-studio-layout";
  const rail = document.createElement("div");
  rail.className = "order-stage-rail";
  const detail = document.createElement("div");
  detail.className = "order-stage-detail";

  availableStages.forEach((stage) => {
    const config = stageControls[stage];
    const layout = currentLayoutState();
    const mode = layout.sortModes[stage] || config.sortMode || "size";
    layout.sortModes[stage] = mode;
    const items = getRenderedItems(stage, config);
    const aggregateCount = getAggregateCount(stage, config);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "order-stage-summary";
    button.classList.toggle("active", stage === state.selectedOrderStage);
    button.setAttribute("aria-pressed", stage === state.selectedOrderStage ? "true" : "false");
    button.innerHTML = `
      <div>
        <strong>${stage}</strong>
        <span>${escapeHtml(config.label.replace(`${stage} `, ""))}</span>
      </div>
      <span>${items.length} items</span>
      <small>${sortModeLabel(mode)}${aggregateCount ? `, tail ${aggregateCount}` : ""}</small>
    `;
    button.addEventListener("click", () => {
      state.selectedOrderStage = stage;
      renderOrderBoard(stageControls);
    });
    rail.appendChild(button);
  });
  detail.appendChild(buildOrderStageEditor(state.selectedOrderStage, stageControls[state.selectedOrderStage], grid));
  shell.appendChild(rail);
  shell.appendChild(detail);
  grid.appendChild(shell);
  orderLayoutShell = shell;
  orderLayoutRail = rail;
  syncOrderStudioDetailHeight(shell, rail);
}

async function applySortModeToAll(sortMode) {
  const layout = currentLayoutState();
  state.stageOrder.forEach((stage) => {
    const config = state.lastStageControls[stage];
    layout.sortModes[stage] = sortMode;
    if (sortMode === "manual" && config) {
      syncManualOrder(stage, config.items || []);
    }
    if (sortMode === "continent") {
      layout.aggregateCounts[stage] = 0;
    }
  });
  await loadFigure();
}

function formatValue(value, key = "") {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "number") {
    if (key.toLowerCase().includes("scale")) {
      return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 });
    }
    if (key.toLowerCase().includes("pct")) {
      return `${(value * 100).toFixed(1)}%`;
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildTableHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }
  const columns = Array.from(
    rows.reduce((set, row) => {
      Object.keys(row).forEach((key) => set.add(key));
      return set;
    }, new Set()),
  );
  return `
    <table class="data-table">
      <thead>
        <tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                ${columns.map((column) => `<td>${escapeHtml(formatValue(row[column], column))}</td>`).join("")}
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function deltaClass(value) {
  if (typeof value !== "number" || value === 0) {
    return "neutral";
  }
  return value > 0 ? "positive" : "negative";
}

function buildDeltaBadge(value, key = "delta") {
  if (value === null || value === undefined || value === "") {
    return '<span class="delta-badge neutral">-</span>';
  }
  const prefix = typeof value === "number" && !key.toLowerCase().includes("pct") && value > 0 ? "+" : "";
  return `<span class="delta-badge ${deltaClass(value)}">${escapeHtml(`${prefix}${formatValue(value, key)}`)}</span>`;
}

function metricDeltaBadgeClass(metric, value) {
  if (typeof value !== "number" || value === 0) {
    return "neutral";
  }
  if (String(metric || "").toLowerCase().includes("reduction %")) {
    return value > 0 ? "positive" : "negative";
  }
  return value < 0 ? "positive" : "negative";
}

function stageDeltaBadgeClass(value) {
  if (typeof value !== "number" || value === 0) {
    return "neutral";
  }
  return value < 0 ? "positive" : "negative";
}

function buildCustomDeltaBadge(value, cssClass, key = "delta") {
  if (value === null || value === undefined || value === "") {
    return '<span class="delta-badge neutral">-</span>';
  }
  const prefix = typeof value === "number" && !key.toLowerCase().includes("pct") && value > 0 ? "+" : "";
  return `<span class="delta-badge ${cssClass}">${escapeHtml(`${prefix}${formatValue(value, key)}`)}</span>`;
}

function buildCompareMetricsTableHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }
  return `
    <table class="data-table compare-table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Original</th>
          <th>Optimized</th>
          <th>Optimized - Original</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map((row) => {
            const deltaKey = String(row.metric || "").toLowerCase().includes("reduction %") ? "pct" : "delta";
            const badgeClass = metricDeltaBadgeClass(row.metric, row.delta);
            return `
              <tr>
                <th scope="row">${escapeHtml(row.metric)}</th>
                <td>${escapeHtml(formatValue(row.baseline, "baseline")) || "-"}</td>
                <td>${escapeHtml(formatValue(row.optimized, "optimized")) || "-"}</td>
                <td>${buildCustomDeltaBadge(row.delta, badgeClass, deltaKey)}</td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function buildCompareStageTableHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }
  return `
    <table class="data-table compare-table">
      <thead>
        <tr>
          <th>Stage</th>
          <th>Original Unknown</th>
          <th>Optimized Unknown</th>
          <th>Unknown: Optimized - Original</th>
          <th>Original Special</th>
          <th>Optimized Special</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <th scope="row">${escapeHtml(row.stage)}</th>
                <td>${escapeHtml(formatValue(row.baseline_unknown, "baseline_unknown"))}</td>
                <td>${escapeHtml(formatValue(row.optimized_unknown, "optimized_unknown"))}</td>
                <td>${buildCustomDeltaBadge(row.unknown_delta, stageDeltaBadgeClass(row.unknown_delta), "delta")}</td>
                <td>${escapeHtml(formatValue(row.baseline_special, "baseline_special"))}</td>
                <td>${escapeHtml(formatValue(row.optimized_special, "optimized_special"))}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function buildCompareParameterTableHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }
  return `
    <table class="data-table compare-table">
      <thead>
        <tr>
          <th>Parameter</th>
          <th>Original</th>
          <th>Optimized</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>
                <th scope="row">${escapeHtml(row.parameter)}</th>
                <td>${escapeHtml(formatValue(row.baseline, "baseline")) || "-"}</td>
                <td>${escapeHtml(formatValue(row.optimized, "optimized")) || "-"}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function isPresent(value) {
  return value !== null && value !== undefined && value !== "";
}

function normalizeLabel(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function shortenText(value, maxLength = 180) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(0, maxLength - 3)).trim()}...`;
}

function extractLabel(row) {
  return row?.label || row?.Metric || row?.metric || row?.Parameter || row?.parameter || row?.["Stage Group"] || row?.stage || "";
}

function extractValue(row) {
  return row?.Value ?? row?.value ?? row?.optimized ?? row?.baseline ?? "";
}

function extractNote(row) {
  return row?.Note || row?.note || "";
}

function findRowByLabel(rows, label) {
  const normalizedTarget = normalizeLabel(label);
  return (rows || []).find((row) => normalizeLabel(extractLabel(row)) === normalizedTarget);
}

function findPanelByTitle(row, title) {
  return (row?.diagnostic_panels || []).find((panel) => normalizeLabel(panel.title) === normalizeLabel(title));
}

function findItemByLabel(items, label) {
  return (items || []).find((item) => normalizeLabel(item.label) === normalizeLabel(label));
}

function buildMetricHighlightHtml(item) {
  const value = isPresent(item?.value) ? formatValue(item.value, item.label || "value") : "-";
  return `
    <article class="diagnostic-highlight${item?.className ? ` ${item.className}` : ""}">
      <span>${escapeHtml(item?.label || "")}</span>
      <strong>${escapeHtml(value)}</strong>
      ${item?.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
    </article>
  `;
}

function buildFactTileHtml(item) {
  const label = item?.label || "";
  const value = isPresent(item?.value) ? formatValue(item.value, label || "value") : "-";
  return `
    <article class="diagnostic-fact${item?.className ? ` ${item.className}` : ""}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${item?.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
    </article>
  `;
}

function buildStageStatHtml(item) {
  const value = isPresent(item?.value) ? formatValue(item.value, item.label || "value") : "-";
  return `
    <article class="stage-stat${item?.className ? ` ${item.className}` : ""}">
      <span>${escapeHtml(item?.label || "")}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

function asNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.replaceAll(",", "").replace("%", ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function stageGroupRank(stageGroup) {
  return { "S1-S2-S3": 0, "S3-S4-S5": 1, "S5-S6-S7": 2 }[stageGroup] ?? 99;
}

function metricValue(rows, label) {
  const row = findRowByLabel(
    (rows || []).map((item) => ({
      label: extractLabel(item),
      value: extractValue(item),
      note: extractNote(item),
    })),
    label,
  );
  return row?.value;
}

function coefficientRowKey(row) {
  return [
    row.transition_display || row.transition || "",
    row.hs_code || "",
    row.coefficient_class || "",
    row.producer_scope || "",
    row.partner_scope || "",
  ].join("::");
}

function buildToneBadge(label, tone = "neutral") {
  const normalized = normalizeLabel(tone || label);
  if (["positive", "negative", "warn", "neutral"].includes(normalized)) {
    return `<span class="delta-badge ${normalized}">${escapeHtml(label || "-")}</span>`;
  }
  const className =
    normalized.includes("reduced") || normalized.includes("success") || normalized.includes("interior")
      ? "positive"
      : normalized.includes("increased") || normalized.includes("upper") || normalized.includes("lower") || normalized.includes("removed")
        ? "warn"
        : "neutral";
  return `<span class="delta-badge ${className}">${escapeHtml(label || "-")}</span>`;
}

function formatSignedChange(value, key = "change") {
  if (!isPresent(value)) {
    return "-";
  }
  const numeric = asNumber(value);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${formatValue(numeric, key)}`;
}

function buildFilterButtons(name, options, activeValue) {
  return `
    <div class="explorer-filter-group" role="group" aria-label="${escapeHtml(name)}">
      ${options
        .map(
          (option) => `
            <button
              type="button"
              class="explorer-filter-btn${option.value === activeValue ? " active" : ""}"
              data-filter="${escapeHtml(name)}"
              data-value="${escapeHtml(option.value)}"
            >${escapeHtml(option.label)}</button>
          `,
        )
        .join("")}
    </div>
  `;
}

function rowMatchesSearch(row, query, fields) {
  if (!query) {
    return true;
  }
  const haystack = fields.map((field) => row[field] ?? "").join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function optimizationStageRows(rows) {
  return (rows || []).filter((row) => Object.prototype.hasOwnProperty.call(row, "Stage Group"));
}

function buildOptimizationImpactOverviewHtml(metricRows, stageRows, unknownRows) {
  const optimizedStages = optimizationStageRows(stageRows);
  if (!optimizedStages.length) {
    return buildMetricSnapshotHtml(metricRows);
  }

  const originalTotal = asNumber(metricValue(metricRows, "Original SN Total"));
  const optimizedTotal = asNumber(metricValue(metricRows, "Optimized SN Total"));
  const reductionTotal = asNumber(metricValue(metricRows, "SN Reduction"));
  const reductionPct = asNumber(metricValue(metricRows, "SN Reduction Pct"));
  const boundHits = asNumber(metricValue(metricRows, "Bound Hits"));
  const scaledSources = asNumber(metricValue(metricRows, "Scaled Sources"));
  const scaledSourceNote =
    scaledSources > 0
      ? `${formatValue(scaledSources, "value")} source-side scaling events recorded`
      : "No source-side scaling events recorded";
  const bestStage = [...optimizedStages].sort(
    (left, right) =>
      asNumber(right["Original SN"]) - asNumber(right["Optimized SN"]) -
      (asNumber(left["Original SN"]) - asNumber(left["Optimized SN"])),
  )[0];
  const strongestUnknown = [...(unknownRows || [])]
    .filter((row) => row.type_key !== "total_special")
    .sort((left, right) => asNumber(right.reduction) - asNumber(left.reduction))[0];
  const reviewStage = [...optimizedStages].sort((left, right) => asNumber(left["Reduction Pct"]) - asNumber(right["Reduction Pct"]))[0];

  const insightItems = [
    {
      label: "Main driver",
      value: bestStage?.["Stage Group"] || "-",
      note: bestStage
        ? `${formatValue(asNumber(bestStage["Original SN"]) - asNumber(bestStage["Optimized SN"]), "reduction")} SN reduction`
        : "",
    },
    {
      label: "Largest node-type drop",
      value: strongestUnknown?.unknown_type || "-",
      note: strongestUnknown
        ? `${strongestUnknown.stage_group} decreased by ${formatValue(strongestUnknown.reduction, "reduction")}`
        : "",
    },
    {
      label: "Constraint pressure",
      value: boundHits,
      note: "Optimized coefficients on Cmin or Cmax.",
    },
    {
      label: "Review priority",
      value: reviewStage?.["Stage Group"] || "-",
      note: reviewStage ? `${formatValue(reviewStage["Reduction Pct"], "pct")} reduction; inspect low-gain stage first.` : "",
    },
  ];

  return `
    <section class="impact-overview">
      <div class="impact-hero">
        <div>
          <span class="impact-label">Original to ${escapeHtml(resultModeLabel(state.resultMode))}</span>
          <div class="impact-flow">
            <strong>${escapeHtml(formatValue(originalTotal, "value"))}</strong>
            <span>to</span>
            <strong>${escapeHtml(formatValue(optimizedTotal, "value"))}</strong>
          </div>
          <p>${escapeHtml(formatValue(reductionTotal, "value"))} lower SN mass, ${escapeHtml(formatValue(reductionPct, "pct"))} reduction across supported stage groups.</p>
        </div>
        <div class="impact-score">
          <span>SN reduction</span>
          <strong>${escapeHtml(formatValue(reductionPct, "pct"))}</strong>
          <small>${escapeHtml(scaledSourceNote)}</small>
        </div>
      </div>
      <div class="impact-insight-grid">
        ${insightItems.map((item) => buildFactTileHtml(item)).join("")}
      </div>
    </section>
  `;
}

function buildMetricSnapshotHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }

  const normalizedRows = rows.map((row) => ({
    label: extractLabel(row),
    value: extractValue(row),
    note: extractNote(row),
  }));
  const isOptimizationSnapshot = normalizedRows.some((row) => normalizeLabel(row.label) === "supported stage groups");

  const highlightLabels = isOptimizationSnapshot
    ? ["Supported Stage Groups", "SN Reduction", "SN Reduction Pct", "c_pp / c_pn / c_np Rows"]
    : ["Unknown Total", "Total Special", "Total Regular", "Structural Sink"];
  const highlightSet = new Set(highlightLabels.map(normalizeLabel));
  const highlights = highlightLabels
    .map((label) => normalizedRows.find((row) => normalizeLabel(row.label) === normalizeLabel(label)))
    .filter(Boolean);
  const detailRows = normalizedRows.filter((row) => !highlightSet.has(normalizeLabel(row.label)));

  return `
    <div class="diagnostic-highlight-grid">
      ${highlights.map((item) => buildMetricHighlightHtml(item)).join("")}
    </div>
    <div class="diagnostic-fact-grid">
      ${detailRows.map((item) => buildFactTileHtml(item)).join("")}
    </div>
  `;
}

function buildStageOutcomeCardHtml(row, isOptimizationView) {
  if (isOptimizationView) {
    const coefficientTotal = ["c_pp Rows", "c_pn Rows", "c_np Rows"].reduce(
      (sum, key) => sum + (Number(row[key]) || 0),
      0,
    );
    const statusValue = String(row.Status || "Recorded");
    const statusClass =
      normalizeLabel(statusValue) === "success"
        ? "positive"
        : isPresent(row.Failure)
          ? "negative"
          : "neutral";
    const headlineNote = row.Failure || `${formatValue(row.Countries, "Countries")} countries | ${formatValue(row["HS Codes"], "HS Codes")} HS codes | ${formatValue(coefficientTotal, "Coefficient Rows")} coefficient rows`;
    const detailItems = [
      { label: "Countries", value: row.Countries },
      { label: "HS codes", value: row["HS Codes"] },
      { label: "Coefficient rows", value: coefficientTotal },
      { label: "Bound hits", value: row["Bound Hits"] },
      { label: "Scaled sources", value: row["Scaled Sources"] },
      { label: "Special total", value: row["Special Total"] },
      { label: "Overflow before scaling", value: row["Overflow Before Scaling"] },
    ];

    return `
      <article class="stage-outcome-card">
        <div class="stage-outcome-head">
          <div>
            <span class="transition-eyebrow">Stage Group</span>
            <h4>${escapeHtml(row["Stage Group"] || "Stage Group")}</h4>
            <p>${escapeHtml(shortenText(headlineNote, 160))}</p>
          </div>
          <span class="delta-badge ${statusClass}">${escapeHtml(statusValue)}</span>
        </div>
        <div class="stage-stat-grid">
          ${[
            { label: "Original SN", value: row["Original SN"] },
            { label: "Optimized SN", value: row["Optimized SN"] },
            { label: "Reduction Pct", value: row["Reduction Pct"] },
          ]
            .map((item) => buildStageStatHtml(item))
            .join("")}
        </div>
        <div class="diagnostic-fact-grid diagnostic-fact-grid-compact">
          ${detailItems.map((item) => buildFactTileHtml(item)).join("")}
        </div>
      </article>
    `;
  }

  return `
    <article class="stage-outcome-card">
      <div class="stage-outcome-head">
        <div>
          <span class="transition-eyebrow">Original Export</span>
          <h4>${escapeHtml(row.stage || "Stage")}</h4>
          <p>Precomputed baseline totals before optimization-specific adjustments.</p>
        </div>
        <span class="delta-badge neutral">Original</span>
      </div>
      <div class="stage-stat-grid">
        ${[
          { label: "Total Flow", value: row.total_value },
          { label: "Unknown Total", value: row.unknown_total },
          { label: "Special Total", value: row.special_total },
        ]
          .map((item) => buildStageStatHtml(item))
          .join("")}
      </div>
    </article>
  `;
}

function reductionBadgeHtml(value) {
  const numeric = asNumber(value);
  const className = numeric > 0 ? "positive" : numeric < 0 ? "negative" : "neutral";
  const prefix = numeric > 0 ? "-" : numeric < 0 ? "+" : "";
  return `<span class="delta-badge ${className}">${escapeHtml(`${prefix}${formatValue(Math.abs(numeric), "reduction")}`)}</span>`;
}

function inverseChangeBadgeHtml(value, key = "change") {
  const numeric = asNumber(value);
  const className = numeric < 0 ? "positive" : numeric > 0 ? "negative" : "neutral";
  return `<span class="delta-badge ${className}">${escapeHtml(formatSignedChange(numeric, key))}</span>`;
}

function buildStageComparisonHtml(rows) {
  const optimizedRows = optimizationStageRows(rows).sort(
    (left, right) => stageGroupRank(left["Stage Group"]) - stageGroupRank(right["Stage Group"]),
  );
  if (!optimizedRows.length) {
    return "";
  }

  const optimizedLabel = resultModeLabel(state.resultMode);
  const maxOriginal = Math.max(...optimizedRows.map((row) => asNumber(row["Original SN"])), 1);
  return `
    <section class="stage-comparison-panel">
      <div class="transition-panel-head">
        <strong>Stage Group Comparison</strong>
        <span>Original SN and ${escapeHtml(optimizedLabel)} SN are compared side by side for each synchronized S1-S2-S3 style group.</span>
      </div>
      <div class="stage-comparison-table-wrap">
        <table class="data-table stage-comparison-table">
          <thead>
            <tr>
              <th>Stage group</th>
              <th>Original SN</th>
              <th>${escapeHtml(optimizedLabel)} SN</th>
              <th>Reduction</th>
              <th>Reduction pct</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${optimizedRows
              .map((row) => {
                const original = asNumber(row["Original SN"]);
                const optimized = asNumber(row["Optimized SN"]);
                const reduction = original - optimized;
                const originalWidth = Math.max(2, Math.min(100, (original / maxOriginal) * 100));
                const optimizedWidth = Math.max(2, Math.min(100, (optimized / maxOriginal) * 100));
                const statusValue = String(row.Status || "Recorded");
                const statusClass =
                  normalizeLabel(statusValue) === "success"
                    ? "positive"
                    : isPresent(row.Failure)
                      ? "negative"
                      : "neutral";
                return `
                  <tr>
                    <th>
                      <strong>${escapeHtml(row["Stage Group"] || "Stage Group")}</strong>
                      <small>${escapeHtml(formatValue(row.Countries, "countries"))} countries | ${escapeHtml(formatValue(row["HS Codes"], "HS Codes"))} HS codes</small>
                    </th>
                    <td>
                      <span>${escapeHtml(formatValue(original, "value"))}</span>
                      <div class="stage-impact-bar stage-impact-bar-original" aria-hidden="true">
                        <span style="width: ${originalWidth.toFixed(2)}%"></span>
                      </div>
                    </td>
                    <td>
                      <span>${escapeHtml(formatValue(optimized, "value"))}</span>
                      <div class="stage-impact-bar stage-impact-bar-optimized" aria-hidden="true">
                        <span style="width: ${optimizedWidth.toFixed(2)}%"></span>
                      </div>
                    </td>
                    <td>${reductionBadgeHtml(reduction)}</td>
                    <td>${escapeHtml(formatValue(row["Reduction Pct"], "pct"))}</td>
                    <td>${buildToneBadge(statusValue, statusClass)}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function buildUnknownBreakdownHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">Unknown node breakdown is available when the selected optimization result publishes synchronized node analysis.</div>`;
  }
  const grouped = new Map();
  [...rows]
    .sort((left, right) => {
      const stageDiff = stageGroupRank(left.stage_group) - stageGroupRank(right.stage_group);
      if (stageDiff !== 0) {
        return stageDiff;
      }
      return asNumber(left.type_order) - asNumber(right.type_order);
    })
    .forEach((row) => {
      const key = row.stage_group || "Stage group";
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key).push(row);
    });

  const maxValue = Math.max(
    ...rows.flatMap((row) => [asNumber(row.original_value), asNumber(row.optimized_value)]),
    1,
  );
  const barWidth = (value) => Math.max(1, Math.min(100, (asNumber(value) / maxValue) * 100)).toFixed(2);

  return `
    <section class="unknown-breakdown-panel">
      <div class="transition-panel-head">
        <strong>Unknown Node Breakdown</strong>
        <span>Each type of special/unknown node is separated so users can see where the optimizer reduced volume and where it moved volume between buckets.</span>
      </div>
      <div class="unknown-breakdown-grid">
        ${Array.from(grouped.entries())
          .map(([stageGroup, groupRows]) => {
            const totalRow = groupRows.find((row) => row.type_key === "total_special");
            const detailRows = groupRows.filter((row) => row.type_key !== "total_special");
            return `
              <article class="unknown-breakdown-card">
                <div class="unknown-breakdown-head">
                  <div>
                    <span class="transition-eyebrow">Stage group</span>
                    <strong>${escapeHtml(stageGroup)}</strong>
                  </div>
                  ${totalRow ? reductionBadgeHtml(totalRow.reduction) : ""}
                </div>
                <div class="unknown-total-row">
                  <span>Total special nodes</span>
                  <strong>${escapeHtml(formatValue(totalRow?.optimized_value ?? 0, "value"))}</strong>
                  <small>${escapeHtml(formatValue(totalRow?.original_value ?? 0, "value"))} original | ${escapeHtml(formatValue(totalRow?.reduction_pct ?? 0, "pct"))} reduction</small>
                </div>
                <div class="unknown-breakdown-table-wrap">
                  <table class="data-table unknown-breakdown-table">
                    <thead>
                      <tr>
                        <th>Unknown type</th>
                        <th>Original</th>
                        <th>Optimized</th>
                        <th>Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${detailRows
                        .map(
                          (row) => `
                            <tr>
                              <th>
                                <span class="unknown-node-label">
                                  <span class="unknown-dot unknown-dot-${escapeHtml(row.type_key || "unknown")}"></span>
                                  ${escapeHtml(row.unknown_type || "Unknown")}
                                </span>
                              </th>
                              <td>
                                <span>${escapeHtml(formatValue(row.original_value, "value"))}</span>
                                <div class="unknown-bar unknown-bar-original" aria-hidden="true"><span style="width: ${barWidth(row.original_value)}%"></span></div>
                              </td>
                              <td>
                                <span>${escapeHtml(formatValue(row.optimized_value, "value"))}</span>
                                <div class="unknown-bar unknown-bar-optimized" aria-hidden="true"><span style="width: ${barWidth(row.optimized_value)}%"></span></div>
                              </td>
                              <td>${reductionBadgeHtml(row.reduction)}</td>
                            </tr>
                          `,
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>
              </article>
            `;
          })
          .join("")}
      </div>
    </section>
  `;
}

function buildStageOutcomeCardsHtml(rows, unknownRows = []) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }
  const isOptimizationView = Object.prototype.hasOwnProperty.call(rows[0], "Stage Group");
  if (isOptimizationView) {
    return `
      <div class="stage-comparison-stack">
        ${buildStageComparisonHtml(rows)}
        ${buildUnknownBreakdownHtml(unknownRows)}
      </div>
    `;
  }
  return `
    <div class="stage-outcome-grid">
      ${rows.map((row) => buildStageOutcomeCardHtml(row, isOptimizationView)).join("")}
    </div>
  `;
}

function buildParameterItemHtml(row) {
  const label = extractLabel(row);
  const value = extractValue(row);
  const note = extractNote(row);
  return `
    <article class="parameter-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(isPresent(value) ? formatValue(value, label || "value") : "-")}</strong>
      ${note ? `<small>${escapeHtml(shortenText(note, 220))}</small>` : ""}
    </article>
  `;
}

function buildParameterGroupHtml(title, subtitle, rows) {
  if (!rows.length) {
    return "";
  }
  return `
    <section class="parameter-group-card">
      <div class="transition-panel-head">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(subtitle)}</span>
      </div>
      <div class="parameter-item-grid">
        ${rows.map((row) => buildParameterItemHtml(row)).join("")}
      </div>
    </section>
  `;
}

function buildParameterOverviewHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }

  const normalizedRows = rows.map((row) => ({
    label: extractLabel(row),
    value: extractValue(row),
    note: extractNote(row),
  }));
  const hasFirstOptimizationGroups = normalizedRows.some((row) => normalizeLabel(row.label) === "data source");

  if (!hasFirstOptimizationGroups) {
    return `
      <div class="parameter-group-grid parameter-group-grid-single">
        ${buildParameterGroupHtml(
          "Original Mode",
          "Baseline mode does not introduce optimizer weights, bounds, or synchronized factor analysis.",
          normalizedRows,
        )}
      </div>
    `;
  }

  const runtimeRows = ["Data Source", "Result Sync", "Solver"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);
  const weightRows = ["alpha", "beta_pp", "beta_pn", "beta_np"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);
  const boundsRows = ["Bounds", "Source Scaling", "Special Handling", "HS Memo Rules"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);
  const groupedLabels = new Set(
    ["Data Source", "Result Sync", "Solver", "alpha", "beta_pp", "beta_pn", "beta_np", "Bounds", "Source Scaling", "Special Handling", "HS Memo Rules"].map(
      normalizeLabel,
    ),
  );
  const selectedStageRows = normalizedRows.filter((row) => !groupedLabels.has(normalizeLabel(row.label)));

  return `
    <div class="parameter-group-grid">
      ${buildParameterGroupHtml(
        "Runtime Snapshot",
        "Which optimizer output is rendered and how it becomes the published runtime view.",
        runtimeRows,
      )}
      ${buildParameterGroupHtml(
        "Objective Weights",
        "Active weights used for SN reduction and coefficient movement penalties.",
        weightRows,
      )}
      ${buildParameterGroupHtml(
        "Bounds, Scaling And HS Memo",
        "Constraint behavior, special handling, source scaling, and memo-driven HS rules.",
        boundsRows,
      )}
      ${buildParameterGroupHtml(
        "Selected Stage Settings",
        "Stage-level status, beta weights, and selection notes for the chosen optimization result.",
        selectedStageRows,
      )}
    </div>
  `;
}

function buildTransitionMetricPill(itemOrLabel, value, tone = "neutral") {
  const item = typeof itemOrLabel === "object" ? itemOrLabel : { label: itemOrLabel, value, tone };
  return `
    <div class="transition-pill transition-pill-${item.tone || tone}">
      <span>${escapeHtml(item.label || "")}</span>
      <strong>${escapeHtml(formatValue(item.value, item.label || "value"))}</strong>
    </div>
  `;
}

function buildKeyValueGrid(items, emptyText) {
  if (!items || !items.length) {
    return `<div class="order-empty">${escapeHtml(emptyText)}</div>`;
  }
  return `
    <div class="kv-grid">
      ${items
        .map((item) => {
          const label = item.label || item.country || item.parameter || "";
          const value = item.value ?? item.scale;
          return `
            <div class="kv-item">
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(formatValue(value, label || "value"))}</strong>
              ${item.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function buildDiagnosticListHtml(items, emptyText = "No rows were recorded for this section.") {
  const visibleItems = (items || []).filter((item) => isPresent(item?.value) || item?.note);
  if (!visibleItems.length) {
    return `<div class="order-empty">${escapeHtml(emptyText)}</div>`;
  }
  return `
    <div class="diagnostic-list">
      ${visibleItems
        .map((item) => {
          const label = item.label || "";
          const value = isPresent(item.value) ? formatValue(item.value, label || "value") : "-";
          return `
            <article class="diagnostic-list-item">
              <strong>${escapeHtml(label)}</strong>
              <span>${escapeHtml(value)}</span>
              ${item.note ? `<small>${escapeHtml(shortenText(item.note, 220))}</small>` : ""}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function buildStageDiagnosticSectionHtml(title, subtitle, contentHtml, extraClass = "") {
  return `
    <section class="diagnostic-section${extraClass ? ` ${extraClass}` : ""}">
      <div class="transition-panel-head">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(subtitle)}</span>
      </div>
      ${contentHtml}
    </section>
  `;
}

function buildTransitionCardHtml(row) {
  const signalLabel = row.signal_label || (row.has_signal ? "Tuned" : "No visible adjustment");
  const signalClass = row.signal_class || (row.has_signal ? "positive" : "neutral");
  const diagnosticPills = row.diagnostic_pills || [];
  const outcomePanel = findPanelByTitle(row, "Outcome");
  const coveragePanel = findPanelByTitle(row, "Coefficient Coverage");
  const scalingPanel = findPanelByTitle(row, "Sankey Scaling");
  const boundsPanel = findPanelByTitle(row, "Bounds");
  const specialPanel = findPanelByTitle(row, "Special Handling");
  const exposurePanel = findPanelByTitle(row, "Top HS Exposure");
  const setupPanel = findPanelByTitle(row, "Run Setup");
  const failureValue = findItemByLabel(outcomePanel?.items, "Failure")?.value;

  const outcomeFacts = [
    findItemByLabel(outcomePanel?.items, "Countries"),
    findItemByLabel(coveragePanel?.items, "HS codes"),
    findItemByLabel(outcomePanel?.items, "Original SN"),
    findItemByLabel(outcomePanel?.items, "Optimized SN"),
    findItemByLabel(outcomePanel?.items, "Reduction Pct"),
  ].filter(Boolean);
  const coverageFacts = [
    findItemByLabel(coveragePanel?.items, "c_pp rows"),
    findItemByLabel(coveragePanel?.items, "c_pn rows"),
    findItemByLabel(coveragePanel?.items, "c_np rows"),
    findItemByLabel(coveragePanel?.items, "Total rows"),
  ].filter(Boolean);
  const boundsAndScalingFacts = [
    findItemByLabel(boundsPanel?.items, "Lower hits"),
    findItemByLabel(boundsPanel?.items, "Upper hits"),
    findItemByLabel(boundsPanel?.items, "Bound hits"),
    findItemByLabel(boundsPanel?.items, "Interior rows"),
    findItemByLabel(scalingPanel?.items, "Scaled sources"),
    findItemByLabel(scalingPanel?.items, "Overflow before scaling"),
    findItemByLabel(scalingPanel?.items, "Worst scale ratio"),
    findItemByLabel(scalingPanel?.items, "Residual self / non-target fill"),
  ].filter(Boolean);
  const specialSummaryFacts = [
    findItemByLabel(specialPanel?.items, "Representative total"),
    findItemByLabel(specialPanel?.items, "Adjustment types"),
  ].filter(Boolean);
  const specialBreakoutItems = (specialPanel?.items || [])
    .filter(
      (item) =>
        ![
          "representative total",
          "adjustment types",
        ].includes(normalizeLabel(item.label)),
    )
    .slice(0, 4);
  const setupItems = (setupPanel?.items || []).slice(0, 5);
  const exposureItems = (exposurePanel?.items || []).slice(0, 5);
  const cardTitle = row.card_title || row.folder_display || "Stage Diagnostic";

  return `
    <article class="transition-card transition-stage-card">
      <div class="transition-card-head">
        <div>
          <span class="transition-eyebrow">${escapeHtml(row.transition_display || row.transition || "")}</span>
          <h4>${escapeHtml(cardTitle)}</h4>
          <p>${escapeHtml(row.card_note || row.folder_group || "")}</p>
        </div>
        <span class="delta-badge ${signalClass}">${escapeHtml(signalLabel)}</span>
      </div>
      <div class="transition-pill-row">
        ${diagnosticPills.map((item) => buildTransitionMetricPill(item)).join("")}
      </div>
      <div class="stage-diagnostic-grid">
        ${buildStageDiagnosticSectionHtml(
          "Run Outcome",
          "Stage-group size, SN totals, and reduction after synchronization into the published snapshot.",
          `<div class="diagnostic-fact-grid diagnostic-fact-grid-compact">${outcomeFacts.map((item) => buildFactTileHtml(item)).join("")}</div>`,
        )}
        ${buildStageDiagnosticSectionHtml(
          "Coefficient Coverage",
          "How many c_pp / c_pn / c_np rows were emitted for this stage group.",
          `<div class="diagnostic-fact-grid diagnostic-fact-grid-compact">${coverageFacts.map((item) => buildFactTileHtml(item)).join("")}</div>`,
        )}
        ${buildStageDiagnosticSectionHtml(
          "Bounds And Scaling",
          "Constraint pressure and any source-side rescaling required before residual fill.",
          `<div class="diagnostic-fact-grid diagnostic-fact-grid-compact">${boundsAndScalingFacts.map((item) => buildFactTileHtml(item)).join("")}</div>`,
        )}
        ${buildStageDiagnosticSectionHtml(
          "Special Handling",
          "Representative excluded volume plus the largest mirrored or bypass adjustments recorded here.",
          `
            <div class="diagnostic-fact-grid diagnostic-fact-grid-compact">
              ${specialSummaryFacts.map((item) => buildFactTileHtml(item)).join("")}
            </div>
            ${buildDiagnosticListHtml(
              specialBreakoutItems,
              specialPanel?.emptyText || "No special-case adjustments were recorded for this stage group.",
            )}
          `,
        )}
        ${buildStageDiagnosticSectionHtml(
          "Top HS Exposure",
          "Largest raw-trade HS series contributing to this stage-group run.",
          buildDiagnosticListHtml(
            exposureItems,
            exposurePanel?.emptyText || "No HS exposure rows were recorded for this stage group.",
          ),
        )}
        ${buildStageDiagnosticSectionHtml(
          "Run Setup",
          "Solver, weights, bounds, source scaling, and memo rules carried by the optimizer output.",
          buildDiagnosticListHtml(
            setupItems,
            setupPanel?.emptyText || "No setup notes were recorded for this stage group.",
          ),
        )}
      </div>
      ${
        isPresent(failureValue)
          ? `<div class="diagnostic-inline-note warn">${escapeHtml(String(failureValue))}</div>`
          : ""
      }
    </article>
  `;
}

function coefficientStageLabel(row) {
  return row?.transition_display || row?.transition || "Stage group";
}

function optionList(rows, getter, allLabel, preferredOrder = []) {
  const order = new Map(preferredOrder.map((value, index) => [value, index]));
  const values = Array.from(new Set((rows || []).map(getter).filter(Boolean)));
  values.sort((left, right) => {
    const leftRank = order.has(left) ? order.get(left) : stageGroupRank(left);
    const rightRank = order.has(right) ? order.get(right) : stageGroupRank(right);
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return String(left).localeCompare(String(right));
  });
  return [{ value: "all", label: allLabel }, ...values.map((value) => ({ value, label: value }))];
}

function coefficientDeviation(row) {
  if (!isPresent(row?.coef_value) || !isPresent(row?.recommended_value)) {
    return null;
  }
  return asNumber(row.coef_value) - asNumber(row.recommended_value);
}

function filteredCoefficientRows(rows) {
  const filters = state.diagnosticFilters;
  return (rows || []).filter((row) => {
    const stage = coefficientStageLabel(row);
    const coefficientClass = row.coefficient_class || "Unknown";
    const boundStatus = row.bound_status || "Unknown";
    const matchesStage = filters.coefficientStage === "all" || stage === filters.coefficientStage;
    const matchesClass = filters.coefficientClass === "all" || coefficientClass === filters.coefficientClass;
    const matchesBound = filters.coefficientBound === "all" || boundStatus === filters.coefficientBound;
    const matchesSearch = rowMatchesSearch(row, filters.coefficientSearch, [
      "transition_display",
      "transition",
      "hs_code",
      "coefficient_class",
      "producer_scope",
      "partner_scope",
      "bound_status",
    ]);
    return matchesStage && matchesClass && matchesBound && matchesSearch;
  });
}

function buildCoefficientIntroHtml(rows, visibleRows) {
  const selectedResultLabel = resultModeLabel(state.resultMode);
  const classCounts = rows.reduce((accumulator, row) => {
    const key = row.coefficient_class || "Unknown";
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  const boundCounts = rows.reduce((accumulator, row) => {
    const key = row.bound_status || "Unknown";
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  const stageCounts = rows.reduce((accumulator, row) => {
    const key = coefficientStageLabel(row);
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  const uniqueHsCodes = new Set(rows.map((row) => row.hs_code || "Unknown"));
  const largestExposureRow = rows.reduce((currentMax, row) => {
    if (!currentMax) {
      return row;
    }
    return asNumber(row.exposure) > asNumber(currentMax.exposure) ? row : currentMax;
  }, null);
  const classSummary = ["c_pp", "c_pn", "c_np", "PP", "PN", "NP"]
    .filter((label) => classCounts[label])
    .map((label) => `${label} ${classCounts[label]}`)
    .join(" | ");
  const boundSummary = ["Lower", "Upper", "Interior"]
    .filter((label) => boundCounts[label])
    .map((label) => `${label} ${boundCounts[label]}`)
    .join(" | ");
  const busiestStage = Object.entries(stageCounts).sort((left, right) => right[1] - left[1])[0];
  const summaryItems = [
    { label: "Visible Rows", value: visibleRows.length, note: `${rows.length} total coefficient rows in this ${selectedResultLabel} export.` },
    { label: "Stage Groups", value: Object.keys(stageCounts).length, note: busiestStage ? `${busiestStage[0]} has ${busiestStage[1]} coefficient rows.` : "" },
    { label: "HS Codes", value: uniqueHsCodes.size, note: "Unique HS codes represented by the optimizer coefficient output." },
    { label: "Class Mix", value: classSummary || "-", note: "c_pp / c_pn / c_np identify how the row participates in the balance equations." },
    { label: "Bound Status Mix", value: boundSummary || "-", note: "Lower and Upper rows sit on Cmin or Cmax; Interior rows remain inside bounds." },
    largestExposureRow
      ? {
          label: "Largest Exposure Row",
          value: largestExposureRow.exposure,
          note: `${coefficientStageLabel(largestExposureRow)} | ${largestExposureRow.hs_code || "Unknown"} | ${largestExposureRow.producer_scope || "Unknown"} -> ${largestExposureRow.partner_scope || "Unknown"}`,
        }
      : null,
  ].filter(Boolean);

  return `
    <section class="producer-coefficient-intro">
      <p>${escapeHtml(selectedResultLabel)} chooses coefficients within Cmin/Cmax while minimizing unknown-node mass and weighted movement away from the recommended value. Use the filters to inspect one coefficient row, then compare its stage with the trade flows below.</p>
      <div class="producer-summary-grid">
        ${summaryItems.map((item) => buildFactTileHtml(item)).join("")}
      </div>
      <div class="producer-legend-grid">
        <article class="producer-legend-item">
          <strong>Recommended</strong>
          <span>The optimizer's reference coefficient before movement penalties are applied.</span>
        </article>
        <article class="producer-legend-item">
          <strong>Cmin / Cmax</strong>
          <span>The lower and upper bounds that keep the coefficient inside the published constraint range.</span>
        </article>
        <article class="producer-legend-item">
          <strong>Exposure</strong>
          <span>The raw trade quantity attached to this coefficient row in the selected stage group and HS code.</span>
        </article>
      </div>
    </section>
  `;
}

function buildCoefficientDetailHtml(row, tradeRows) {
  if (!row) {
    return `
      <aside class="explorer-detail">
        <div class="order-empty">No coefficient rows match the active filters.</div>
      </aside>
    `;
  }

  const deviation = coefficientDeviation(row);
  const lower = asNumber(row.lower_bound);
  const upper = asNumber(row.upper_bound);
  const recommended = asNumber(row.recommended_value);
  const coefficient = asNumber(row.coef_value);
  const hasRange = isPresent(row.lower_bound) && isPresent(row.upper_bound) && Math.abs(upper - lower) > 1e-12;
  const coefPosition = hasRange ? Math.max(0, Math.min(100, ((coefficient - lower) / (upper - lower)) * 100)) : 0;
  const recommendedPosition = hasRange ? Math.max(0, Math.min(100, ((recommended - lower) / (upper - lower)) * 100)) : 0;
  const stageGroup = coefficientStageLabel(row);
  const relatedFlows = (tradeRows || [])
    .filter((flow) => flow.stage_group === stageGroup)
    .slice(0, 5);

  return `
    <aside class="explorer-detail">
      <div class="explorer-detail-head">
        <div>
          <span class="transition-eyebrow">Selected coefficient</span>
          <strong>${escapeHtml(row.coefficient_class || "Coefficient")} | ${escapeHtml(row.hs_code || "Unknown HS")}</strong>
          <small>${escapeHtml(stageGroup)} | ${escapeHtml(row.producer_scope || "Unknown")} -> ${escapeHtml(row.partner_scope || "Unknown")}</small>
        </div>
        ${buildToneBadge(row.bound_status || "Unknown", row.bound_status || "neutral")}
      </div>
      <div class="coefficient-range">
        <div class="coefficient-range-track" aria-hidden="true">
          <span class="coefficient-range-rec" style="left: ${recommendedPosition.toFixed(2)}%"></span>
          <span class="coefficient-range-value" style="left: ${coefPosition.toFixed(2)}%"></span>
        </div>
        <div class="coefficient-range-labels">
          <span>Cmin ${escapeHtml(formatValue(row.lower_bound, "coefficient"))}</span>
          <span>Recommended ${escapeHtml(formatValue(row.recommended_value, "coefficient"))}</span>
          <span>Cmax ${escapeHtml(formatValue(row.upper_bound, "coefficient"))}</span>
        </div>
      </div>
      <div class="diagnostic-fact-grid diagnostic-fact-grid-compact">
        ${[
          { label: "Optimized Coefficient", value: row.coef_value },
          { label: "Delta From Recommended", value: deviation ?? "-", note: "Optimized value minus recommended coefficient." },
          { label: "Exposure", value: row.exposure },
          { label: "Exposure Share", value: row.exposure_share },
        ]
          .map((item) => buildFactTileHtml(item))
          .join("")}
      </div>
      <div class="related-flow-list">
        <div class="transition-panel-head">
          <strong>Related Stage Flow Changes</strong>
          <span>Largest flow changes in the same stage group.</span>
        </div>
        ${relatedFlows.length
          ? `
            <table class="data-table related-flow-table">
              <tbody>
                ${relatedFlows
                  .map(
                    (flow) => `
                      <tr>
                        <th>${escapeHtml(flow.source_label || "Source")} -> ${escapeHtml(flow.target_label || "Target")}</th>
                        <td>${inverseChangeBadgeHtml(flow.change)}</td>
                      </tr>
                    `,
                  )
                  .join("")}
              </tbody>
            </table>
          `
          : `<div class="order-empty">No matching trade-flow comparison rows are available for this stage group.</div>`}
      </div>
    </aside>
  `;
}

function buildProducerCoefficientSectionsHtml(rows, tradeRows = []) {
  if (!rows || !rows.length) {
    return `
      <div class="order-empty">
        No coefficient rows are present in the active runtime data for this optimization export.
        Render deployments must include optimizer diagnostics such as intermediate coefficient CSVs
        or workbook-backed selected-stage hyperparameter files under the configured app data directory.
      </div>
    `;
  }

  const visibleRows = filteredCoefficientRows(rows);
  const selectedRow =
    visibleRows.find((row) => coefficientRowKey(row) === state.diagnosticFilters.selectedCoefficientKey) ||
    visibleRows[0] ||
    rows[0];
  if (selectedRow) {
    state.diagnosticFilters.selectedCoefficientKey = coefficientRowKey(selectedRow);
  }

  const stageOptions = optionList(rows, coefficientStageLabel, "All stages", ["S1-S2-S3", "S3-S4-S5", "S5-S6-S7"]);
  const classOptions = optionList(rows, (row) => row.coefficient_class || "Unknown", "All classes", ["c_pp", "c_pn", "c_np", "PP", "PN", "NP"]);
  const boundOptions = optionList(rows, (row) => row.bound_status || "Unknown", "All bounds", ["Lower", "Upper", "Interior"]);
  const tableRows = visibleRows.slice(0, 120);
  const hiddenCount = Math.max(0, visibleRows.length - tableRows.length);

  return `
    <section class="explorer-shell coefficient-explorer">
      ${buildCoefficientIntroHtml(rows, visibleRows)}
      <div class="explorer-toolbar">
        <label class="explorer-search">
          <span>Find coefficient</span>
          <input id="coefficient-search" type="search" value="${escapeHtml(state.diagnosticFilters.coefficientSearch)}" placeholder="HS code, class, country, bound status" />
        </label>
        <div class="explorer-filter-stack">
          <div>
            <span>Stage</span>
            ${buildFilterButtons("coefficientStage", stageOptions, state.diagnosticFilters.coefficientStage)}
          </div>
          <div>
            <span>Class</span>
            ${buildFilterButtons("coefficientClass", classOptions, state.diagnosticFilters.coefficientClass)}
          </div>
          <div>
            <span>Bound</span>
            ${buildFilterButtons("coefficientBound", boundOptions, state.diagnosticFilters.coefficientBound)}
          </div>
        </div>
      </div>
      <div class="explorer-layout">
        <div class="explorer-table-wrap">
          <table class="data-table explorer-table">
            <thead>
              <tr>
                <th>Coefficient</th>
                <th>HS code</th>
                <th>Scope</th>
                <th>Optimized</th>
                <th>Recommended</th>
                <th>Bound</th>
                <th>Exposure</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${tableRows
                .map((row) => {
                  const rowKey = coefficientRowKey(row);
                  const isSelected = rowKey === state.diagnosticFilters.selectedCoefficientKey;
                  const deviation = coefficientDeviation(row);
                  return `
                    <tr class="${isSelected ? "is-selected" : ""}">
                      <th>
                        <strong>${escapeHtml(row.coefficient_class || "Coefficient")}</strong>
                        <small>${escapeHtml(coefficientStageLabel(row))}</small>
                      </th>
                      <td>${escapeHtml(row.hs_code || "Unknown")}</td>
                      <td>
                        <span>${escapeHtml(row.producer_scope || "Unknown")}</span>
                        <small>${escapeHtml(row.partner_scope || "Unknown")}</small>
                      </td>
                      <td>
                        <strong>${escapeHtml(formatValue(row.coef_value, "coefficient"))}</strong>
                        <small>${deviation === null ? "" : escapeHtml(formatSignedChange(deviation, "coefficient"))}</small>
                      </td>
                      <td>${escapeHtml(formatValue(row.recommended_value, "coefficient"))}</td>
                      <td>${buildToneBadge(row.bound_status || "Unknown", row.bound_status || "neutral")}</td>
                      <td>${escapeHtml(formatValue(row.exposure, "exposure"))}</td>
                      <td><button type="button" class="row-action${isSelected ? " active" : ""}" data-coefficient-key="${escapeHtml(rowKey)}">View</button></td>
                    </tr>
                  `;
                })
                .join("")}
            </tbody>
          </table>
          ${hiddenCount ? `<div class="explorer-footnote">${escapeHtml(`${hiddenCount} more matching rows are hidden. Refine filters or search to narrow the list.`)}</div>` : ""}
        </div>
        ${buildCoefficientDetailHtml(selectedRow, tradeRows)}
      </div>
    </section>
  `;
}

function tradeStatusTone(status) {
  const normalized = normalizeLabel(status);
  if (normalized === "reduced" || normalized === "removed") {
    return "positive";
  }
  if (normalized === "increased" || normalized === "new") {
    return "negative";
  }
  return "neutral";
}

function filteredTradeRows(rows) {
  const filters = state.diagnosticFilters;
  return (rows || []).filter((row) => {
    const matchesStage = filters.tradeStage === "all" || row.stage_group === filters.tradeStage;
    const matchesStatus = filters.tradeStatus === "all" || row.status === filters.tradeStatus;
    const matchesSearch = rowMatchesSearch(row, filters.tradeSearch, [
      "stage_group",
      "source_stage",
      "target_stage",
      "source_label",
      "target_label",
      "flow_type",
      "status",
    ]);
    return matchesStage && matchesStatus && matchesSearch;
  });
}

function buildTradeFlowExplorerHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">Trade-flow comparison is available when Original and a selected optimization link export are both present.</div>`;
  }

  const selectedResultLabel = resultModeLabel(state.resultMode);
  const visibleRows = filteredTradeRows(rows);
  const stageOptions = optionList(rows, (row) => row.stage_group || "Other", "All stages", ["S1-S2-S3", "S3-S4-S5", "S5-S6-S7", "Other"]);
  const statusOptions = optionList(rows, (row) => row.status || "Unknown", "All statuses", ["Reduced", "Increased", "Removed", "New", "Flat"]);
  const reducedVolume = visibleRows.reduce((sum, row) => sum + Math.max(0, asNumber(row.reduction)), 0);
  const increasedVolume = visibleRows.reduce((sum, row) => sum + Math.max(0, asNumber(row.change)), 0);
  const specialCount = visibleRows.filter((row) => row.flow_type !== "Country flow").length;
  const tableRows = visibleRows.slice(0, 160);
  const hiddenCount = Math.max(0, visibleRows.length - tableRows.length);

  return `
    <section class="explorer-shell trade-flow-explorer">
      <div class="trade-flow-summary">
        ${[
          { label: "Visible Flows", value: visibleRows.length, note: `${rows.length} total flow comparison rows.` },
          { label: "Reduced Volume", value: reducedVolume, note: "Sum of positive Original minus Optimized changes in the active filter." },
          { label: "Increased Volume", value: increasedVolume, note: "Sum of positive Optimized minus Original changes in the active filter." },
          { label: "Unknown / Special Flows", value: specialCount, note: "Rows involving Unknown, Non-source, Non-target, or other special nodes." },
        ]
          .map((item) => buildFactTileHtml(item))
          .join("")}
      </div>
      <div class="explorer-toolbar">
        <label class="explorer-search">
          <span>Find trade flow</span>
          <input id="trade-search" type="search" value="${escapeHtml(state.diagnosticFilters.tradeSearch)}" placeholder="Source, target, stage, status" />
        </label>
        <div class="explorer-filter-stack">
          <div>
            <span>Stage</span>
            ${buildFilterButtons("tradeStage", stageOptions, state.diagnosticFilters.tradeStage)}
          </div>
          <div>
            <span>Status</span>
            ${buildFilterButtons("tradeStatus", statusOptions, state.diagnosticFilters.tradeStatus)}
          </div>
        </div>
      </div>
      <div class="explorer-table-wrap">
        <table class="data-table explorer-table trade-flow-table">
          <thead>
            <tr>
              <th>Stage</th>
              <th>Flow</th>
              <th>Type</th>
              <th>Original</th>
              <th>${escapeHtml(selectedResultLabel)}</th>
              <th>Change</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows
              .map(
                (row) => `
                  <tr>
                    <th>
                      <strong>${escapeHtml(row.stage_group || "Other")}</strong>
                      <small>${escapeHtml(row.source_stage || "?")} -> ${escapeHtml(row.target_stage || "?")}</small>
                    </th>
                    <td>
                      <span>${escapeHtml(row.source_label || "Source")}</span>
                      <small>${escapeHtml(row.target_label || "Target")}</small>
                    </td>
                    <td>${escapeHtml(row.flow_type || "Country flow")}</td>
                    <td>${escapeHtml(formatValue(row.original_value, "value"))}</td>
                    <td>${escapeHtml(formatValue(row.optimized_value, "value"))}</td>
                    <td>${inverseChangeBadgeHtml(row.change)}</td>
                    <td>${buildToneBadge(row.status || "Flat", tradeStatusTone(row.status || "Flat"))}</td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
        ${hiddenCount ? `<div class="explorer-footnote">${escapeHtml(`${hiddenCount} more matching flows are hidden. Refine filters or search to narrow the list.`)}</div>` : ""}
      </div>
    </section>
  `;
}

function vulnerabilityCaseEntries(record) {
  if (!record) {
    return [];
  }
  return [
    {
      key: "proportional",
      label: VULNERABILITY_DASHBOARD_DATA.caseLabels.proportional,
      value: record.proportional ?? record.proportionalMean,
    },
    {
      key: "minimum",
      label: VULNERABILITY_DASHBOARD_DATA.caseLabels.minimum,
      value: record.minimum ?? record.minimumMean,
    },
    {
      key: "maximumKnown",
      label: VULNERABILITY_DASHBOARD_DATA.caseLabels.maximumKnown,
      value: record.maximumKnown ?? record.maximumKnownMean,
    },
    {
      key: "maximumWithUnknown",
      label: VULNERABILITY_DASHBOARD_DATA.caseLabels.maximumWithUnknown,
      value: record.maximumWithUnknown ?? record.maximumWithUnknownMean,
    },
  ];
}

function formatVulnerabilityPercent(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  const numeric = asNumber(value);
  if (!Number.isFinite(numeric)) {
    return "N/A";
  }
  const digits = Math.abs(numeric) < 0.01 && numeric !== 0 ? 2 : 1;
  return `${(numeric * 100).toFixed(digits)}%`;
}

function vulnerabilityPercentWidth(value) {
  if (value === null || value === undefined || value === "") {
    return "0%";
  }
  const numeric = asNumber(value);
  if (!Number.isFinite(numeric)) {
    return "0%";
  }
  return `${Math.min(100, Math.max(0, numeric * 100)).toFixed(1)}%`;
}

function buildVulnerabilityDeltaBadge(value) {
  if (value === null || value === undefined || value === "") {
    return '<span class="delta-badge neutral">-</span>';
  }
  const numeric = asNumber(value);
  const className = numeric < 0 ? "positive" : numeric > 0 ? "negative" : "neutral";
  const prefix = numeric > 0 ? "+" : "";
  return `<span class="delta-badge ${className}">${escapeHtml(`${prefix}${formatVulnerabilityPercent(numeric)}`)}</span>`;
}

function vulnerabilityMetalId() {
  const allowed = (state.metals || []).map((metal) => metal.id || metal).filter(Boolean);
  if (!state.vulnerabilityMetal || (allowed.length && !allowed.includes(state.vulnerabilityMetal))) {
    state.vulnerabilityMetal = allowed.includes(state.metal) ? state.metal : allowed[0] || state.metal;
  }
  return state.vulnerabilityMetal;
}

function vulnerabilityCobaltMode(metal = vulnerabilityMetalId()) {
  return metal === "Co" ? state.cobaltMode : "default";
}

function parseVulnerabilityPair(pair) {
  const [material = "", metal = ""] = String(pair || "").split("-");
  return { material, metal };
}

function vulnerabilityPairForMaterial(material = state.vulnerabilityMaterial, metal = vulnerabilityMetalId()) {
  const cleanMaterial = String(material || "").trim();
  return cleanMaterial && metal ? `${cleanMaterial}-${metal}` : "";
}

function vulnerabilityMaterialSortKey(material) {
  const order = { LFP: 0, NCA: 1, NMC: 2, NCX: 3 };
  return [order[material] ?? 99, material];
}

function sortVulnerabilityMaterials(materials) {
  return Array.from(new Set(materials.filter(Boolean))).sort((a, b) => {
    const left = vulnerabilityMaterialSortKey(a);
    const right = vulnerabilityMaterialSortKey(b);
    return left[0] - right[0] || String(left[1]).localeCompare(String(right[1]));
  });
}

function currentVulnerabilityScopeRows(rows, { includeResult = true } = {}) {
  const metal = vulnerabilityMetalId();
  return (rows || []).filter((row) => {
    const matchesMetal = !row.metal || row.metal === metal;
    const matchesYear = !row.year || Number(row.year) === Number(state.year);
    const matchesResult = !includeResult || !row.resultMode || row.resultMode === state.resultMode;
    const matchesCobalt = metal !== "Co" || !row.coCase || row.coCase === "default" || row.coCase === vulnerabilityCobaltMode(metal);
    return matchesMetal && matchesYear && matchesResult && matchesCobalt;
  });
}

function vulnerabilityCountryOptions() {
  const metal = vulnerabilityMetalId();
  const trendSourceRows = VULNERABILITY_DASHBOARD_DATA.countryPairTrendRows || VULNERABILITY_DASHBOARD_DATA.countryTrendRows || [];
  const scopeRows = trendSourceRows.filter((row) => {
    const matchesMetal = row.metal === metal;
    const matchesCobalt = metal !== "Co" || !row.coCase || row.coCase === "default" || row.coCase === vulnerabilityCobaltMode(metal);
    return matchesMetal && matchesCobalt;
  });
  const countryNames = Array.from(new Set(scopeRows.map((row) => row.country).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  const rankedRows = currentVulnerabilityScopeRows(VULNERABILITY_DASHBOARD_DATA.countryRows);
  const rankedNames = rankedRows.map((row) => row.country).filter(Boolean);
  return Array.from(new Set([...rankedNames, ...countryNames]));
}

function vulnerabilityPairRowsForCountry(country, options = {}) {
  const metal = vulnerabilityMetalId();
  const rows = VULNERABILITY_DASHBOARD_DATA.countryPairTrendRows || [];
  if (!country || !rows.length) {
    return [];
  }
  const requestedYear = options.year === undefined ? null : Number(options.year);
  const requestedResult = options.resultMode || null;
  return rows.filter((row) => {
    const matchesMetal = row.metal === metal;
    const matchesCountry = row.country === country;
    const matchesCobalt = metal !== "Co" || !row.coCase || row.coCase === "default" || row.coCase === vulnerabilityCobaltMode(metal);
    const matchesYear = !Number.isFinite(requestedYear) || Number(row.year) === requestedYear;
    const matchesResult = !requestedResult || row.resultMode === requestedResult;
    return matchesMetal && matchesCountry && matchesCobalt && matchesYear && matchesResult;
  });
}

function vulnerabilityMaterialOptionsForCountry(country, options = {}) {
  const exactRows = vulnerabilityPairRowsForCountry(country, options);
  const fallbackRows = exactRows.length ? exactRows : vulnerabilityPairRowsForCountry(country);
  const materials = fallbackRows
    .map((row) => row.chemistry || parseVulnerabilityPair(row.materialPair).material)
    .filter(Boolean);
  if (materials.includes("NMC") && materials.includes("NCA")) {
    materials.push("NCX");
  }
  return sortVulnerabilityMaterials(materials);
}

function vulnerabilityPairOptionsForCountry(country, options = {}) {
  const metal = vulnerabilityMetalId();
  return vulnerabilityMaterialOptionsForCountry(country, options).map((material) => ({
    chemistry: material,
    pair: vulnerabilityPairForMaterial(material, metal),
    label: material,
  }));
}

function defaultVulnerabilityPairForCountry(country, options = {}) {
  const exactRows = vulnerabilityPairRowsForCountry(country, options);
  const fallbackRows = exactRows.length ? exactRows : vulnerabilityPairRowsForCountry(country);
  if (fallbackRows.length) {
    const bestRow = fallbackRows.reduce((best, row) => {
      const currentValue = asNumber(row.proportional);
      const bestValue = asNumber(best?.proportional);
      return !best || (Number.isFinite(currentValue) && currentValue > bestValue) ? row : best;
    }, null);
    if (bestRow?.materialPair) {
      return bestRow.materialPair;
    }
  }
  return vulnerabilityPairOptionsForCountry(country, options)[0]?.pair || "";
}

function defaultVulnerabilityMaterialForCountry(country, options = {}) {
  return parseVulnerabilityPair(defaultVulnerabilityPairForCountry(country, options)).material
    || vulnerabilityMaterialOptionsForCountry(country, options)[0]
    || "";
}

function vulnerabilityPairOptionsHtml(pairOptions, selectedPair) {
  return pairOptions
    .map((entry) => `<option value="${escapeHtml(entry.pair)}" ${entry.pair === selectedPair ? "selected" : ""}>${escapeHtml(entry.label || entry.pair)}</option>`)
    .join("");
}

function ensureVulnerabilityPairSelections() {
  ensureVulnerabilityResultScopes();
  const profileYear = Number(state.vulnerabilityStageProfileYear || state.year);
  const materialOptions = vulnerabilityMaterialOptionsForCountry(state.vulnerabilityCountry, {
    year: profileYear,
    resultMode: vulnerabilityStageProfileResultMode(),
  });
  if (!materialOptions.includes(state.vulnerabilityMaterial)) {
    state.vulnerabilityMaterial = defaultVulnerabilityMaterialForCountry(state.vulnerabilityCountry, {
      year: profileYear,
      resultMode: state.resultMode,
    });
  }
  state.vulnerabilityStageProfilePair = vulnerabilityPairForMaterial(state.vulnerabilityMaterial);
  state.vulnerabilityTrendCountry = state.vulnerabilityCountry;
  state.vulnerabilityTrendPair = state.vulnerabilityStageProfilePair;
}

function ensureVulnerabilityCountry() {
  const options = vulnerabilityCountryOptions();
  if (!options.includes(state.vulnerabilityCountry)) {
    state.vulnerabilityCountry = options[0] || "";
  }
  state.vulnerabilityTrendCountry = state.vulnerabilityCountry || options[0] || "";
  state.vulnerabilityTrendCompareCountries = state.vulnerabilityTrendCompareCountries
    .filter((country) => options.includes(country) && country !== state.vulnerabilityCountry)
    .slice(0, 3);
  state.vulnerabilityCompareCountries = state.vulnerabilityTrendCompareCountries;
  const activeCountries = new Set([state.vulnerabilityTrendCountry, ...state.vulnerabilityTrendCompareCountries].filter(Boolean));
  Object.keys(state.vulnerabilityCountryVisible).forEach((country) => {
    if (!activeCountries.has(country)) {
      delete state.vulnerabilityCountryVisible[country];
    }
  });
  ensureVulnerabilityPairSelections();
  return options;
}

function currentVulnerabilityRecord() {
  const exact = currentVulnerabilityScopeRows(VULNERABILITY_DASHBOARD_DATA.yearlyMeans)[0];
  if (exact) {
    return exact;
  }
  return VULNERABILITY_DASHBOARD_DATA.scenarioMetrics.find((row) => row.resultMode === state.resultMode)
    || VULNERABILITY_DASHBOARD_DATA.scenarioMetrics[0];
}

function comparisonCountryOptions(options = vulnerabilityCountryOptions()) {
  return options.filter(
    (country) => country !== state.vulnerabilityCountry && !state.vulnerabilityTrendCompareCountries.includes(country),
  );
}

function vulnerabilityTrendCountries() {
  const options = vulnerabilityCountryOptions();
  if (!options.includes(state.vulnerabilityCountry)) {
    state.vulnerabilityCountry = options[0] || "";
  }
  state.vulnerabilityTrendCountry = state.vulnerabilityCountry;
  state.vulnerabilityTrendCompareCountries = state.vulnerabilityTrendCompareCountries
    .filter((country) => options.includes(country) && country !== state.vulnerabilityCountry)
    .slice(0, 3);
  state.vulnerabilityCompareCountries = state.vulnerabilityTrendCompareCountries;
  ensureVulnerabilityPairSelections();
  return [state.vulnerabilityTrendCountry, ...state.vulnerabilityTrendCompareCountries].filter(Boolean);
}

function trendRowsForCountry(country) {
  if (!country) {
    return [];
  }
  const pairRows = VULNERABILITY_DASHBOARD_DATA.countryPairTrendRows || [];
  const dynamicRows = vulnerabilityCountryViDataRows();
  const staticRows = pairRows.length ? pairRows : (VULNERABILITY_DASHBOARD_DATA.countryTrendRows || []);
  const sourceRows = dynamicRows.length
    ? [
        ...dynamicRows,
        ...staticRows.filter((row) => row.country !== state.vulnerabilityCountry),
      ]
    : staticRows;
  const selectedPair = pairRows.length
    ? (state.vulnerabilityStageProfilePair || defaultVulnerabilityPairForCountry(country))
    : "";
  const metal = vulnerabilityMetalId();
  return sourceRows.filter((row) => {
    const matchesMetal = row.metal === metal;
    const matchesCountry = row.country === country;
    const matchesCobalt = metal !== "Co" || !row.coCase || row.coCase === "default" || row.coCase === vulnerabilityCobaltMode(metal);
    const matchesPair = !selectedPair || !row.materialPair || row.materialPair === selectedPair;
    return matchesMetal && matchesCountry && matchesCobalt && matchesPair;
  });
}

function trendRowsForSelectedCountry() {
  return vulnerabilityTrendCountries().flatMap((country) => trendRowsForCountry(country));
}

function vulnerabilityTrendCountryLabel() {
  const countries = vulnerabilityTrendCountries();
  if (!countries.length) {
    return "Focal country";
  }
  return countries.join(", ");
}

function vulnerabilityTrendPairLabel() {
  return state.vulnerabilityStageProfilePair || "All pairs";
}

function buildVulnerabilityScoreCardsHtml(record) {
  const entries = vulnerabilityCaseEntries(record);
  if (!entries.length) {
    return `<div class="order-empty">No vulnerability summary is available for the current selection.</div>`;
  }
  return entries
    .map(
      (entry) => `
        <article class="vulnerability-score-card vulnerability-score-${escapeHtml(entry.key)}">
          <span>${escapeHtml(entry.label)}</span>
          <strong>${escapeHtml(formatVulnerabilityPercent(entry.value))}</strong>
          <div class="vulnerability-mini-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(entry.value))}"></span></div>
        </article>
      `,
    )
    .join("");
}

function buildVulnerabilityCaseComparisonHtml() {
  const rows = currentVulnerabilityScopeRows(VULNERABILITY_DASHBOARD_DATA.yearlyMeans, { includeResult: false });
  const comparisonRows = rows.length ? rows : VULNERABILITY_DASHBOARD_DATA.scenarioMetrics;
  return `
    <div class="vulnerability-case-grid">
      ${comparisonRows
        .map(
          (row) => `
            <article class="vulnerability-case-row ${row.resultMode === state.resultMode ? "active" : ""}">
              <div>
                <strong>${escapeHtml(row.resultMode ? resultModeLabel(row.resultMode) : row.label)}</strong>
                <span>${escapeHtml(row.metal ? `${row.metal} ${row.year}` : "All selected scenarios")}</span>
              </div>
              <div class="vulnerability-case-bars">
                ${vulnerabilityCaseEntries(row)
                  .map(
                    (entry) => `
                      <div class="vulnerability-bar-row">
                        <span>${escapeHtml(entry.label)}</span>
                        <div class="vulnerability-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(entry.value))}"></span></div>
                        <strong>${escapeHtml(formatVulnerabilityPercent(entry.value))}</strong>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function vulnerabilitySeriesVisible(seriesKey) {
  return state.vulnerabilityTrendVisible[seriesKey] !== false;
}

function vulnerabilityCountryVisible(country) {
  return state.vulnerabilityCountryVisible[country] !== false;
}

function visibleVulnerabilityTrendCountries() {
  return vulnerabilityTrendCountries().filter((country) => vulnerabilityCountryVisible(country));
}

function buildVulnerabilityCaseGuideHtml() {
  return VULNERABILITY_CASE_GUIDE.map(
    (caseConfig) => `
      <article class="vulnerability-case-guide-card vulnerability-case-guide-${escapeHtml(caseConfig.key)}">
        <span>${escapeHtml(caseConfig.eyebrow)}</span>
        <strong>${escapeHtml(caseConfig.label)}</strong>
        <p>${escapeHtml(caseConfig.description)}</p>
      </article>
    `,
  ).join("");
}

function buildVulnerabilityTrendLegendHtml() {
  return `
    <div class="vulnerability-trend-legend" aria-label="Result legend">
      ${vulnerabilityResultChoices().map((series) => {
        const isVisible = vulnerabilitySeriesVisible(series.key);
        return `
          <button
            class="vulnerability-legend-item vulnerability-trend-${escapeHtml(series.className)} ${isVisible ? "active" : "is-muted"}"
            type="button"
            data-vulnerability-series="${escapeHtml(series.key)}"
            aria-pressed="${isVisible ? "true" : "false"}"
            style="--series-color: ${escapeHtml(series.color)}"
          >
            <span class="vulnerability-legend-swatch" aria-hidden="true"></span>
            <span>${escapeHtml(series.label)}</span>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function vulnerabilityCountryLineStyleClass(dash) {
  return `vulnerability-country-line-${String(dash || "solid").replace(/[^a-z]/g, "-")}`;
}

function vulnerabilityCountryLineStyleLabel(dash) {
  if (dash === "dash") {
    return "dashed";
  }
  if (dash === "dot") {
    return "dotted";
  }
  if (dash === "dashdot") {
    return "dash-dot";
  }
  return "solid";
}

function buildVulnerabilityCountryLineLegendHtml() {
  const countries = vulnerabilityTrendCountries();
  if (!countries.length) {
    return "";
  }
  return `
    ${countries
      .map((country, index) => {
        const style = VULNERABILITY_COUNTRY_LINE_STYLES[index % VULNERABILITY_COUNTRY_LINE_STYLES.length];
        const styleLabel = vulnerabilityCountryLineStyleLabel(style.dash);
        const isVisible = vulnerabilityCountryVisible(country);
        return `
          <button
            class="vulnerability-legend-item vulnerability-country-line-item ${isVisible ? "active" : "is-muted"}"
            type="button"
            data-vulnerability-country-line="${escapeHtml(country)}"
            aria-pressed="${isVisible ? "true" : "false"}"
          >
            <span class="vulnerability-country-line-swatch ${escapeHtml(vulnerabilityCountryLineStyleClass(style.dash))}" aria-hidden="true"></span>
            <span>${escapeHtml(`${country}${index === 0 ? " (focal)" : ""} - ${styleLabel}`)}</span>
          </button>
        `;
      })
      .join("")}
  `;
}

function buildVulnerabilityCombinedLegendHtml() {
  return `
    <div class="vulnerability-trend-legend-deck">
      <div id="vulnerability-country-line-legend" class="vulnerability-country-line-legend" aria-label="Country line guide">
        ${buildVulnerabilityCountryLineLegendHtml()}
      </div>
      ${buildVulnerabilityTrendLegendHtml()}
    </div>
  `;
}

function renderVulnerabilityCountryLineLegend() {
  const host = document.getElementById("vulnerability-country-line-legend");
  if (host) {
    host.innerHTML = buildVulnerabilityCountryLineLegendHtml();
  }
}

function bindVulnerabilityCountryLineLegendControls() {
  document.querySelectorAll("[data-vulnerability-country-line]").forEach((button) => {
    button.onclick = () => {
      const country = button.dataset.vulnerabilityCountryLine;
      if (!country) {
        return;
      }
      state.vulnerabilityCountryVisible[country] = !vulnerabilityCountryVisible(country);
      renderVulnerabilityCountryLineLegend();
      bindVulnerabilityCountryLineLegendControls();
      scheduleVulnerabilityTrendPlots();
    };
  });
}

function vulnerabilityTrendYears(rows) {
  return Array.from(new Set(rows.map((row) => Number(row.year)).filter(Number.isFinite))).sort((a, b) => a - b);
}

function vulnerabilityTrendPercent(row, caseKey) {
  if (!row || row[caseKey] === null || row[caseKey] === undefined) {
    return null;
  }
  const numeric = asNumber(row[caseKey]);
  return Number.isFinite(numeric) ? numeric * 100 : null;
}

function vulnerabilityProfileYears() {
  const fromState = (state.years || []).map((year) => Number(year)).filter(Number.isFinite);
  if (fromState.length) {
    return Array.from(new Set(fromState)).sort((a, b) => a - b);
  }
  const rows = trendRowsForSelectedCountry();
  return vulnerabilityTrendYears(rows);
}

function ensureVulnerabilityStageProfileYear() {
  const years = vulnerabilityProfileYears();
  const current = Number(state.vulnerabilityStageProfileYear);
  if (years.includes(current)) {
    return current;
  }
  const navYear = Number(state.year);
  state.vulnerabilityStageProfileYear = years.includes(navYear) ? navYear : years[0] || navYear;
  return Number(state.vulnerabilityStageProfileYear);
}

function buildVulnerabilityStageYearOptionsHtml(selectedYear) {
  return vulnerabilityProfileYears()
    .map((year) => `<option value="${escapeHtml(String(year))}" ${Number(year) === Number(selectedYear) ? "selected" : ""}>${escapeHtml(String(year))}</option>`)
    .join("");
}

function buildVulnerabilityCountryOptionsHtml(selectedCountry) {
  return vulnerabilityCountryOptions()
    .map((country) => `<option value="${escapeHtml(country)}" ${country === selectedCountry ? "selected" : ""}>${escapeHtml(country)}</option>`)
    .join("");
}

function buildVulnerabilityMetalOptionsHtml(selectedMetal = vulnerabilityMetalId()) {
  return (state.metals || [])
    .map((metal) => {
      const value = metal.id || metal;
      const label = metal.label || value;
      return `<option value="${escapeHtml(value)}" ${value === selectedMetal ? "selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function buildVulnerabilityMaterialOptionsHtml(materialOptions, selectedMaterial = state.vulnerabilityMaterial) {
  return materialOptions
    .map((material) => `<option value="${escapeHtml(material)}" ${material === selectedMaterial ? "selected" : ""}>${escapeHtml(material)}</option>`)
    .join("");
}

function vulnerabilityCountryViKey() {
  ensureVulnerabilityPairSelections();
  const countries = [state.vulnerabilityCountry, ...state.vulnerabilityTrendCompareCountries]
    .filter(Boolean);
  return [
    vulnerabilityMetalId(),
    vulnerabilityCobaltMode(),
    countries.join(","),
    state.vulnerabilityStageProfilePair || "",
  ].join("|");
}

function vulnerabilityCountryViDataRows() {
  if (state.vulnerabilityCountryVi.key !== vulnerabilityCountryViKey()) {
    return [];
  }
  const payload = state.vulnerabilityCountryVi.data;
  return payload?.rows || [];
}

function selectedVulnerabilityCountryPairRows() {
  ensureVulnerabilityPairSelections();
  const dynamicRows = vulnerabilityCountryViDataRows();
  const rows = dynamicRows.length ? dynamicRows : (VULNERABILITY_DASHBOARD_DATA.countryPairTrendRows || []);
  const selectedYear = ensureVulnerabilityStageProfileYear();
  const selectedPair = state.vulnerabilityStageProfilePair;
  const metal = vulnerabilityMetalId();
  return rows.filter((row) => {
    const matchesMetal = row.metal === metal;
    const matchesCountry = row.country === state.vulnerabilityCountry;
    const matchesPair = !selectedPair || row.materialPair === selectedPair;
    const matchesYear = Number(row.year) === Number(selectedYear);
    const matchesCobalt = metal !== "Co" || !row.coCase || row.coCase === "default" || row.coCase === vulnerabilityCobaltMode(metal);
    return matchesMetal && matchesCountry && matchesPair && matchesYear && matchesCobalt;
  });
}

function buildVulnerabilityCountryViControlsHtml() {
  const selectedYear = ensureVulnerabilityStageProfileYear();
  const materialOptions = vulnerabilityMaterialOptionsForCountry(state.vulnerabilityCountry, {
    year: selectedYear,
    resultMode: vulnerabilityStageProfileResultMode(),
  });
  return `
    <div class="vulnerability-country-vi-controls" aria-label="Country VI scope controls">
      <label class="vulnerability-country-picker" for="vulnerability-country-vi-country-select">
        <span>Target country</span>
        <select id="vulnerability-country-vi-country-select" class="text-input">
          ${buildVulnerabilityCountryOptionsHtml(state.vulnerabilityCountry)}
        </select>
      </label>
      <label class="vulnerability-country-picker" for="vulnerability-country-vi-metal-select">
        <span>VI metal</span>
        <select id="vulnerability-country-vi-metal-select" class="text-input">
          ${buildVulnerabilityMetalOptionsHtml(vulnerabilityMetalId())}
        </select>
      </label>
      <label class="vulnerability-country-picker" for="vulnerability-country-vi-material-select">
        <span>Material type</span>
        <select id="vulnerability-country-vi-material-select" class="text-input" ${materialOptions.length ? "" : "disabled"}>
          ${buildVulnerabilityMaterialOptionsHtml(materialOptions, state.vulnerabilityMaterial)}
        </select>
      </label>
      <label class="vulnerability-country-picker" for="vulnerability-country-vi-year-select">
        <span>Profile year</span>
        <select id="vulnerability-country-vi-year-select" class="text-input">
          ${buildVulnerabilityStageYearOptionsHtml(selectedYear)}
        </select>
      </label>
    </div>
  `;
}

/**
 * Render the compact Country VI comparison table for the currently selected
 * target country, VI metal, material type, and year. Each row is an absolute
 * VI value for one Conversion Factor Optimization result, split by the four
 * graph-based VI treatments: Base VI, Minimum, Maximum A, and Maximum B.
 *
 * This table intentionally avoids Base-vs-Original deltas. Those comparisons
 * are easier to interpret in the Stage Exposure Profile and Time Trend panels,
 * where users can see how the same country/material scope changes visually.
 */
function buildVulnerabilityCountryResultComparisonHtml() {
  if (state.vulnerabilityCountryVi.loading) {
    return `<div class="order-empty">Loading exact Country VI rows for the selected metal and material...</div>`;
  }
  if (state.vulnerabilityCountryVi.error) {
    return `<div class="order-empty">${escapeHtml(state.vulnerabilityCountryVi.error)}</div>`;
  }
  const rows = selectedVulnerabilityCountryPairRows();
  if (!rows.length) {
    return `<div class="order-empty">No result comparison is available for the selected Country VI scope.</div>`;
  }
  // Keep this table to the exact VI method values only. Delta-to-Original
  // comparisons are intentionally omitted here because users compare result
  // modes visually in the stage profile and time-trend panels below.
  const byResult = new Map(rows.map((row) => [row.resultMode, row]));
  return `
    <section class="vulnerability-country-result-comparison" aria-label="Country VI result comparison">
      <div class="vulnerability-country-result-head">
        <div>
          <strong>Result Comparison</strong>
          <span>${escapeHtml(`${state.vulnerabilityCountry} | ${state.vulnerabilityStageProfilePair} | ${ensureVulnerabilityStageProfileYear()}`)}</span>
        </div>
      </div>
      <div class="table-scroll">
        <table class="data-table vulnerability-table vulnerability-country-result-table">
          <thead>
            <tr>
              <th>Result</th>
              <th>Base VI</th>
              <th>Minimum</th>
              <th>Maximum A</th>
              <th>Maximum B</th>
            </tr>
          </thead>
          <tbody>
            ${vulnerabilityResultChoices()
              .map((series) => {
                const row = byResult.get(series.key);
                return `
                  <tr class="${series.key === state.resultMode ? "is-active" : ""}">
                    <th>${escapeHtml(resultModeLabel(series.key))}</th>
                    <td>${escapeHtml(formatVulnerabilityPercent(row?.proportional))}</td>
                    <td>${escapeHtml(formatVulnerabilityPercent(row?.minimum))}</td>
                    <td>${escapeHtml(formatVulnerabilityPercent(row?.maximumKnown))}</td>
                    <td>${escapeHtml(formatVulnerabilityPercent(row?.maximumWithUnknown))}</td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function buildPlotDownloadButtonHtml(plotId, label, filename) {
  return `
    <button
      class="ghost-btn plot-download-btn"
      type="button"
      data-download-plot="${escapeHtml(plotId)}"
      data-download-filename="${escapeHtml(filename)}"
      aria-label="${escapeHtml(`Download ${label}`)}"
    >
      Download PNG
    </button>
  `;
}

function buildVulnerabilityTrendChartShellHtml(caseConfig) {
  const plotId = `vulnerability-plot-${caseConfig.key}`;
  const pairLabel = vulnerabilityTrendPairLabel();
  return `
    <article class="vulnerability-trend-chart" data-vulnerability-case="${escapeHtml(caseConfig.key)}">
      <div class="vulnerability-trend-head">
        <div>
          <strong>${escapeHtml(caseConfig.label)}</strong>
          <span>${escapeHtml(`${vulnerabilityTrendCountryLabel()} | ${pairLabel}`)}</span>
        </div>
        ${buildPlotDownloadButtonHtml(plotId, `${caseConfig.label} trend`, `country-vi-${vulnerabilityMetalId()}-${caseConfig.key}-trend`)}
      </div>
      <div
        id="${escapeHtml(plotId)}"
        class="vulnerability-plot-host"
        role="img"
        aria-label="${escapeHtml(`${caseConfig.label} trend for ${vulnerabilityTrendCountryLabel()}`)}"
      ></div>
    </article>
  `;
}

function vulnerabilityStageProfileKey() {
  const profileYear = ensureVulnerabilityStageProfileYear();
  ensureVulnerabilityPairSelections();
  const metal = vulnerabilityMetalId();
  const resultMode = vulnerabilityStageProfileResultMode();
  return [
    metal,
    profileYear,
    resultMode,
    vulnerabilityCobaltMode(metal),
    state.vulnerabilityCountry || "",
    state.vulnerabilityStageProfilePair || "",
  ].join("|");
}

function vulnerabilityStageProfileRequest() {
  ensureVulnerabilityPairSelections();
  const metal = vulnerabilityMetalId();
  return {
    metal,
    year: ensureVulnerabilityStageProfileYear(),
    resultMode: vulnerabilityStageProfileResultMode(),
    cobaltMode: state.cobaltMode,
    country: state.vulnerabilityCountry,
    pair: state.vulnerabilityStageProfilePair,
  };
}

function vulnerabilityStageProfileLegendSegments(profile) {
  const byId = new Map();
  Object.values(profile?.composition || {}).forEach((segments) => {
    (segments || []).forEach((segment) => {
      if (!segment?.id || segment.id === "__other__") {
        return;
      }
      if (!byId.has(segment.id)) {
        byId.set(segment.id, segment);
      }
    });
  });
  return Array.from(byId.values()).sort((a, b) => {
    if (a.id === profile?.countryId) return -1;
    if (b.id === profile?.countryId) return 1;
    return String(a.label).localeCompare(String(b.label));
  });
}

function buildVulnerabilityStageProfileLegendHtml(profile) {
  const segments = vulnerabilityStageProfileLegendSegments(profile);
  if (!segments.length) {
    return "";
  }
  return `
    <div class="vulnerability-stage-country-legend" aria-label="Stage profile country labels">
      <span>Displayed countries</span>
      ${segments
        .map((segment) => `
          <span class="vulnerability-stage-country-chip" style="--profile-color: ${escapeHtml(segment.color)}">
            <i aria-hidden="true"></i>
            <strong>${escapeHtml(segment.abbr)}</strong>
            <span>${escapeHtml(segment.label)}</span>
          </span>
        `)
        .join("")}
    </div>
  `;
}

function buildVulnerabilityStageProfileControlsHtml() {
  const selectedResult = vulnerabilityStageProfileResultMode();
  return `
    <div class="vulnerability-stage-profile-actions">
      <label class="vulnerability-country-picker vulnerability-country-picker-compact" for="vulnerability-stage-profile-result-select">
        <span>Conversion Factor Optimization</span>
        <select id="vulnerability-stage-profile-result-select" class="text-input">
          ${buildVulnerabilityResultOptionsHtml(selectedResult)}
        </select>
      </label>
      ${buildPlotDownloadButtonHtml("vulnerability-stage-profile-plot", "stage exposure profile", `stage-exposure-${vulnerabilityMetalId()}-${state.vulnerabilityCountry || "country"}`)}
    </div>
  `;
}

function buildVulnerabilityStageProfileHtml() {
  const profile = state.vulnerabilityStageProfile;
  const selectedYear = ensureVulnerabilityStageProfileYear();
  if (profile.loading) {
    return `
      <section class="vulnerability-stage-profile">
        <div class="vulnerability-stage-profile-head">
          <div>
            <strong>Stage Exposure Profile</strong>
            <span>Loading the selected focal-country profile...</span>
          </div>
        </div>
        <div class="order-empty">Preparing interactive stacked bars.</div>
      </section>
    `;
  }
  if (profile.error) {
    return `
      <section class="vulnerability-stage-profile">
        <div class="vulnerability-stage-profile-head">
          <div>
            <strong>Stage Exposure Profile</strong>
            <span>${escapeHtml(profile.error)}</span>
          </div>
        </div>
        <div class="order-empty">No stage profile is available for the current selection.</div>
      </section>
    `;
  }
  if (!profile.data) {
    return `
      <section class="vulnerability-stage-profile">
        <div class="vulnerability-stage-profile-head">
          <div>
            <strong>Stage Exposure Profile</strong>
            <span>Choose a focal country to inspect its stage-level contribution profile.</span>
          </div>
        </div>
      </section>
    `;
  }
  return `
    <section class="vulnerability-stage-profile">
      <div class="vulnerability-stage-profile-head">
        <div>
          <strong>Stage Exposure Profile</strong>
          <span>${escapeHtml(`${profile.data.country} | ${profile.data.pair} | ${profile.data.year} | ${resultModeLabel(profile.data.resultMode)}`)}</span>
        </div>
        ${buildVulnerabilityStageProfileControlsHtml()}
      </div>
      ${buildVulnerabilityStageProfileLegendHtml(profile.data)}
      <div id="vulnerability-stage-profile-plot" class="vulnerability-stage-profile-plot" role="img" aria-label="Stage exposure profile"></div>
    </section>
  `;
}

function renderVulnerabilityStageProfile() {
  const host = document.getElementById("vulnerability-stage-profile");
  if (!host) {
    return;
  }
  host.innerHTML = buildVulnerabilityStageProfileHtml();
  bindVulnerabilityStageProfileControls();
  bindPlotDownloadControls();
  scheduleVulnerabilityStageProfilePlot();
}

function bindVulnerabilityStageProfileControls() {
  const countrySelect = document.getElementById("vulnerability-country-select");
  if (countrySelect) {
    countrySelect.onchange = () => {
      const previousCountry = state.vulnerabilityCountry;
      state.vulnerabilityCountry = countrySelect.value;
      state.vulnerabilityStageProfilePair = "";
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      if (!state.vulnerabilitySensitivity.draftCountry || state.vulnerabilitySensitivity.draftCountry === previousCountry) {
        state.vulnerabilitySensitivity.draftCountry = state.vulnerabilityCountry;
        state.vulnerabilitySensitivity.draftScenarioProduction = "";
        state.vulnerabilitySensitivity.result = null;
      }
      renderVulnerabilityDashboard();
    };
  }
  const pairSelect = document.getElementById("vulnerability-stage-profile-pair-select");
  if (pairSelect) {
    pairSelect.onchange = () => {
      state.vulnerabilityStageProfilePair = pairSelect.value;
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      if (!state.vulnerabilitySensitivity.selectedPair) {
        state.vulnerabilitySensitivity.selectedPair = state.vulnerabilityStageProfilePair;
      }
      renderVulnerabilityStageProfile();
      loadVulnerabilityStageProfile();
    };
  }
  const resultSelect = document.getElementById("vulnerability-stage-profile-result-select");
  if (resultSelect) {
    resultSelect.onchange = () => {
      state.vulnerabilityStageProfileResultMode = resultSelect.value;
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      renderVulnerabilityStageProfile();
      loadVulnerabilityStageProfile();
    };
  }
  const yearSelect = document.getElementById("vulnerability-stage-profile-year-select");
  if (yearSelect) {
    yearSelect.onchange = () => {
      const nextYear = Number(yearSelect.value);
      if (!Number.isFinite(nextYear) || Number(nextYear) === Number(state.vulnerabilityStageProfileYear)) {
        return;
      }
      state.vulnerabilityStageProfileYear = nextYear;
      state.vulnerabilityStageProfilePair = "";
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      renderVulnerabilityStageProfile();
      loadVulnerabilityStageProfile();
    };
  }
}

async function loadVulnerabilityStageProfile() {
  const profile = state.vulnerabilityStageProfile;
  const key = vulnerabilityStageProfileKey();
  if (!state.vulnerabilityCountry || profile.loading || (profile.key === key && (profile.data || profile.error))) {
    return;
  }
  profile.key = key;
  profile.loading = true;
  profile.error = "";
  profile.data = null;
  renderVulnerabilityStageProfile();
  try {
    profile.data = await apiClient.requestVulnerabilityStageProfile(vulnerabilityStageProfileRequest());
  } catch (error) {
    profile.error = error?.message || "Stage profile request failed.";
  } finally {
    profile.loading = false;
    renderVulnerabilityStageProfile();
  }
}

function buildVulnerabilityTrendControlsHtml() {
  ensureVulnerabilityPairSelections();
  const compareOptions = comparisonCountryOptions();
  return `
    <div class="vulnerability-trend-section-head">
      <div class="vulnerability-trend-title">
        <strong>Time Trend</strong>
        <span>Compare all Conversion Factor Optimization results by year for the shared Country VI scope.</span>
      </div>
      <div class="vulnerability-country-tools vulnerability-trend-country-tools">
        <div class="vulnerability-compare-controls">
          <label class="vulnerability-country-picker vulnerability-compare-picker" for="vulnerability-trend-compare-country-select">
            <span>Add comparison</span>
            <select id="vulnerability-trend-compare-country-select" class="text-input" ${compareOptions.length ? "" : "disabled"}>
              ${compareOptions.map((country) => `<option value="${escapeHtml(country)}">${escapeHtml(country)}</option>`).join("")}
            </select>
          </label>
          <button id="vulnerability-trend-add-country-btn" class="ghost-btn" type="button" ${compareOptions.length && state.vulnerabilityTrendCompareCountries.length < 3 ? "" : "disabled"}>Add</button>
        </div>
        <div id="vulnerability-country-chips" class="vulnerability-country-chips" aria-label="Compared countries">
          ${buildVulnerabilityCountryChipsHtml()}
        </div>
      </div>
    </div>
  `;
}

function buildVulnerabilityCountryTrendHtml() {
  return `
    <div class="vulnerability-country-vi-shell">
      ${buildVulnerabilityCountryViControlsHtml()}
      ${buildVulnerabilityCountryResultComparisonHtml()}
      <div id="vulnerability-stage-profile" class="vulnerability-country-vi-panel">
        ${buildVulnerabilityStageProfileHtml()}
      </div>
      ${buildVulnerabilityTimeTrendPanelHtml()}
    </div>
  `;
}

function buildVulnerabilityTimeTrendPanelHtml() {
  const rows = trendRowsForSelectedCountry();
  const stateMessage = state.vulnerabilityCountryVi.loading
    ? `<div class="order-empty">Loading exact Country VI rows...</div>`
    : state.vulnerabilityCountryVi.error
      ? `<div class="order-empty">${escapeHtml(state.vulnerabilityCountryVi.error)}</div>`
      : !rows.length
        ? `<div class="order-empty">No country trend data are available for the current metal, material, and country selection.</div>`
        : "";
  return `
    <section id="vulnerability-time-trend-panel" class="vulnerability-country-vi-panel vulnerability-trend-panel">
      ${buildVulnerabilityTrendControlsHtml()}
      ${buildVulnerabilityCombinedLegendHtml()}
      ${stateMessage || `
        <div class="vulnerability-trend-grid">
          ${VULNERABILITY_TREND_CASES.map((caseConfig) => buildVulnerabilityTrendChartShellHtml(caseConfig)).join("")}
        </div>
      `}
    </section>
  `;
}

function buildVulnerabilityTrendPlotData(caseConfig, rows, years, countries) {
  const visibleCountries = countries.filter((country) => vulnerabilityCountryVisible(country));
  const highlightedYear = Number(state.vulnerabilityStageProfileYear || state.year);
  return visibleCountries.flatMap((country) => {
    const countryIndex = countries.indexOf(country);
    const lineStyle = VULNERABILITY_COUNTRY_LINE_STYLES[countryIndex % VULNERABILITY_COUNTRY_LINE_STYLES.length];
    const resultChoices = vulnerabilityResultChoices();
    return resultChoices.map((series, seriesIndex) => ({
      type: "scatter",
      mode: "lines+markers",
      name: countries.length > 1 ? `${series.label} - ${country}` : series.label,
      x: years,
      y: years.map((year) => {
        const row = rows.find(
          (item) => item.country === country && Number(item.year) === Number(year) && item.resultMode === series.key,
        );
        return vulnerabilityTrendPercent(row, caseConfig.key);
      }),
      visible: vulnerabilitySeriesVisible(series.key),
      connectgaps: false,
      opacity: countryIndex === 0 ? 1 : 0.72,
      line: {
        color: series.color,
        // The four optimization results can be numerically very close. Tapering
        // widths by result lets lower traces remain visible as a subtle edge
        // instead of being fully covered by the last drawn line.
        width: Math.max(1.4, (countryIndex === 0 ? 3.6 : 2.8) - seriesIndex * 0.42),
        shape: "linear",
        dash: lineStyle.dash,
      },
      marker: {
        color: series.color,
        symbol: series.symbol,
        size: years.map((year) => (Number(year) === highlightedYear ? (countryIndex === 0 ? 10 : 8) : 6.5)),
        line: {
          color: "rgba(255, 253, 248, 0.96)",
          width: 1.4,
        },
      },
      hovertemplate: `${escapeHtml(country)}<br>${escapeHtml(series.label)}<br>${escapeHtml(caseConfig.label)}: %{y:.1f}%<extra></extra>`,
    }));
  });
}

function stageProfilePositions(profile) {
  const visibleStages = (profile?.stages || ["Mining", "Processing", "Refining", "Cathode", "Total"]);
  const cases = profile?.cases || [];
  const positions = [];
  cases.forEach((caseEntry, caseIndex) => {
    visibleStages.forEach((stage, stageIndex) => {
      positions.push({
        caseKey: caseEntry.key,
        caseLabel: caseEntry.label,
        stage,
        x: caseIndex * 6 + (stage === "Total" ? 4.65 : stageIndex),
      });
    });
  });
  return positions;
}

function buildVulnerabilityStageProfilePlotData(profile) {
  if (!profile?.cases?.length) {
    return [];
  }
  const tracesBySegment = new Map();
  const stageList = (profile.stages || []).filter((stage) => stage !== "Total");
  const ensureTrace = (segment) => {
    if (!tracesBySegment.has(segment.id)) {
      tracesBySegment.set(segment.id, {
        type: "bar",
        name: segment.label,
        x: [],
        y: [],
        base: [],
        width: [],
        text: [],
        customdata: [],
        marker: {
          color: segment.color,
          line: { color: "rgba(42, 34, 28, 0.42)", width: 0.6 },
        },
        hovertemplate:
          "%{customdata[0]}<br>%{customdata[1]}<br>%{customdata[2]} displayed: %{y:.1f}%<br>Computed path share: %{customdata[3]:.1f}%<extra></extra>",
      });
    }
    return tracesBySegment.get(segment.id);
  };

  profile.cases.forEach((caseEntry, caseIndex) => {
    stageList.forEach((stage, stageIndex) => {
      const x = caseIndex * 6 + stageIndex;
      let bottom = 0;
      (profile.composition?.[stage] || []).forEach((segment) => {
        const rawRatio = Number(segment.ratio) * 100;
        if (!Number.isFinite(rawRatio) || rawRatio <= 0 || bottom >= 100) {
          return;
        }
        const ratio = Math.max(0, Math.min(rawRatio, 100 - bottom));
        if (ratio <= 0) {
          return;
        }
        const trace = ensureTrace(segment);
        trace.x.push(x);
        trace.y.push(ratio);
        trace.base.push(bottom);
        trace.width.push(0.56);
        trace.text.push(ratio >= 6 || segment.id === profile.countryId ? segment.abbr : "");
        trace.customdata.push([caseEntry.label, stage, segment.label, rawRatio]);
        bottom += ratio;
      });
    });
  });

  const focalTrace = {
    type: "bar",
    name: `Supply involving ${profile.countryAbbr || profile.country}`,
    x: [],
    y: [],
    base: [],
    width: [],
    text: [],
    customdata: [],
    marker: {
      color: "rgba(209, 47, 40, 0.32)",
      line: { color: "rgba(209, 47, 40, 0.82)", width: 1.1 },
    },
    hovertemplate: "%{customdata[0]}<br>%{customdata[1]} exposure: %{y:.1f}%<extra></extra>",
  };
  profile.cases.forEach((caseEntry, caseIndex) => {
    (profile.stages || []).forEach((stage, stageIndex) => {
      const x = caseIndex * 6 + (stage === "Total" ? 4.65 : stageIndex);
      const value = Number(caseEntry.stageRatios?.[stage]) * 100;
      if (!Number.isFinite(value)) {
        return;
      }
      focalTrace.x.push(x);
      focalTrace.y.push(value);
      focalTrace.base.push(0);
      focalTrace.width.push(stage === "Total" ? 0.7 : 0.7);
      focalTrace.text.push(value >= 12 || stage === "Total" ? `${value.toFixed(0)}%` : "");
      focalTrace.customdata.push([caseEntry.label, stage]);
    });
  });

  const traces = Array.from(tracesBySegment.values()).map((trace) => ({
    ...trace,
    textposition: "inside",
    insidetextfont: { color: "rgba(32, 25, 21, 0.88)", size: 10 },
    cliponaxis: false,
  }));
  traces.push({
    ...focalTrace,
    textposition: "inside",
    insidetextfont: { color: "#7e241f", size: 10 },
    cliponaxis: false,
  });
  return traces;
}

function buildVulnerabilityStageProfileLayout(profile, options = {}) {
  const positions = stageProfilePositions(profile);
  const caseAnnotations = (profile?.cases || []).map((caseEntry, index) => ({
    x: index * 6 + 2.05,
    y: 1.16,
    xref: "x",
    yref: "paper",
    text: `<b>${escapeHtml(caseEntry.label)}</b>`,
    showarrow: false,
    font: { size: 12, color: "#2a211c" },
  }));
  const separators = (profile?.cases || []).slice(0, -1).map((_caseEntry, index) => ({
    type: "line",
    x0: index * 6 + 5.38,
    x1: index * 6 + 5.38,
    y0: 0,
    y1: 100,
    xref: "x",
    yref: "y",
    line: { color: "rgba(42, 34, 28, 0.32)", width: 1, dash: "dash" },
  }));
  return {
    autosize: true,
    height: options.height || 336,
    margin: { l: 42, r: 12, t: 56, b: 48 },
    paper_bgcolor: "rgba(0, 0, 0, 0)",
    plot_bgcolor: "rgba(0, 0, 0, 0)",
    barmode: "overlay",
    bargap: 0.16,
    hovermode: "closest",
    dragmode: false,
    showlegend: false,
    font: {
      family: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      color: "#6d6256",
      size: 11,
    },
    xaxis: {
      tickmode: "array",
      tickvals: positions.map((item) => item.x),
      ticktext: positions.map((item) => item.stage),
      tickangle: -28,
      showgrid: false,
      zeroline: false,
      fixedrange: true,
      linecolor: "rgba(128, 111, 93, 0.28)",
      linewidth: 1,
    },
    yaxis: {
      range: [0, 105],
      tickmode: "array",
      tickvals: [0, 50, 100],
      ticksuffix: "%",
      gridcolor: "rgba(128, 111, 93, 0.18)",
      zeroline: false,
      fixedrange: true,
    },
    shapes: separators,
    annotations: caseAnnotations,
  };
}

function renderVulnerabilityStageProfilePlot() {
  const profile = state.vulnerabilityStageProfile.data;
  const host = document.getElementById("vulnerability-stage-profile-plot");
  if (!host || host.offsetParent === null || typeof Plotly === "undefined" || !profile) {
    return;
  }
  Plotly.react(
    host,
    buildVulnerabilityStageProfilePlotData(profile),
    buildVulnerabilityStageProfileLayout(profile),
    { ...PLOTLY_CONFIG, displayModeBar: false },
  );
}

function scheduleVulnerabilityStageProfilePlot() {
  if (vulnerabilityStageProfilePlotFrame) {
    window.cancelAnimationFrame(vulnerabilityStageProfilePlotFrame);
  }
  vulnerabilityStageProfilePlotFrame = window.requestAnimationFrame(() => {
    vulnerabilityStageProfilePlotFrame = window.requestAnimationFrame(() => {
      vulnerabilityStageProfilePlotFrame = 0;
      renderVulnerabilityStageProfilePlot();
    });
  });
}

function buildSensitivityStageProfileHtml(countryResult) {
  const profile = countryResult?.stageProfile;
  if (!profile) {
    return "";
  }
  return `
    <section class="vulnerability-stage-profile vulnerability-sensitivity-stage-profile">
      <div class="vulnerability-stage-profile-head">
        <div>
          <strong>Recalculated Stage Exposure Profile</strong>
          <span>${escapeHtml(`${profile.country} | ${profile.pair} | ${profile.year} | ${resultModeLabel(profile.resultMode)}`)}</span>
        </div>
        <div class="vulnerability-stage-profile-actions">
          <span class="vulnerability-stage-profile-note">Scenario graph after the active production edits.</span>
          ${buildPlotDownloadButtonHtml("vulnerability-sensitivity-stage-profile-plot", "recalculated stage exposure profile", `recalculated-stage-exposure-${profile.metal || sensitivityMetalId()}-${profile.country || "country"}`)}
        </div>
      </div>
      ${buildVulnerabilityStageProfileLegendHtml(profile)}
      <div id="vulnerability-sensitivity-stage-profile-plot" class="vulnerability-stage-profile-plot" role="img" aria-label="Recalculated stage exposure profile"></div>
    </section>
  `;
}

function renderVulnerabilitySensitivityStageProfilePlot() {
  const result = state.vulnerabilitySensitivity.result;
  const countryResult = sensitivityResultCountry(result);
  const profile = countryResult?.stageProfile;
  const host = document.getElementById("vulnerability-sensitivity-stage-profile-plot");
  if (!host || host.offsetParent === null || typeof Plotly === "undefined" || !profile) {
    return;
  }
  Plotly.react(
    host,
    buildVulnerabilityStageProfilePlotData(profile),
    buildVulnerabilityStageProfileLayout(profile, { height: 300 }),
    { ...PLOTLY_CONFIG, displayModeBar: false },
  );
}

function scheduleVulnerabilitySensitivityStageProfilePlot() {
  if (vulnerabilitySensitivityStageProfilePlotFrame) {
    window.cancelAnimationFrame(vulnerabilitySensitivityStageProfilePlotFrame);
  }
  vulnerabilitySensitivityStageProfilePlotFrame = window.requestAnimationFrame(() => {
    vulnerabilitySensitivityStageProfilePlotFrame = window.requestAnimationFrame(() => {
      vulnerabilitySensitivityStageProfilePlotFrame = 0;
      renderVulnerabilitySensitivityStageProfilePlot();
    });
  });
}

function plotDownloadFilename(rawName) {
  return String(rawName || "plot")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "plot";
}

async function downloadPlotImage(plotId, filename) {
  const host = document.getElementById(plotId);
  if (!host || typeof Plotly === "undefined") {
    return;
  }
  const width = Math.max(900, Math.round(host.getBoundingClientRect().width || host.offsetWidth || 900));
  const height = Math.max(520, Math.round(host.getBoundingClientRect().height || host.offsetHeight || 520));
  await Plotly.downloadImage(host, {
    format: "png",
    filename: plotDownloadFilename(filename),
    width,
    height,
    scale: 2,
  });
}

function bindPlotDownloadControls() {
  document.querySelectorAll("[data-download-plot]").forEach((button) => {
    button.onclick = () => {
      const plotId = button.dataset.downloadPlot;
      const filename = button.dataset.downloadFilename || plotId;
      downloadPlotImage(plotId, filename);
    };
  });
}

function buildVulnerabilityTrendLayout(caseConfig, years) {
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  return {
    autosize: true,
    height: 236,
    margin: { l: 42, r: 14, t: 6, b: 34 },
    paper_bgcolor: "rgba(0, 0, 0, 0)",
    plot_bgcolor: "rgba(0, 0, 0, 0)",
    showlegend: false,
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "rgba(255, 253, 248, 0.98)",
      bordercolor: "rgba(128, 111, 93, 0.22)",
      font: { color: "#2f2721", size: 12 },
    },
    dragmode: false,
    font: {
      family: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      color: "#6d6256",
      size: 12,
    },
    xaxis: {
      range: [minYear - 0.15, maxYear + 0.15],
      tickmode: "array",
      tickvals: years,
      tickfont: { color: "#5e5247", size: 12 },
      showgrid: false,
      zeroline: false,
      fixedrange: true,
      linecolor: "rgba(128, 111, 93, 0.3)",
      linewidth: 1,
    },
    yaxis: {
      range: [0, 100],
      tickmode: "array",
      tickvals: [0, 50, 100],
      ticksuffix: "%",
      tickfont: { color: "#6d6256", size: 12 },
      gridcolor: "rgba(128, 111, 93, 0.18)",
      zeroline: false,
      fixedrange: true,
    },
    meta: { caseKey: caseConfig.key },
  };
}

function renderVulnerabilityTrendPlots() {
  const trendHost = document.getElementById("vulnerability-trend-charts");
  if (!trendHost || trendHost.offsetParent === null || typeof Plotly === "undefined") {
    return;
  }
  const rows = trendRowsForSelectedCountry();
  const years = vulnerabilityTrendYears(rows);
  const countries = vulnerabilityTrendCountries();
  if (!rows.length || !years.length) {
    return;
  }
  VULNERABILITY_TREND_CASES.forEach((caseConfig) => {
    const plotHost = document.getElementById(`vulnerability-plot-${caseConfig.key}`);
    if (!plotHost) {
      return;
    }
    Plotly.react(
      plotHost,
      buildVulnerabilityTrendPlotData(caseConfig, rows, years, countries),
      buildVulnerabilityTrendLayout(caseConfig, years),
      { ...PLOTLY_CONFIG, displayModeBar: false },
    );
  });
}

function scheduleVulnerabilityTrendPlots() {
  if (vulnerabilityTrendPlotFrame) {
    window.cancelAnimationFrame(vulnerabilityTrendPlotFrame);
  }
  vulnerabilityTrendPlotFrame = window.requestAnimationFrame(() => {
    vulnerabilityTrendPlotFrame = window.requestAnimationFrame(() => {
      vulnerabilityTrendPlotFrame = 0;
      renderVulnerabilityTrendPlots();
    });
  });
}

function bindVulnerabilityTrendLegendControls() {
  document.querySelectorAll("[data-vulnerability-series]").forEach((button) => {
    button.addEventListener("click", () => {
      const seriesKey = button.dataset.vulnerabilitySeries;
      if (!seriesKey) {
        return;
      }
      state.vulnerabilityTrendVisible[seriesKey] = !vulnerabilitySeriesVisible(seriesKey);
      renderVulnerabilityTimeTrendPanel();
    });
  });
}

function buildVulnerabilityCountryChipsHtml() {
  const countries = vulnerabilityTrendCountries();
  if (countries.length <= 1) {
    return `<span class="vulnerability-country-chip vulnerability-country-chip-muted">Single country view</span>`;
  }
  return countries
    .map((country, index) => {
      const isPrimary = index === 0;
      return `
        <span class="vulnerability-country-chip ${isPrimary ? "is-primary" : ""}">
          ${escapeHtml(isPrimary ? `${country} - focal` : country)}
          ${isPrimary ? "" : `<button type="button" data-vulnerability-remove-country="${escapeHtml(country)}" aria-label="Remove ${escapeHtml(country)}">x</button>`}
        </span>
      `;
    })
    .join("");
}

function buildVulnerabilityRankingHtml() {
  const rows = currentVulnerabilityScopeRows(VULNERABILITY_DASHBOARD_DATA.countryRows);
  if (!rows.length) {
    return `<div class="order-empty">No country-level vulnerability ranking rows are available for the current selection.</div>`;
  }
  return `
    <table class="data-table vulnerability-table">
      <thead>
        <tr>
          <th>Rank</th>
          <th>Country</th>
          <th>Pair</th>
          <th>Base VI</th>
          <th>Minimum</th>
          <th>Maximum A</th>
          <th>Maximum B</th>
        </tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row, index) => `
              <tr>
                <th>${index + 1}</th>
                <td>
                  <strong>${escapeHtml(row.country)}</strong>
                  <div class="vulnerability-table-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(row.proportional))}"></span></div>
                </td>
                <td>${escapeHtml(row.materialPair)}</td>
                <td>${escapeHtml(formatVulnerabilityPercent(row.proportional))}</td>
                <td>${escapeHtml(formatVulnerabilityPercent(row.minimum))}</td>
                <td>${escapeHtml(formatVulnerabilityPercent(row.maximumKnown))}</td>
                <td>${escapeHtml(formatVulnerabilityPercent(row.maximumWithUnknown))}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function buildVulnerabilityDeltaHtml() {
  if (state.resultMode === "baseline") {
    return `<div class="order-empty">Choose an optimization result to compare vulnerability against Original.</div>`;
  }
  const rows = currentVulnerabilityScopeRows(VULNERABILITY_DASHBOARD_DATA.topDeltas);
  if (rows.length) {
    return `
      <table class="data-table vulnerability-table">
        <thead>
          <tr>
            <th>Country</th>
            <th>Pair</th>
            <th>Original</th>
            <th>${escapeHtml(resultModeLabel(state.resultMode))}</th>
            <th>Delta</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
                <tr>
                  <th>${escapeHtml(row.country)}</th>
                  <td>${escapeHtml(row.materialPair)}</td>
                  <td>${escapeHtml(formatVulnerabilityPercent(row.baseline))}</td>
                  <td>${escapeHtml(formatVulnerabilityPercent(row.scenario))}</td>
                  <td>${buildVulnerabilityDeltaBadge(row.delta)}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    `;
  }
  const summary = VULNERABILITY_DASHBOARD_DATA.baselineDeltas.find((row) => row.resultMode === state.resultMode);
  if (!summary) {
    return `<div class="order-empty">No baseline-delta summary is available for the selected result.</div>`;
  }
  return `
    <div class="diagnostic-fact-grid diagnostic-fact-grid-compact">
      ${[
        { label: "Mean Base Delta", value: summary.meanDeltaProportional, note: "Selected result minus Original." },
        { label: "Mean Absolute Base Delta", value: summary.meanAbsDeltaProportional, note: "Average movement regardless of direction." },
        { label: "Largest Base Delta", value: summary.maxAbsDeltaProportional, note: "Largest country-material change in the release." },
        { label: "Maximum B Mean Absolute Delta", value: summary.meanAbsDeltaMaximumWithUnknown, note: "Upper-bound movement under uncertainty." },
      ]
        .map(
          (item) => `
            <article class="diagnostic-fact">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(formatVulnerabilityPercent(item.value))}</strong>
              <small>${escapeHtml(item.note)}</small>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function vulnerabilityResultChoices() {
  const allowedModes = state.resultModes.length
    ? state.resultModes
    : VULNERABILITY_RESULT_SERIES.map((series) => series.key);
  return VULNERABILITY_RESULT_SERIES.filter((series) => allowedModes.includes(series.key));
}

function defaultVulnerabilityResultMode() {
  const choices = vulnerabilityResultChoices().map((series) => series.key);
  if (choices.includes(state.resultMode)) {
    return state.resultMode;
  }
  return choices.includes("baseline") ? "baseline" : choices[0] || "baseline";
}

function ensureVulnerabilityResultScopes() {
  const choices = vulnerabilityResultChoices().map((series) => series.key);
  const fallback = defaultVulnerabilityResultMode();
  if (!choices.includes(state.vulnerabilityStageProfileResultMode)) {
    state.vulnerabilityStageProfileResultMode = fallback;
  }
}

function vulnerabilityStageProfileResultMode() {
  ensureVulnerabilityResultScopes();
  return state.vulnerabilityStageProfileResultMode;
}

function buildVulnerabilityResultOptionsHtml(selectedResult) {
  return vulnerabilityResultChoices()
    .map((series) => `<option value="${escapeHtml(series.key)}" ${series.key === selectedResult ? "selected" : ""}>${escapeHtml(resultModeLabel(series.key))}</option>`)
    .join("");
}

function unusedLegacyBuildVulnerabilitySensitivityOutputHtml() {
  return "";
  /*
    <div class="vulnerability-sensitivity-summary">
      <article>
        <span>Local sensitivity preview</span>
        <strong>${escapeHtml(sensitivity.country)} · ${escapeHtml(step.label)}</strong>
        <small>${escapeHtml(`${state.metal} ${state.year}, ${resultModeLabel(sensitivity.resultMode)}`)}</small>
      </article>
      <article>
        <span>Base VI movement</span>
        <strong>${escapeHtml(formatVulnerabilityPercent(baseEntry.current))} → ${escapeHtml(formatVulnerabilityPercent(baseEntry.scenario))}</strong>
        <small>${buildVulnerabilityDeltaBadge(baseEntry.delta)}</small>
      </article>
      <article>
        <span>Stage response weight</span>
        <strong>${escapeHtml(`${(step.weight * 100).toFixed(0)}%`)}</strong>
        <small>Used for fast local reweighting.</small>
      </article>
    </div>
    <div class="vulnerability-sensitivity-case-grid">
      ${entries
        .map(
          (entry) => `
            <article class="vulnerability-sensitivity-case">
              <div class="vulnerability-sensitivity-case-head">
                <span>${escapeHtml(entry.eyebrow)}</span>
                <strong>${escapeHtml(entry.label)}</strong>
                ${buildVulnerabilityDeltaBadge(entry.delta)}
              </div>
              <div class="vulnerability-sensitivity-bars">
                <div class="vulnerability-sensitivity-bar-row">
                  <span>Current</span>
                  <div class="vulnerability-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(entry.current))}"></span></div>
                  <strong>${escapeHtml(formatVulnerabilityPercent(entry.current))}</strong>
                </div>
                <div class="vulnerability-sensitivity-bar-row">
                  <span>Scenario</span>
                  <div class="vulnerability-bar vulnerability-sensitivity-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(entry.scenario))}"></span></div>
                  <strong>${escapeHtml(formatVulnerabilityPercent(entry.scenario))}</strong>
                </div>
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
  */
}

function buildVulnerabilityMethodNoteHtml() {
  return `
    <div class="vulnerability-method-list">
      ${VULNERABILITY_DASHBOARD_DATA.methodNotes
        .map((note) => `<p>${escapeHtml(note)}</p>`)
        .join("")}
    </div>
  `;
}

function renderVulnerabilityCountryTrend() {
  const trendHost = document.getElementById("vulnerability-trend-charts");
  if (trendHost) {
    trendHost.innerHTML = buildVulnerabilityCountryTrendHtml();
    renderVulnerabilityCountryLineLegend();
    bindVulnerabilityCountryControls();
    bindVulnerabilityCountryLineLegendControls();
    renderVulnerabilityStageProfile();
    bindVulnerabilityTrendLegendControls();
    bindPlotDownloadControls();
    scheduleVulnerabilityTrendPlots();
    loadVulnerabilityCountryViData();
    loadVulnerabilityStageProfile();
  }
}

function renderVulnerabilityTimeTrendPanel() {
  const panel = document.getElementById("vulnerability-time-trend-panel");
  if (!panel) {
    renderVulnerabilityCountryTrend();
    return;
  }
  panel.outerHTML = buildVulnerabilityTimeTrendPanelHtml();
  renderVulnerabilityCountryLineLegend();
  bindVulnerabilityCountryControls();
  bindVulnerabilityCountryLineLegendControls();
  bindVulnerabilityTrendLegendControls();
  bindPlotDownloadControls();
  scheduleVulnerabilityTrendPlots();
  loadVulnerabilityCountryViData({ trendOnly: true });
}

async function loadVulnerabilityCountryViData({ trendOnly = false } = {}) {
  const payload = state.vulnerabilityCountryVi;
  const countries = vulnerabilityTrendCountries();
  const key = vulnerabilityCountryViKey();
  if (!countries.length || payload.loading || (payload.key === key && (payload.data || payload.error))) {
    return;
  }
  payload.key = key;
  payload.loading = true;
  payload.error = "";
  payload.data = null;
  if (trendOnly) {
    renderVulnerabilityTimeTrendPanel();
  } else {
    renderVulnerabilityCountryTrend();
  }
  try {
    const settledResponses = await Promise.allSettled(
      countries.map((country) => apiClient.requestVulnerabilityCountryVi({
        metal: vulnerabilityMetalId(),
        year: ensureVulnerabilityStageProfileYear(),
        resultMode: state.resultMode,
        cobaltMode: state.cobaltMode,
        country,
        pair: state.vulnerabilityStageProfilePair,
        accessMode: state.accessMode,
        accessPassword: state.accessPassword,
      })),
    );
    const responses = settledResponses
      .filter((entry) => entry.status === "fulfilled")
      .map((entry) => entry.value);
    if (!responses.length) {
      const firstError = settledResponses.find((entry) => entry.status === "rejected")?.reason;
      throw firstError || new Error("Country VI request failed.");
    }
    payload.data = {
      countries: responses,
      pairOptions: responses[0]?.pairOptions || [],
      rows: responses.flatMap((response) => response?.rows || []),
    };
  } catch (error) {
    payload.error = error?.message || "Country VI request failed.";
  } finally {
    payload.loading = false;
    if (trendOnly) {
      renderVulnerabilityTimeTrendPanel();
    } else {
      renderVulnerabilityCountryTrend();
    }
  }
}

function renderVulnerabilitySensitivityPanel() {
  const host = document.getElementById("vulnerability-sensitivity-panel");
  if (!host) {
    return;
  }
  const sensitivity = ensureVulnerabilitySensitivity();
  host.innerHTML = buildVulnerabilitySensitivityPanelHtml();
  bindVulnerabilitySensitivityControls();
  bindPlotDownloadControls();
  scheduleVulnerabilitySensitivityStageProfilePlot();
  if (
    state.accessMode === "analyst"
    && state.accessUnlocked
    && !sensitivity.options
    && !sensitivity.optionsLoading
    && !sensitivity.optionsError
  ) {
    loadVulnerabilitySensitivityOptions();
  }
}

function bindVulnerabilityCountryControls() {
  const countrySelect = document.getElementById("vulnerability-country-vi-country-select");
  if (countrySelect) {
    countrySelect.onchange = () => {
      const previousCountry = state.vulnerabilityCountry;
      state.vulnerabilityCountry = countrySelect.value;
      state.vulnerabilityTrendCountry = state.vulnerabilityCountry;
      state.vulnerabilityStageProfilePair = "";
      state.vulnerabilityTrendPair = "";
      state.vulnerabilityTrendCompareCountries = state.vulnerabilityTrendCompareCountries.filter(
        (country) => country !== state.vulnerabilityCountry,
      );
      state.vulnerabilityCompareCountries = state.vulnerabilityTrendCompareCountries;
      state.vulnerabilityCountryVi.key = "";
      state.vulnerabilityCountryVi.data = null;
      state.vulnerabilityCountryVi.error = "";
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      if (!state.vulnerabilitySensitivity.draftCountry || state.vulnerabilitySensitivity.draftCountry === previousCountry) {
        state.vulnerabilitySensitivity.draftCountry = state.vulnerabilityCountry;
        state.vulnerabilitySensitivity.draftScenarioProduction = "";
        state.vulnerabilitySensitivity.result = null;
      }
      renderVulnerabilityDashboard();
    };
  }

  const metalSelect = document.getElementById("vulnerability-country-vi-metal-select");
  if (metalSelect) {
    metalSelect.onchange = () => {
      state.vulnerabilityMetal = metalSelect.value;
      state.vulnerabilityCountry = "";
      state.vulnerabilityMaterial = "";
      state.vulnerabilityStageProfilePair = "";
      state.vulnerabilityTrendPair = "";
      state.vulnerabilityTrendCompareCountries = [];
      state.vulnerabilityCompareCountries = [];
      state.vulnerabilityCountryVisible = {};
      state.vulnerabilityCountryVi.key = "";
      state.vulnerabilityCountryVi.data = null;
      state.vulnerabilityCountryVi.error = "";
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      state.vulnerabilitySensitivity.selectedMetal = state.vulnerabilityMetal;
      state.vulnerabilitySensitivity.selectedMaterial = "";
      state.vulnerabilitySensitivity.selectedPair = "";
      state.vulnerabilitySensitivity.options = null;
      state.vulnerabilitySensitivity.optionsKey = "";
      state.vulnerabilitySensitivity.result = null;
      syncStateToUrl(state);
      renderVulnerabilityDashboard();
    };
  }

  const materialSelect = document.getElementById("vulnerability-country-vi-material-select");
  if (materialSelect) {
    materialSelect.onchange = () => {
      state.vulnerabilityMaterial = materialSelect.value;
      state.vulnerabilityStageProfilePair = vulnerabilityPairForMaterial(state.vulnerabilityMaterial);
      state.vulnerabilityTrendPair = state.vulnerabilityStageProfilePair;
      state.vulnerabilityCountryVi.key = "";
      state.vulnerabilityCountryVi.data = null;
      state.vulnerabilityCountryVi.error = "";
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      if (!state.vulnerabilitySensitivity.selectedPair) {
        state.vulnerabilitySensitivity.selectedPair = state.vulnerabilityStageProfilePair;
      }
      renderVulnerabilityDashboard();
    };
  }

  const yearSelect = document.getElementById("vulnerability-country-vi-year-select");
  if (yearSelect) {
    yearSelect.onchange = () => {
      const nextYear = Number(yearSelect.value);
      if (!Number.isFinite(nextYear) || nextYear === Number(state.vulnerabilityStageProfileYear)) {
        return;
      }
      state.vulnerabilityStageProfileYear = nextYear;
      state.vulnerabilityStageProfile.key = "";
      state.vulnerabilityStageProfile.data = null;
      state.vulnerabilityStageProfile.error = "";
      state.vulnerabilityStageProfile.loading = false;
      renderVulnerabilityDashboard();
    };
  }

  const compareSelect = document.getElementById("vulnerability-trend-compare-country-select");
  const addButton = document.getElementById("vulnerability-trend-add-country-btn");
  if (addButton && compareSelect) {
    addButton.onclick = () => {
      const nextCountry = compareSelect.value;
      if (
        nextCountry
        && nextCountry !== state.vulnerabilityTrendCountry
        && !state.vulnerabilityTrendCompareCountries.includes(nextCountry)
        && state.vulnerabilityTrendCompareCountries.length < 3
      ) {
        state.vulnerabilityTrendCompareCountries = [...state.vulnerabilityTrendCompareCountries, nextCountry];
        state.vulnerabilityCompareCountries = state.vulnerabilityTrendCompareCountries;
        state.vulnerabilityCountryVi.key = "";
        state.vulnerabilityCountryVi.data = null;
        state.vulnerabilityCountryVi.error = "";
        renderVulnerabilityTimeTrendPanel();
      }
    };
  }

  document.querySelectorAll("[data-vulnerability-remove-country]").forEach((button) => {
    button.onclick = () => {
      const country = button.dataset.vulnerabilityRemoveCountry;
      state.vulnerabilityTrendCompareCountries = state.vulnerabilityTrendCompareCountries.filter((entry) => entry !== country);
      state.vulnerabilityCompareCountries = state.vulnerabilityTrendCompareCountries;
      state.vulnerabilityCountryVi.key = "";
      state.vulnerabilityCountryVi.data = null;
      state.vulnerabilityCountryVi.error = "";
      renderVulnerabilityTimeTrendPanel();
    };
  });
}

function vulnerabilitySensitivityRuntimeKey(resultMode = state.vulnerabilitySensitivity.resultMode) {
  const sensitivity = state.vulnerabilitySensitivity;
  return [sensitivity.selectedMetal || vulnerabilityMetalId(), state.year, state.cobaltMode, resultMode].join("|");
}

function vulnerabilitySensitivityStep(stepKey) {
  return VULNERABILITY_SENSITIVITY_STEPS.find((entry) => entry.key === stepKey)
    || VULNERABILITY_SENSITIVITY_STEPS[2];
}

function roundSensitivityProduction(value) {
  const numeric = asNumber(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.round(numeric * 10) / 10;
}

function formatSensitivityProduction(value) {
  const numeric = asNumber(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function formatSensitivityProductionDelta(current, scenario) {
  const base = asNumber(current);
  const next = asNumber(scenario);
  if (!Number.isFinite(base) || base <= 0 || !Number.isFinite(next)) {
    return "-";
  }
  const pct = ((next - base) / base) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function sensitivityOptionsCountries() {
  return state.vulnerabilitySensitivity.options?.countries || [];
}

function sensitivityMetalId() {
  const sensitivity = state.vulnerabilitySensitivity;
  const allowed = (state.metals || []).map((metal) => metal.id || metal).filter(Boolean);
  if (!sensitivity.selectedMetal || (allowed.length && !allowed.includes(sensitivity.selectedMetal))) {
    sensitivity.selectedMetal = allowed.includes(vulnerabilityMetalId()) ? vulnerabilityMetalId() : allowed[0] || state.metal;
  }
  return sensitivity.selectedMetal;
}

function sensitivityMaterialOptions() {
  const pairs = state.vulnerabilitySensitivity.options?.pairs || [];
  const materials = pairs
    .map((entry) => entry.chemistry || parseVulnerabilityPair(entry.pair).material)
    .filter(Boolean);
  if (materials.includes("NMC") && materials.includes("NCA")) {
    materials.push("NCX");
  }
  return sortVulnerabilityMaterials(materials);
}

function sensitivityCountryOption(country) {
  return sensitivityOptionsCountries().find((entry) => entry.country === country) || null;
}

function sensitivityProductionValue(country, step) {
  const option = sensitivityCountryOption(country);
  const value = option?.steps?.[step];
  return Number.isFinite(asNumber(value)) ? asNumber(value) : 0;
}

function normalizeSensitivityEdit(edit) {
  const step = vulnerabilitySensitivityStep(edit.step).key;
  const country = edit.country || state.vulnerabilitySensitivity.draftCountry;
  const current = sensitivityProductionValue(country, step);
  const scenario = Number.isFinite(asNumber(edit.scenarioProduction))
    ? Math.max(0, roundSensitivityProduction(edit.scenarioProduction))
    : roundSensitivityProduction(current);
  return {
    country,
    step,
    scenarioProduction: scenario,
  };
}

function ensureVulnerabilitySensitivity() {
  const sensitivity = state.vulnerabilitySensitivity;
  sensitivityMetalId();
  const resultChoices = vulnerabilityResultChoices();
  const validResults = resultChoices.map((series) => series.key);
  const validSteps = VULNERABILITY_SENSITIVITY_STEPS.map((step) => step.key);
  if (!validResults.includes(sensitivity.resultMode)) {
    sensitivity.resultMode = validResults.includes(state.resultMode)
      ? state.resultMode
      : validResults[0] || "baseline";
  }
  if (!validSteps.includes(sensitivity.draftStep)) {
    sensitivity.draftStep = "refining";
  }
  const runtimeKey = vulnerabilitySensitivityRuntimeKey();
  if (sensitivity.optionsKey && sensitivity.optionsKey !== runtimeKey) {
    sensitivity.options = null;
    sensitivity.optionsKey = "";
    sensitivity.optionsError = "";
    sensitivity.result = null;
    sensitivity.resultError = "";
  }
  const countryOptions = sensitivityOptionsCountries().map((entry) => entry.country);
  const materialOptions = sensitivityMaterialOptions();
  if (materialOptions.length && !materialOptions.includes(sensitivity.selectedMaterial)) {
    const preferredMaterial = [
      state.vulnerabilityMaterial,
      parseVulnerabilityPair(state.vulnerabilityStageProfilePair).material,
      parseVulnerabilityPair(state.vulnerabilityTrendPair).material,
    ].find((material) => materialOptions.includes(material));
    sensitivity.selectedMaterial = preferredMaterial || materialOptions[0];
  }
  const selectedPair = vulnerabilityPairForMaterial(sensitivity.selectedMaterial, sensitivity.selectedMetal);
  if (selectedPair && sensitivity.selectedPair !== selectedPair) {
    sensitivity.selectedPair = selectedPair;
    sensitivity.result = null;
  }
  if (countryOptions.length) {
    if (!countryOptions.includes(sensitivity.draftCountry)) {
      sensitivity.draftCountry = countryOptions.includes(state.vulnerabilityCountry)
        ? state.vulnerabilityCountry
        : countryOptions[0];
    }
    sensitivity.edits = sensitivity.edits
      .filter((edit) => countryOptions.includes(edit.country) && validSteps.includes(edit.step))
      .map(normalizeSensitivityEdit);
    const draftCurrent = sensitivityProductionValue(sensitivity.draftCountry, sensitivity.draftStep);
    if (!Number.isFinite(asNumber(sensitivity.draftScenarioProduction)) || sensitivity.draftScenarioProduction === "") {
      sensitivity.draftScenarioProduction = roundSensitivityProduction(draftCurrent);
    }
  } else if (!sensitivity.draftCountry) {
    sensitivity.draftCountry = state.vulnerabilityCountry || "";
  }
  return sensitivity;
}

function vulnerabilitySensitivityRequestBase() {
  const sensitivity = ensureVulnerabilitySensitivity();
  return {
    metal: sensitivity.selectedMetal || vulnerabilityMetalId(),
    year: state.year,
    resultMode: sensitivity.resultMode,
    cobaltMode: state.cobaltMode,
    accessMode: state.accessMode,
    accessPassword: state.accessPassword,
  };
}

async function loadVulnerabilitySensitivityOptions(options = {}) {
  const sensitivity = ensureVulnerabilitySensitivity();
  if (state.accessMode !== "analyst" || !state.accessUnlocked || sensitivity.optionsLoading) {
    return;
  }
  const runtimeKey = vulnerabilitySensitivityRuntimeKey();
  if (!options.force && sensitivity.options && sensitivity.optionsKey === runtimeKey) {
    return;
  }
  sensitivity.optionsLoading = true;
  sensitivity.optionsError = "";
  renderVulnerabilitySensitivityPanel();
  try {
    const payload = await apiClient.requestVulnerabilitySensitivityOptions(vulnerabilitySensitivityRequestBase());
    sensitivity.options = payload;
    sensitivity.optionsKey = runtimeKey;
    sensitivity.optionsError = "";
    const countries = (payload.countries || []).map((entry) => entry.country);
    if (countries.length && !countries.includes(sensitivity.draftCountry)) {
      sensitivity.draftCountry = countries.includes(state.vulnerabilityCountry)
        ? state.vulnerabilityCountry
        : countries[0];
    }
    sensitivity.draftScenarioProduction = "";
    ensureVulnerabilitySensitivity();
  } catch (error) {
    sensitivity.options = null;
    sensitivity.optionsKey = "";
    sensitivity.optionsError = error.message || "Failed to load production options.";
  } finally {
    sensitivity.optionsLoading = false;
    renderVulnerabilitySensitivityPanel();
  }
}

function buildSensitivityCountryOptionsHtml(selectedCountry) {
  return sensitivityOptionsCountries()
    .map((entry) => `<option value="${escapeHtml(entry.country)}" ${entry.country === selectedCountry ? "selected" : ""}>${escapeHtml(entry.country)}</option>`)
    .join("");
}

function buildSensitivityStepOptionsHtml(selectedStep) {
  return VULNERABILITY_SENSITIVITY_STEPS
    .map((entry) => `<option value="${escapeHtml(entry.key)}" ${entry.key === selectedStep ? "selected" : ""}>${escapeHtml(entry.label)}</option>`)
    .join("");
}

function buildSensitivityResultOptionsHtml(selectedResult) {
  return buildVulnerabilityResultOptionsHtml(selectedResult);
}

function buildSensitivityPairOptionsHtml(selectedPair) {
  return (state.vulnerabilitySensitivity.options?.pairs || [])
    .map((entry) => `<option value="${escapeHtml(entry.pair)}" ${entry.pair === selectedPair ? "selected" : ""}>${escapeHtml(entry.label || entry.pair)}</option>`)
    .join("");
}

function buildSensitivityMaterialOptionsHtml(selectedMaterial) {
  return sensitivityMaterialOptions()
    .map((material) => `<option value="${escapeHtml(material)}" ${material === selectedMaterial ? "selected" : ""}>${escapeHtml(material)}</option>`)
    .join("");
}

function buildVulnerabilitySensitivityEditRowsHtml() {
  const sensitivity = ensureVulnerabilitySensitivity();
  if (!sensitivity.edits.length) {
    return `<div class="order-empty">Add one or more country-step production edits before recalculating VI.</div>`;
  }
  return `
    <div class="vulnerability-edit-table" role="table" aria-label="Batch production edits">
      <div class="vulnerability-edit-row vulnerability-edit-row-head" role="row">
        <span>Country</span>
        <span>Step</span>
        <span>Current production</span>
        <span>Scenario production</span>
        <span>Change</span>
        <span></span>
      </div>
      ${sensitivity.edits
        .map((edit, index) => {
          const current = sensitivityProductionValue(edit.country, edit.step);
          const delta = formatSensitivityProductionDelta(current, edit.scenarioProduction);
          return `
            <div class="vulnerability-edit-row" role="row">
              <strong>${escapeHtml(edit.country)}</strong>
              <span>${escapeHtml(vulnerabilitySensitivityStep(edit.step).label)}</span>
              <span>${escapeHtml(formatSensitivityProduction(current))}</span>
              <label class="vulnerability-edit-input-label">
                <span class="sr-only">Scenario production</span>
                <input class="text-input" data-vulnerability-edit-production="${escapeHtml(String(index))}" type="number" min="0" step="0.1" value="${escapeHtml(String(edit.scenarioProduction))}" />
              </label>
              <span class="vulnerability-edit-delta">${escapeHtml(delta)}</span>
              <button class="ghost-btn vulnerability-edit-remove" type="button" data-vulnerability-remove-edit="${escapeHtml(String(index))}">Remove</button>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function buildVulnerabilitySensitivityControlsHtml() {
  const sensitivity = ensureVulnerabilitySensitivity();
  if (sensitivity.optionsLoading) {
    return `
      <div class="vulnerability-sensitivity-loading">
        <strong>Loading graph production data</strong>
        <span>Production baselines are read from the selected coefficient-set nodes before editing.</span>
      </div>
    `;
  }
  if (sensitivity.optionsError) {
    return `
      <div class="vulnerability-sensitivity-lock">
        <strong>Could not load VI sensitivity setup</strong>
        <span>${escapeHtml(sensitivity.optionsError)}</span>
        <button id="vulnerability-sensitivity-retry-btn" class="ghost-btn" type="button">Retry</button>
      </div>
    `;
  }
  if (!sensitivity.options) {
    return `
      <div class="vulnerability-sensitivity-loading">
        <strong>Preparing VI sensitivity setup</strong>
        <span>Non-Guest mode will load editable production totals without changing the main Sankey or VI tables.</span>
      </div>
    `;
  }

  const draftCurrent = sensitivityProductionValue(sensitivity.draftCountry, sensitivity.draftStep);
  const draftScenario = Number.isFinite(asNumber(sensitivity.draftScenarioProduction))
    ? roundSensitivityProduction(sensitivity.draftScenarioProduction)
    : roundSensitivityProduction(draftCurrent);
  const draftDelta = formatSensitivityProductionDelta(draftCurrent, draftScenario);
  return `
    <div class="vulnerability-sensitivity-sandbox vulnerability-sensitivity-sandbox-exact">
      <section class="vulnerability-sensitivity-section vulnerability-sensitivity-scenario">
        <div class="vulnerability-sensitivity-section-head">
          <span>Scenario setup</span>
          <strong>Batch-edit production and choose the Conversion Factor Optimization set</strong>
          <small>Each recalculation copies the selected graph, applies these edits, then runs the original VI graph algorithms.</small>
        </div>
        <div class="vulnerability-sensitivity-controls vulnerability-sensitivity-controls-exact">
          <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-result-select">
            <span>Conversion Factor Optimization</span>
            <select id="vulnerability-sensitivity-result-select" class="text-input">
              ${buildSensitivityResultOptionsHtml(sensitivity.resultMode)}
            </select>
          </label>
          <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-metal-select">
            <span>VI metal</span>
            <select id="vulnerability-sensitivity-metal-select" class="text-input">
              ${buildVulnerabilityMetalOptionsHtml(sensitivity.selectedMetal)}
            </select>
          </label>
          <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-material-select">
            <span>Material type</span>
            <select id="vulnerability-sensitivity-material-select" class="text-input">
              ${buildSensitivityMaterialOptionsHtml(sensitivity.selectedMaterial)}
            </select>
          </label>
          <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-country-select">
            <span>Country</span>
            <select id="vulnerability-sensitivity-country-select" class="text-input">
              ${buildSensitivityCountryOptionsHtml(sensitivity.draftCountry)}
            </select>
          </label>
          <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-step-select">
            <span>Step</span>
            <select id="vulnerability-sensitivity-step-select" class="text-input">
              ${buildSensitivityStepOptionsHtml(sensitivity.draftStep)}
            </select>
          </label>
          <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-draft-production-input">
            <span>Scenario production</span>
            <input id="vulnerability-sensitivity-draft-production-input" class="text-input" type="number" min="0" step="0.1" value="${escapeHtml(String(draftScenario))}" />
          </label>
          <article class="vulnerability-production-field vulnerability-production-delta">
            <span>Current</span>
            <strong>${escapeHtml(formatSensitivityProduction(draftCurrent))}</strong>
            <small>${escapeHtml(draftDelta)}</small>
          </article>
          <button id="vulnerability-sensitivity-add-edit-btn" class="ghost-btn" type="button">Add edit</button>
        </div>
      </section>
      <section class="vulnerability-sensitivity-section vulnerability-production-editor">
        <div class="vulnerability-sensitivity-section-head">
          <span>Production editor</span>
          <strong>${escapeHtml(`${sensitivity.edits.length} active ${sensitivity.edits.length === 1 ? "edit" : "edits"}`)}</strong>
          <small>Scenario production values are temporary and scoped to this lab.</small>
        </div>
        ${buildVulnerabilitySensitivityEditRowsHtml()}
        <div class="vulnerability-sensitivity-actions">
          <button id="vulnerability-sensitivity-reset-btn" class="ghost-btn" type="button" ${sensitivity.edits.length ? "" : "disabled"}>Reset edits</button>
          <button id="vulnerability-sensitivity-recalculate-btn" class="primary-btn" type="button" ${sensitivity.edits.length || sensitivity.resultLoading ? "" : "disabled"}>${sensitivity.resultLoading ? "Recalculating..." : "Recalculate VI"}</button>
        </div>
      </section>
    </div>
  `;
}

function sensitivityResultCountry(result, preferredCountry = state.vulnerabilitySensitivity.outputCountry) {
  const countries = result?.countries || [];
  return countries.find((entry) => entry.country === preferredCountry) || countries[0] || null;
}

function buildSensitivitySummaryCardHtml(caseConfig, entry) {
  const current = entry?.current;
  const scenario = entry?.scenario;
  const delta = entry?.delta;
  return `
    <article class="vulnerability-sensitivity-case">
      <div class="vulnerability-sensitivity-case-head">
        <span>${escapeHtml(caseConfig.eyebrow)}</span>
        <strong>${escapeHtml(caseConfig.label)}</strong>
        ${buildVulnerabilityDeltaBadge(delta)}
      </div>
      <div class="vulnerability-sensitivity-bars">
        <div class="vulnerability-sensitivity-bar-row">
          <span>Current</span>
          <div class="vulnerability-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(current))}"></span></div>
          <strong>${escapeHtml(formatVulnerabilityPercent(current))}</strong>
        </div>
        <div class="vulnerability-sensitivity-bar-row">
          <span>Scenario</span>
          <div class="vulnerability-bar vulnerability-sensitivity-bar" aria-hidden="true"><span style="width: ${escapeHtml(vulnerabilityPercentWidth(scenario))}"></span></div>
          <strong>${escapeHtml(formatVulnerabilityPercent(scenario))}</strong>
        </div>
      </div>
    </article>
  `;
}

function buildSensitivityPairTableHtml(countryResult) {
  const pairs = countryResult?.pairs || [];
  if (!pairs.length) {
    return `<div class="order-empty">No chemistry-pair VI rows are available for this output country.</div>`;
  }
  return `
    <div class="table-scroll">
      <table class="vulnerability-table vulnerability-sensitivity-pair-table">
        <thead>
          <tr>
            <th>Pair</th>
            <th>Case</th>
            <th>Current</th>
            <th>Scenario</th>
            <th>Delta</th>
            <th>Scenario denominator</th>
          </tr>
        </thead>
        <tbody>
          ${pairs
            .map((pair) => VULNERABILITY_CASE_GUIDE
              .map((caseConfig, index) => {
                const entry = pair[caseConfig.key] || {};
                return `
                  <tr class="${pair.selected ? "is-selected" : ""}">
                    ${index === 0 ? `<th rowspan="${escapeHtml(String(VULNERABILITY_CASE_GUIDE.length))}">${escapeHtml(pair.pair)}</th>` : ""}
                    <td><strong>${escapeHtml(caseConfig.label)}</strong></td>
                    <td>${escapeHtml(formatVulnerabilityPercent(entry.current))}</td>
                    <td>${escapeHtml(formatVulnerabilityPercent(entry.scenario))}</td>
                    <td>${buildVulnerabilityDeltaBadge(entry.delta)}</td>
                    ${index === 0 ? `<td rowspan="${escapeHtml(String(VULNERABILITY_CASE_GUIDE.length))}">${escapeHtml(formatSensitivityProduction(pair.scenarioDenominator))}</td>` : ""}
                  </tr>
                `;
              })
              .join(""))
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function buildAppliedSensitivityEditsHtml(result) {
  const edits = result?.edits || [];
  if (!edits.length) {
    return "";
  }
  return `
    <div class="vulnerability-applied-edits">
      ${edits
        .map((edit) => `
          <span>
            <strong>${escapeHtml(edit.country)}</strong>
            ${escapeHtml(edit.stepLabel || vulnerabilitySensitivityStep(edit.step).label)}
            ${escapeHtml(formatSensitivityProduction(edit.currentProduction))}
            to
            ${escapeHtml(formatSensitivityProduction(edit.scenarioProduction))}
          </span>
        `)
        .join("")}
    </div>
  `;
}

function buildVulnerabilitySensitivityOutputHtml() {
  const sensitivity = ensureVulnerabilitySensitivity();
  if (sensitivity.resultLoading) {
    return `
      <div class="vulnerability-sensitivity-output">
        <div class="vulnerability-sensitivity-output-head">
          <span>Scenario Output</span>
          <strong>Running original VI recomputation</strong>
          <small>The sandbox graph is being recalculated without mutating the main Sankey or VI tables.</small>
        </div>
        <div class="order-empty">Recalculating VI from the edited graph...</div>
      </div>
    `;
  }
  if (sensitivity.resultError) {
    return `
      <div class="vulnerability-sensitivity-output">
        <div class="vulnerability-sensitivity-output-head">
          <span>Scenario Output</span>
          <strong>Recalculation failed</strong>
          <small>${escapeHtml(sensitivity.resultError)}</small>
        </div>
      </div>
    `;
  }
  const result = sensitivity.result;
  if (!result) {
    return `
      <div class="vulnerability-sensitivity-output">
        <div class="vulnerability-sensitivity-output-head">
          <span>Scenario Output</span>
          <strong>Ready for exact VI recomputation</strong>
          <small>Add one or more production edits, then run Recalculate VI. Main Sankey and VI tables remain unchanged.</small>
        </div>
        <div class="order-empty">No sensitivity result has been applied to this sandbox yet.</div>
      </div>
    `;
  }
  const countries = result.countries || [];
  const countryResult = sensitivityResultCountry(result);
  if (!countryResult) {
    return `<div class="order-empty">No output-country VI result is available for this recalculation.</div>`;
  }
  sensitivity.outputCountry = countryResult.country;
  const selectedPair = countryResult.selectedPair || result.pair || sensitivity.selectedPair || "";
  const selectedScope = parseVulnerabilityPair(selectedPair);
  const selectedScopeLabel = selectedScope.material
    ? `${selectedScope.material} on ${selectedScope.metal || result.metal || sensitivity.selectedMetal}`
    : (selectedPair || "selected material");
  return `
    <div class="vulnerability-sensitivity-output">
      <div class="vulnerability-sensitivity-output-head vulnerability-sensitivity-output-toolbar">
        <div class="vulnerability-sensitivity-output-title">
          <span>Scenario Output</span>
          <strong>${escapeHtml(`${countryResult.country} | ${result.metal || sensitivity.selectedMetal} ${result.year || state.year} | ${resultModeLabel(result.resultMode)}`)}</strong>
          <small>${escapeHtml(`Material scope: ${selectedScopeLabel}. Main Sankey and primary VI tables remain unchanged.`)}</small>
        </div>
        <label class="vulnerability-sensitivity-field" for="vulnerability-sensitivity-output-country-select">
          <span>View country</span>
          <select id="vulnerability-sensitivity-output-country-select" class="text-input">
            ${countries
              .map((entry) => `<option value="${escapeHtml(entry.country)}" ${entry.country === countryResult.country ? "selected" : ""}>${escapeHtml(entry.country)}</option>`)
              .join("")}
          </select>
        </label>
      </div>
      <div class="vulnerability-sensitivity-summary">
        <article>
          <span>Applied edits</span>
          <strong>${escapeHtml(String((result.edits || []).length))}</strong>
          <small>Temporary country-step production changes.</small>
        </article>
        <article>
          <span>Method</span>
          <strong>Exact VI</strong>
          <small>${escapeHtml(`Original graph algorithms for ${selectedScopeLabel}.`)}</small>
        </article>
      </div>
      ${buildAppliedSensitivityEditsHtml(result)}
      <div class="vulnerability-sensitivity-case-grid">
        ${VULNERABILITY_CASE_GUIDE
          .map((caseConfig) => buildSensitivitySummaryCardHtml(caseConfig, countryResult.summary?.[caseConfig.key]))
          .join("")}
      </div>
      ${buildSensitivityStageProfileHtml(countryResult)}
      ${buildSensitivityPairTableHtml(countryResult)}
    </div>
  `;
}

function buildVulnerabilitySensitivityPanelHtml() {
  if (state.accessMode !== "analyst" || !state.accessUnlocked) {
    return `
      <div class="vulnerability-sensitivity-lock">
        <strong>VI Sensitivity requires Non-Guest Login</strong>
        <span>Guest mode keeps production editing and recalculation controls unavailable.</span>
      </div>
    `;
  }
  return `
    <div class="vulnerability-sensitivity-shell">
      ${buildVulnerabilitySensitivityControlsHtml()}
      ${buildVulnerabilitySensitivityOutputHtml()}
    </div>
  `;
}

function syncVulnerabilitySensitivityFromControls() {
  const sensitivity = ensureVulnerabilitySensitivity();
  const resultSelect = document.getElementById("vulnerability-sensitivity-result-select");
  const metalSelect = document.getElementById("vulnerability-sensitivity-metal-select");
  const materialSelect = document.getElementById("vulnerability-sensitivity-material-select");
  const countrySelect = document.getElementById("vulnerability-sensitivity-country-select");
  const stepSelect = document.getElementById("vulnerability-sensitivity-step-select");
  const draftInput = document.getElementById("vulnerability-sensitivity-draft-production-input");
  const previousResult = sensitivity.resultMode;
  const previousMetal = sensitivity.selectedMetal;
  const previousMaterial = sensitivity.selectedMaterial;
  sensitivity.resultMode = resultSelect?.value || sensitivity.resultMode;
  sensitivity.selectedMetal = metalSelect?.value || sensitivity.selectedMetal;
  sensitivity.selectedMaterial = materialSelect?.value || sensitivity.selectedMaterial;
  sensitivity.selectedPair = vulnerabilityPairForMaterial(sensitivity.selectedMaterial, sensitivity.selectedMetal);
  sensitivity.draftCountry = countrySelect?.value || sensitivity.draftCountry;
  sensitivity.draftStep = stepSelect?.value || sensitivity.draftStep;
  const draftValue = asNumber(draftInput?.value);
  if (Number.isFinite(draftValue)) {
    sensitivity.draftScenarioProduction = Math.max(0, roundSensitivityProduction(draftValue));
  }
  document.querySelectorAll("[data-vulnerability-edit-production]").forEach((input) => {
    const index = Number(input.dataset.vulnerabilityEditProduction);
    const value = asNumber(input.value);
    if (Number.isInteger(index) && sensitivity.edits[index] && Number.isFinite(value)) {
      sensitivity.edits[index].scenarioProduction = Math.max(0, roundSensitivityProduction(value));
    }
  });
  if (previousResult !== sensitivity.resultMode) {
    sensitivity.options = null;
    sensitivity.optionsKey = "";
    sensitivity.optionsError = "";
    sensitivity.result = null;
    sensitivity.resultError = "";
  }
  if (previousMetal !== sensitivity.selectedMetal) {
    sensitivity.options = null;
    sensitivity.optionsKey = "";
    sensitivity.optionsError = "";
    sensitivity.edits = [];
    sensitivity.draftCountry = "";
    sensitivity.draftScenarioProduction = "";
    sensitivity.result = null;
    sensitivity.resultError = "";
  } else if (previousMaterial !== sensitivity.selectedMaterial) {
    sensitivity.result = null;
    sensitivity.resultError = "";
  }
  ensureVulnerabilitySensitivity();
}

function addVulnerabilitySensitivityEdit() {
  const sensitivity = ensureVulnerabilitySensitivity();
  const country = sensitivity.draftCountry;
  const step = vulnerabilitySensitivityStep(sensitivity.draftStep).key;
  const current = sensitivityProductionValue(country, step);
  const scenario = Number.isFinite(asNumber(sensitivity.draftScenarioProduction))
    ? Math.max(0, roundSensitivityProduction(sensitivity.draftScenarioProduction))
    : roundSensitivityProduction(current);
  const nextEdit = { country, step, scenarioProduction: scenario };
  const existingIndex = sensitivity.edits.findIndex((edit) => edit.country === country && edit.step === step);
  if (existingIndex >= 0) {
    sensitivity.edits[existingIndex] = nextEdit;
  } else {
    sensitivity.edits = [...sensitivity.edits, nextEdit];
  }
  sensitivity.result = null;
  sensitivity.resultError = "";
}

async function recalculateVulnerabilitySensitivity() {
  const sensitivity = ensureVulnerabilitySensitivity();
  if (!sensitivity.edits.length) {
    sensitivity.resultError = "Add at least one production edit before recalculating VI.";
    renderVulnerabilitySensitivityPanel();
    return;
  }
  const reportCountries = Array.from(
    new Set([
      sensitivity.outputCountry,
      sensitivity.draftCountry,
      ...sensitivity.edits.map((edit) => edit.country),
    ].filter(Boolean)),
  );
  sensitivity.resultLoading = true;
  sensitivity.resultError = "";
  renderVulnerabilitySensitivityPanel();
  try {
    const payload = await apiClient.recalculateVulnerabilitySensitivity({
      ...vulnerabilitySensitivityRequestBase(),
      pair: sensitivity.selectedPair,
      edits: sensitivity.edits,
      reportCountries,
    });
    sensitivity.result = payload;
    const resultCountries = (payload.countries || []).map((entry) => entry.country);
    sensitivity.outputCountry = resultCountries.includes(sensitivity.outputCountry)
      ? sensitivity.outputCountry
      : resultCountries[0] || "";
  } catch (error) {
    sensitivity.result = null;
    sensitivity.resultError = error.message || "Vulnerability sensitivity recalculation failed.";
  } finally {
    sensitivity.resultLoading = false;
    renderVulnerabilitySensitivityPanel();
  }
}

function bindVulnerabilitySensitivityControls() {
  const sensitivity = ensureVulnerabilitySensitivity();
  const retryButton = document.getElementById("vulnerability-sensitivity-retry-btn");
  if (retryButton) {
    retryButton.onclick = () => {
      loadVulnerabilitySensitivityOptions({ force: true });
    };
  }
  const resultSelect = document.getElementById("vulnerability-sensitivity-result-select");
  if (resultSelect) {
    resultSelect.onchange = () => {
      syncVulnerabilitySensitivityFromControls();
      renderVulnerabilitySensitivityPanel();
      loadVulnerabilitySensitivityOptions({ force: true });
    };
  }
  const metalSelect = document.getElementById("vulnerability-sensitivity-metal-select");
  if (metalSelect) {
    metalSelect.onchange = () => {
      syncVulnerabilitySensitivityFromControls();
      renderVulnerabilitySensitivityPanel();
      loadVulnerabilitySensitivityOptions({ force: true });
    };
  }
  const materialSelect = document.getElementById("vulnerability-sensitivity-material-select");
  if (materialSelect) {
    materialSelect.onchange = () => {
      syncVulnerabilitySensitivityFromControls();
      sensitivity.result = null;
      renderVulnerabilitySensitivityPanel();
    };
  }
  ["vulnerability-sensitivity-country-select", "vulnerability-sensitivity-step-select"].forEach((id) => {
    const control = document.getElementById(id);
    if (control) {
      control.onchange = () => {
        syncVulnerabilitySensitivityFromControls();
        sensitivity.draftScenarioProduction = "";
        sensitivity.result = null;
        renderVulnerabilitySensitivityPanel();
      };
    }
  });
  const draftInput = document.getElementById("vulnerability-sensitivity-draft-production-input");
  if (draftInput) {
    draftInput.onchange = () => {
      syncVulnerabilitySensitivityFromControls();
      renderVulnerabilitySensitivityPanel();
    };
  }
  document.getElementById("vulnerability-sensitivity-add-edit-btn")?.addEventListener("click", () => {
    syncVulnerabilitySensitivityFromControls();
    addVulnerabilitySensitivityEdit();
    renderVulnerabilitySensitivityPanel();
  });
  document.querySelectorAll("[data-vulnerability-edit-production]").forEach((input) => {
    input.onchange = () => {
      syncVulnerabilitySensitivityFromControls();
      state.vulnerabilitySensitivity.result = null;
      renderVulnerabilitySensitivityPanel();
    };
  });
  document.querySelectorAll("[data-vulnerability-remove-edit]").forEach((button) => {
    button.onclick = () => {
      const index = Number(button.dataset.vulnerabilityRemoveEdit);
      if (Number.isInteger(index)) {
        state.vulnerabilitySensitivity.edits = state.vulnerabilitySensitivity.edits.filter((_edit, editIndex) => editIndex !== index);
        state.vulnerabilitySensitivity.result = null;
        renderVulnerabilitySensitivityPanel();
      }
    };
  });
  document.getElementById("vulnerability-sensitivity-reset-btn")?.addEventListener("click", () => {
    state.vulnerabilitySensitivity.edits = [];
    state.vulnerabilitySensitivity.draftScenarioProduction = "";
    state.vulnerabilitySensitivity.result = null;
    state.vulnerabilitySensitivity.resultError = "";
    renderVulnerabilitySensitivityPanel();
  });
  document.getElementById("vulnerability-sensitivity-recalculate-btn")?.addEventListener("click", () => {
    syncVulnerabilitySensitivityFromControls();
    recalculateVulnerabilitySensitivity();
  });
  const outputCountrySelect = document.getElementById("vulnerability-sensitivity-output-country-select");
  if (outputCountrySelect) {
    outputCountrySelect.onchange = () => {
      state.vulnerabilitySensitivity.outputCountry = outputCountrySelect.value;
      renderVulnerabilitySensitivityPanel();
    };
  }
}

function renderVulnerabilityDashboard() {
  const countryOptions = ensureVulnerabilityCountry();
  const record = currentVulnerabilityRecord();
  const status = document.getElementById("vulnerability-status");
  if (status) {
    const scopeLabel = record?.metal ? `${vulnerabilityMetalId()} ${record.year}` : `${vulnerabilityMetalId()} scenario`;
    status.textContent = `${scopeLabel} vulnerability summary for ${resultModeLabel(state.resultMode)}.`;
  }
  const caseGuideHost = document.getElementById("vulnerability-case-guide");
  void countryOptions;
  if (caseGuideHost) {
    caseGuideHost.innerHTML = buildVulnerabilityCaseGuideHtml();
  }
  renderVulnerabilityCountryTrend();
  renderVulnerabilitySensitivityPanel();
  bindVulnerabilityCountryControls();
}

function renderDiagnosticExplorerSections(focusId = "") {
  const tables = state.currentTables || {};
  const producerHost = document.getElementById("producer-coefficient-table");
  const tradeHost = document.getElementById("trade-flow-table");
  if (producerHost) {
    producerHost.innerHTML = buildProducerCoefficientSectionsHtml(tables.producerCoefficients || [], tables.tradeFlows || []);
  }
  if (tradeHost) {
    tradeHost.innerHTML = buildTradeFlowExplorerHtml(tables.tradeFlows || []);
  }
  bindDiagnosticExplorerControls();
  if (focusId) {
    const focusTarget = document.getElementById(focusId);
    if (focusTarget) {
      focusTarget.focus();
      if (typeof focusTarget.setSelectionRange === "function") {
        const end = focusTarget.value.length;
        focusTarget.setSelectionRange(end, end);
      }
    }
  }
}

function queueDiagnosticExplorerRender(focusId = "") {
  window.clearTimeout(diagnosticSearchTimer);
  diagnosticSearchTimer = window.setTimeout(() => {
    renderDiagnosticExplorerSections(focusId);
  }, 180);
}

function bindDiagnosticExplorerControls() {
  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      const filterKey = button.dataset.filter;
      if (!filterKey || !(filterKey in state.diagnosticFilters)) {
        return;
      }
      state.diagnosticFilters[filterKey] = button.dataset.value || "all";
      if (filterKey.startsWith("coefficient")) {
        state.diagnosticFilters.selectedCoefficientKey = "";
      }
      renderDiagnosticExplorerSections();
    });
  });

  document.querySelectorAll("[data-coefficient-key]").forEach((button) => {
    button.addEventListener("click", () => {
      state.diagnosticFilters.selectedCoefficientKey = button.dataset.coefficientKey || "";
      renderDiagnosticExplorerSections();
    });
  });

  const coefficientSearch = document.getElementById("coefficient-search");
  if (coefficientSearch) {
    coefficientSearch.addEventListener("input", (event) => {
      state.diagnosticFilters.coefficientSearch = event.target.value;
      state.diagnosticFilters.selectedCoefficientKey = "";
      queueDiagnosticExplorerRender("coefficient-search");
    });
  }

  const tradeSearch = document.getElementById("trade-search");
  if (tradeSearch) {
    tradeSearch.addEventListener("input", (event) => {
      state.diagnosticFilters.tradeSearch = event.target.value;
      queueDiagnosticExplorerRender("trade-search");
    });
  }
}

function buildTransitionCardsHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No stage analysis rows are available for the current selection.</div>`;
  }
  return `
    <div class="transition-stage-grid">
      ${rows.map((row) => buildTransitionCardHtml(row)).join("")}
    </div>
  `;
}

function renderLockedAnalysis() {
  const lockedHtml = `
    <div class="analysis-lock-panel">
      <strong>Analysis requires Non-Guest mode</strong>
      <span>Guest mode keeps analysis, stage totals, and detailed optimization tables hidden. Use Access controls to unlock Analyst view.</span>
    </div>
  `;
  document.getElementById("metrics-table").innerHTML = lockedHtml;
  document.getElementById("stage-table").innerHTML = "";
  document.getElementById("parameter-table").innerHTML = "";
  document.getElementById("producer-coefficient-table").innerHTML = "";
  document.getElementById("trade-flow-table").innerHTML = "";
}

function renderTables(tables) {
  state.currentTables = tables || {};
  const board = document.getElementById("data-board");
  board.classList.toggle("analysis-board-locked", state.accessMode !== "analyst");
  if (state.accessMode !== "analyst") {
    renderLockedAnalysis();
    return;
  }
  board.classList.remove("analysis-board-locked");
  const metricRows = state.currentTables.metrics || [];
  const stageRows = state.currentTables.stages || [];
  const parameterRows = state.currentTables.parameters || [];
  const unknownBreakdownRows = state.currentTables.unknownBreakdown || [];
  const isOptimizationStageView = stageRows.length && Object.prototype.hasOwnProperty.call(stageRows[0], "Stage Group");
  document.getElementById("metrics-table").innerHTML =
    metricRows.length && (Object.prototype.hasOwnProperty.call(metricRows[0], "Metric") || Object.prototype.hasOwnProperty.call(metricRows[0], "metric"))
      ? isOptimizationStageView
        ? buildOptimizationImpactOverviewHtml(metricRows, stageRows, unknownBreakdownRows)
        : buildMetricSnapshotHtml(metricRows)
      : metricRows.length && Object.prototype.hasOwnProperty.call(metricRows[0], "baseline")
        ? buildCompareMetricsTableHtml(metricRows)
        : buildTableHtml(metricRows);
  document.getElementById("stage-table").innerHTML =
    stageRows.length && (Object.prototype.hasOwnProperty.call(stageRows[0], "Stage Group") || Object.prototype.hasOwnProperty.call(stageRows[0], "stage"))
      ? buildStageOutcomeCardsHtml(stageRows, unknownBreakdownRows)
      : stageRows.length && Object.prototype.hasOwnProperty.call(stageRows[0], "baseline_unknown")
        ? buildCompareStageTableHtml(stageRows)
        : buildTableHtml(stageRows);
  document.getElementById("parameter-table").innerHTML =
    parameterRows.length && (Object.prototype.hasOwnProperty.call(parameterRows[0], "Parameter") || Object.prototype.hasOwnProperty.call(parameterRows[0], "parameter"))
      ? buildParameterOverviewHtml(parameterRows)
      : parameterRows.length && Object.prototype.hasOwnProperty.call(parameterRows[0], "baseline")
        ? buildCompareParameterTableHtml(parameterRows)
        : buildTableHtml(parameterRows);
  renderDiagnosticExplorerSections();
}

function bindSelectionMenus() {
  document.querySelectorAll("[data-selection-menu-trigger]").forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const menuName = trigger.dataset.selectionMenuTrigger;
      selectionMenuOpen = selectionMenuOpen === menuName ? null : menuName;
      renderSelectionMenuStates();
    });
  });
  document.addEventListener("click", (event) => {
    if (!selectionMenuOpen || event.target.closest(".selection-menu")) {
      return;
    }
    closeSelectionMenus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSelectionMenus();
    }
  });
}

async function bootstrap() {
  const payload = await apiClient.getBootstrap();
  const metadata = payload.metadata;
  state.themes = payload.metadata.themes;
  state.metals = payload.metadata.metals;
  state.metal = payload.metadata.defaultMetal;
  state.theme = payload.metadata.defaultTheme;
  state.years = payload.metadata.years;
  state.resultModes = payload.metadata.resultModes || ["baseline", "pareto_optimal", "sn_minimum", "deviation_minimum"];
  state.resultLabels = payload.metadata.resultLabels || {};
  state.tableViews = payload.metadata.tableViews || ["auto", "baseline", "optimized", "compare"];
  state.tableViewLabels = payload.metadata.tableViewLabels || {};
  state.cobaltModes = payload.metadata.cobaltModes || [];
  state.cobaltModeLabels = payload.metadata.cobaltModeLabels || {};
  state.cobaltMode = payload.metadata.defaultCobaltMode || "mid";
  state.accessMode = payload.metadata.defaultAccessMode || "guest";
  state.accessPassword = "";
  state.accessUnlocked = false;
  state.stageLabels = payload.metadata.stageLabels;
  state.stageOrder = payload.metadata.stageOrder;
  state.sortModes = payload.metadata.sortModes;
  state.specialNodePositions = payload.metadata.specialNodePositions || ["first", "last"];
  state.defaultSpecialNodePosition = payload.metadata.defaultSpecialNodePosition || "first";
  state.referenceQtyDefaults = payload.metadata.defaultReferenceQuantities || state.referenceQtyDefaults;
  state.referenceQty = state.referenceQtyDefaults[state.metal] || payload.metadata.defaultReferenceQuantity;
  state.year = payload.metadata.defaultYear || state.years[state.years.length - 1];
  const params = new URLSearchParams(window.location.search);
  hydrateStateFromUrl(state, metadata);
  state.vulnerabilityMetal = params.get("viMetal") || state.metal;
  vulnerabilityMetalId();
  if (!params.has("ref")) {
    state.referenceQty = state.referenceQtyDefaults[state.metal] || payload.metadata.defaultReferenceQuantity;
  }
  ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
  document.getElementById("reference-qty-input").value = Math.round(state.referenceQty);
  applyTheme(state.theme);
  renderThemeButtons();
  renderMetalButtons();
  renderCobaltModeButtons();
  renderAccessControls();
  renderResultButtons();
  updateStateChips();
  bindSelectionMenus();
  bindControlsToggle();

  const yearButtons = document.getElementById("year-buttons");
  const renderYearButtons = () => renderPills(yearButtons, state.years, state.year, selectYear, String);
  const selectYear = async (year) => {
    state.year = year;
    setSelectionValue("year-selection-value", String(year));
    closeSelectionMenus();
    renderYearButtons();
    await loadFigure();
  };
  renderYearButtons();

  document.getElementById("refresh-btn").addEventListener("click", async () => {
    if (!parseReferenceQuantity()) {
      return;
    }
    await loadFigure({ immediate: true, force: true });
  });
  document.getElementById("reference-qty-input").addEventListener("change", async () => {
    if (!parseReferenceQuantity()) {
      return;
    }
    await loadFigure({ immediate: true });
  });
  document.getElementById("reference-qty-input").addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    if (!parseReferenceQuantity()) {
      return;
    }
    await loadFigure({ immediate: true });
  });
  document.getElementById("download-btn").addEventListener("click", async () => {
    await Plotly.downloadImage(document.getElementById("chart"), {
      format: "png",
      filename: `critical-mineral-${state.metal.toLowerCase()}-${state.resultMode}-${state.year}`,
      height: 1400,
      width: 2200,
      scale: 1,
    });
  });
  document.getElementById("sort-all-size")?.addEventListener("click", async () => {
    await applySortModeToAll("size");
  });
  document.getElementById("sort-all-manual")?.addEventListener("click", async () => {
    await applySortModeToAll("manual");
  });
  document.getElementById("sort-all-continent")?.addEventListener("click", async () => {
    await applySortModeToAll("continent");
  });
  state.workspaceView = workspaceViewFromHash(window.location.hash);
  bindWorkspaceNavigation();
  applyWorkspaceView();
  window.addEventListener(
    "resize",
    debounce(() => {
      syncOrderStudioDetailHeight();
    }, 160),
  );
  document.getElementById("s7-country-btn")?.addEventListener("click", async () => {
    await updateS7Display({ country: !state.s7Display.country });
  });
  document.getElementById("s7-chemistry-btn")?.addEventListener("click", async () => {
    await updateS7Display({ chemistry: !state.s7Display.chemistry });
  });
  document.getElementById("s7-aggregate-btn")?.addEventListener("click", async () => {
    if (!state.s7Display.chemistry) {
      return;
    }
    await updateS7Display({ aggregateNmcNca: !state.s7Display.aggregateNmcNca });
  });
  document.getElementById("access-unlock-btn").addEventListener("click", async () => {
    try {
      await unlockAnalystMode();
    } catch (error) {
      showUiError(error.message, "Access denied");
    }
  });
  document.getElementById("access-password-input").addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    try {
      await unlockAnalystMode();
    } catch (error) {
      showUiError(error.message, "Access denied");
    }
  });
  await loadFigure({ immediate: true, force: true });
}

function renderResultButtons() {
  const container = document.getElementById("result-buttons");
  if (!container) {
    return;
  }
  setSelectionValue("result-selection-value", resultModeLabel(state.resultMode));
  container.classList.remove("result-picker");
  container.innerHTML = state.resultModes
    .map(
      (mode) => `
        <button type="button" class="pill-btn ${state.resultMode === mode ? "active" : ""}" role="menuitemradio" aria-checked="${state.resultMode === mode ? "true" : "false"}" data-result-mode="${escapeHtml(mode)}">
          ${escapeHtml(resultModeLabel(mode))}
        </button>
      `,
    )
    .join("");
  container.querySelectorAll("[data-result-mode]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const nextMode = button.dataset.resultMode;
      closeSelectionMenus();
      if (!nextMode || state.resultMode === nextMode) {
        renderResultButtons();
        return;
      }
      state.resultMode = nextMode;
      ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
      renderResultButtons();
      await loadFigure();
    });
  });
  renderSelectionMenuStates();
}

bootstrap().catch((error) => {
  console.error(error);
  showUiError(error.message);
});
