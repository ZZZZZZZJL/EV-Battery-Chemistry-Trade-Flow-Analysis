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

let layoutSyncToken = 0;
let figureRenderToken = 0;

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
    };
  }
  return state.layoutState[variantKey];
}

function currentLayoutState() {
  return ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
}

function resultModeLabel(value) {
  return state.resultLabels[value] || value;
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

function updateStateChips(payload = {}) {
  const host = document.getElementById("state-chip-row");
  if (!host) {
    return;
  }
  const resultLabel = resultModeLabel(payload.resultMode || state.resultMode);
  const cobaltLabel = (payload.metal || state.metal) === "Co" ? cobaltModeLabel(state.cobaltMode) : "";
  const chips = [
    payload.metal || state.metal,
    String(payload.year || state.year),
    resultLabel,
    cobaltLabel,
  ].filter(Boolean);
  host.innerHTML = chips
    .map((chip) => `<span class="state-chip">${escapeHtml(chip)}</span>`)
    .join("");
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
  const note = document.getElementById("metal-note");
  container.innerHTML = "";
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
      renderMetalButtons();
      renderCobaltModeButtons();
      await loadFigure();
    });
    container.appendChild(button);
  });
  note.textContent = "Ni, Li, and Co are currently active datasets for this optimization viewer.";
}

function renderCobaltModeButtons() {
  const block = document.getElementById("cobalt-mode-block");
  const container = document.getElementById("cobalt-mode-buttons");
  const note = document.getElementById("cobalt-mode-note");
  const isVisible = state.metal === "Co";
  block.classList.toggle("is-hidden", !isVisible);
  if (!isVisible) {
    container.innerHTML = "";
    return;
  }
  renderPills(
    container,
    state.cobaltModes,
    state.cobaltMode,
    async (mode) => {
      state.cobaltMode = mode;
      ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
      renderCobaltModeButtons();
      await loadFigure();
    },
    cobaltModeLabel,
  );
  note.textContent = "Cobalt reads three frozen scenario exports. Middle, Max, and Min are all served from precomputed files rather than rebuilt on the fly.";
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
      ? "Guest mode hides stage totals, country production values, and Diagnostics."
      : state.accessUnlocked
        ? "Non-guest mode is unlocked. Full diagnostics and production values are visible."
        : "Enter the password to unlock non-guest mode.";
}

async function unlockAnalystMode() {
  const input = document.getElementById("access-password-input");
  state.accessPassword = input.value || "";
  try {
    await loadFigure();
    state.accessUnlocked = true;
    renderAccessControls();
    document.querySelector(".advanced-panel")?.removeAttribute("open");
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
  await Plotly.react("chart", figure.data, figure.layout, PLOTLY_CONFIG);
}

async function loadFigure() {
  const renderToken = ++figureRenderToken;
  setStatus("Loading", "warn");
  const layout = currentLayoutState();
  const response = await fetch("/api/figure", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
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
      s7ViewMode: currentS7ViewMode(),
      s7AggregateNmcNca: state.s7Display.aggregateNmcNca,
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(payload.detail || "Request failed");
  }
  const payload = await response.json();
  if (renderToken !== figureRenderToken) {
    return;
  }
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
  state.referenceQty = payload.referenceQuantity;
  state.lastStageControls = payload.stageControls || {};
  document.getElementById("reference-qty-input").value = Math.round(payload.referenceQuantity);
  const optimizationLabel = payload.resultMode === "first_optimization" ? "with flow optimization" : "without flow optimization";
  const cobaltSuffix = payload.metal === "Co" ? ` (${cobaltModeLabel(state.cobaltMode)} scenario)` : "";
  document.getElementById("chart-title").textContent =
    `The Sankey Diagram for ${payload.metal} in ${payload.year} ${optimizationLabel}${cobaltSuffix}`;
  updateStateChips(payload);
  renderSummary(payload.stageSummary);
  renderNotes(payload.notes);
  renderDatasetStatus(payload.datasetStatus);
  renderOrderBoard(payload.stageControls);
  renderTables(payload.tables);
  document.getElementById("table-status").textContent =
    state.accessMode === "guest"
        ? "Guest view: diagnostics preview is locked. Unlock Analyst mode for values and drilldowns."
      : state.resultMode === "baseline"
        ? `Diagnostics: Original only. Switch to First Optimization for optimizer-stage summaries.`
        : `Diagnostics: ${resultModeLabel(payload.resultMode)} stage summaries, bounds, source scaling, and coefficient explorers.`;
  state.lastChartHeight = Number(payload.figure?.layout?.height || 0);
  await renderChartFigure(payload.figure);
  if (renderToken !== figureRenderToken) {
    return;
  }
  syncWorkspaceLayout(state.lastChartHeight);
  setStatus("Ready", "ok");
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

function buildOrderEntry({ stage, item, mode, layout, grid, isAggregatedTail }) {
  const entry = document.createElement("div");
  entry.className = "order-item";
  if (isAggregatedTail) {
    entry.classList.add("tail-item");
  }
  entry.draggable = mode === "manual";
  entry.dataset.stage = stage;
  entry.dataset.label = item.label;
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
      ${isAggregatedTail ? '<span class="tail-badge">Aggregated tail</span>' : ""}
    </div>
    ${valueMarkup}
  `;
  if (mode === "manual") {
    addManualDragHandlers(entry, stage, item.label, layout, grid);
  }
  return entry;
}

function renderGroupedItems(list, items, stage, mode, layout, grid, aggregateCount) {
  const tailLabels = new Set(
    mode === "continent" || aggregateCount <= 0 ? [] : items.slice(-aggregateCount).map((item) => item.label),
  );
  let currentGroup = null;
  items.forEach((item) => {
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
        isAggregatedTail: tailLabels.has(item.label),
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
  const aggregateDisabled = mode === "continent" || (config.maxAggregateCount || 0) === 0;
  aggregateControl.innerHTML = `
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
  body.appendChild(aggregateControl);

  const list = document.createElement("div");
  list.className = "order-list";
  if (!items.length) {
    list.innerHTML = `<div class="order-empty">No standalone nodes in this stage for the current view.</div>`;
  } else if (mode === "continent") {
    renderGroupedItems(list, items, stage, mode, layout, grid, 0);
  } else {
    items.forEach((item) => {
      list.appendChild(
        buildOrderEntry({
          stage,
          item,
          mode,
          layout,
          grid,
          isAggregatedTail: false,
        }),
      );
    });
  }
  body.appendChild(list);
  card.appendChild(body);
  return card;
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
          <span class="impact-label">Original to First Optimization</span>
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
          <small>${escapeHtml(formatValue(scaledSources, "value"))} scaled sources in this view</small>
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

  const maxOriginal = Math.max(...optimizedRows.map((row) => asNumber(row["Original SN"])), 1);
  return `
    <section class="stage-comparison-panel">
      <div class="transition-panel-head">
        <strong>Stage Group Comparison</strong>
        <span>Original SN and First Optimization SN are compared side by side for each synchronized S1-S2-S3 style group.</span>
      </div>
      <div class="stage-comparison-table-wrap">
        <table class="data-table stage-comparison-table">
          <thead>
            <tr>
              <th>Stage group</th>
              <th>Original SN</th>
              <th>First Optimization SN</th>
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
    return `<div class="order-empty">Unknown node breakdown is available when First Optimization publishes synchronized node diagnostics.</div>`;
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
          "Baseline mode does not introduce optimizer weights, bounds, or synchronized factor diagnostics.",
          normalizedRows,
        )}
      </div>
    `;
  }

  const runtimeRows = ["Data Source", "Result Sync", "Solver"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);
  const weightRows = ["alpha", "beta_pp", "beta_pn", "beta_np"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);
  const boundsRows = ["Bounds", "Source Scaling", "Special Handling", "HS Memo Rules"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);

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
    { label: "Visible Rows", value: visibleRows.length, note: `${rows.length} total coefficient rows in this First Optimization export.` },
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
      <p>First Optimization chooses coefficients within Cmin/Cmax while minimizing unknown-node mass and weighted movement away from the recommended value. Use the filters to inspect one coefficient row, then compare its stage with the trade flows below.</p>
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
    return `<div class="order-empty">Coefficient rows are only available when First Optimization exposes factor outputs.</div>`;
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
    return `<div class="order-empty">Trade-flow comparison is available when Original and First Optimization link exports are both present.</div>`;
  }

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
              <th>First Optimization</th>
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
      renderDiagnosticExplorerSections("coefficient-search");
    });
  }

  const tradeSearch = document.getElementById("trade-search");
  if (tradeSearch) {
    tradeSearch.addEventListener("input", (event) => {
      state.diagnosticFilters.tradeSearch = event.target.value;
      renderDiagnosticExplorerSections("trade-search");
    });
  }
}

function buildTransitionCardsHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No stage diagnostics are available for the current selection.</div>`;
  }
  return `
    <div class="transition-stage-grid">
      ${rows.map((row) => buildTransitionCardHtml(row)).join("")}
    </div>
  `;
}

function renderTables(tables) {
  state.currentTables = tables || {};
  const board = document.getElementById("data-board");
  board.classList.toggle("is-hidden", state.accessMode !== "analyst");
  if (state.accessMode !== "analyst") {
    return;
  }
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

async function bootstrap() {
  const response = await fetch("/api/bootstrap");
  if (!response.ok) {
    throw new Error("Failed to load bootstrap metadata.");
  }
  const payload = await response.json();
  state.themes = payload.metadata.themes;
  state.metals = payload.metadata.metals;
  state.metal = payload.metadata.defaultMetal;
  state.theme = payload.metadata.defaultTheme;
  state.years = payload.metadata.years;
  state.resultModes = payload.metadata.resultModes || ["baseline", "first_optimization"];
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
  ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
  document.getElementById("reference-qty-input").value = Math.round(state.referenceQty);
  applyTheme(state.theme);
  renderThemeButtons();
  renderMetalButtons();
  renderCobaltModeButtons();
  renderAccessControls();
  renderResultButtons();

  const yearButtons = document.getElementById("year-buttons");
  const renderYearButtons = () => renderPills(yearButtons, state.years, state.year, selectYear, String);
  const selectYear = async (year) => {
    state.year = year;
    renderYearButtons();
    await loadFigure();
  };
  renderYearButtons();

  document.getElementById("refresh-btn").addEventListener("click", async () => {
    if (!parseReferenceQuantity()) {
      return;
    }
    await loadFigure();
  });
  document.getElementById("reference-qty-input").addEventListener("change", async () => {
    if (!parseReferenceQuantity()) {
      return;
    }
    await loadFigure();
  });
  document.getElementById("reference-qty-input").addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    if (!parseReferenceQuantity()) {
      return;
    }
    await loadFigure();
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
  document.querySelectorAll(".top-nav-primary a").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  });
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
  await loadFigure();
}

function renderResultButtons() {
  const container = document.getElementById("result-buttons");
  renderPills(
    container,
    state.resultModes,
    state.resultMode,
    async (mode) => {
      state.resultMode = mode;
      ensureLayoutState(state.metal, state.resultMode, state.cobaltMode);
      renderResultButtons();
      await loadFigure();
    },
    resultModeLabel,
  );
}

bootstrap().catch((error) => {
  console.error(error);
  showUiError(error.message);
});
