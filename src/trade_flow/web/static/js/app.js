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
  years: [],
  stageLabels: {},
  stageOrder: [],
  sortModes: [],
  specialNodePositions: [],
  defaultSpecialNodePosition: "first",
  layoutState: {},
  lastChartHeight: 0,
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
  const workspaceMain = document.querySelector(".workspace-main");
  const workspaceSide = document.querySelector(".workspace-side");
  const chartFrame = document.querySelector(".chart-frame");
  const chartHost = document.getElementById("chart");
  if (!workspaceMain || !chartFrame || !chartHost) {
    return;
  }

  const intrinsicHeight = Math.max(Number(chartHeightHint) || 0, chartHost.offsetHeight || 0, 760);
  chartFrame.style.minHeight = `${Math.ceil(intrinsicHeight)}px`;

  if (!workspaceSide || window.innerWidth <= 1080) {
    return;
  }

  const token = ++layoutSyncToken;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (token !== layoutSyncToken) {
        return;
      }
      const refreshedIntrinsicHeight = Math.max(Number(chartHeightHint) || 0, chartHost.offsetHeight || 0, 760);
      chartFrame.style.minHeight = `${Math.ceil(refreshedIntrinsicHeight)}px`;
      const deficit = workspaceSide.offsetHeight - workspaceMain.offsetHeight;
      if (deficit > 0) {
        chartFrame.style.minHeight = `${Math.ceil(refreshedIntrinsicHeight + deficit)}px`;
      }
      requestAnimationFrame(() => {
        if (token !== layoutSyncToken) {
          return;
        }
        const residual = workspaceSide.offsetHeight - workspaceMain.offsetHeight;
        if (residual > 1) {
          const currentHeight = Math.max(parseFloat(chartFrame.style.minHeight || "0") || 0, refreshedIntrinsicHeight);
          chartFrame.style.minHeight = `${Math.ceil(currentHeight + residual)}px`;
        }
      });
    });
  });
}


function layoutVariantKey(metal = state.metal, resultMode = state.resultMode, cobaltMode = state.cobaltMode) {
  return metal === "Co" ? `${metal}:${resultMode}:${cobaltMode}` : `${metal}:${resultMode}`;
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
    if (item === activeValue) {
      button.classList.add("active");
    }
    button.addEventListener("click", () => onSelect(item));
    container.appendChild(button);
  });
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
  renderThemeButtons();
  renderMetalButtons();
  renderCobaltModeButtons();
  renderAccessControls();
  renderResultButtons();
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
  document.getElementById("reference-qty-input").value = Math.round(payload.referenceQuantity);
  document.getElementById("chart-title").textContent =
    `${payload.metal} 7-Step Supply Chain / ${payload.year} / ${resultModeLabel(payload.resultMode)}${
      payload.metal === "Co" ? ` / ${cobaltModeLabel(state.cobaltMode)}` : ""
    }`;
  renderSummary(payload.stageSummary);
  renderNotes(payload.notes);
  renderDatasetStatus(payload.datasetStatus);
  renderOrderBoard(payload.stageControls);
  renderTables(payload.tables);
  document.getElementById("table-status").textContent =
    state.accessMode === "guest"
        ? "Diagnostics are hidden in guest mode."
      : state.resultMode === "baseline"
        ? `Diagnostics: Original only. Switch to First Optimization for optimizer-stage summaries.`
        : `Diagnostics: ${resultModeLabel(payload.resultMode)} stage summaries, bounds, source scaling, and A/B/G/NN coefficients.`;
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
  entry.innerHTML = `
    <div class="order-item-main">
      <span class="order-item-label">${escapeHtml(item.label)}</span>
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

function renderOrderBoard(stageControls) {
  const grid = document.getElementById("order-grid");
  grid.innerHTML = "";
  state.stageOrder.forEach((stage) => {
    const config = stageControls[stage];
    if (!config) {
      return;
    }
    const layout = currentLayoutState();
    const mode = layout.sortModes[stage] || config.sortMode || "size";
    layout.sortModes[stage] = mode;
    const items = getRenderedItems(stage, config);
    const specialPosition = getSpecialPosition(stage, config);
    const aggregateCount = getAggregateCount(stage, config);

    const card = document.createElement("section");
    card.className = "order-card";

    const head = document.createElement("div");
    head.className = "order-card-head";
    head.innerHTML = `
      <div>
        <strong>${stage}</strong>
        <span>${config.label.replace(`${stage} `, "")}</span>
      </div>
      <span>${items.length} items</span>
    `;
    card.appendChild(head);

    const toggle = document.createElement("div");
    toggle.className = "sort-toggle";
    const sortLabels = {
      size: "By Size",
      manual: "Manual",
      continent: "By Continent",
    };
    ["size", "manual", "continent"].forEach((sortMode) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "pill-btn";
      button.textContent = sortLabels[sortMode];
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
    card.appendChild(toggle);

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
    card.appendChild(specialControl);

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
      }
    }
    if (aggregateInput && !aggregateDisabled) {
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
    card.appendChild(aggregateControl);

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
    card.appendChild(list);
    grid.appendChild(card);
  });
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
    ? ["Supported Stage Groups", "SN Reduction", "SN Reduction Pct", "A / B / G / NN Rows"]
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
    const coefficientTotal = ["A Rows", "B Rows", "G Rows", "NN Rows"].reduce(
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

function buildStageOutcomeCardsHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">No rows available for the current selection.</div>`;
  }
  const isOptimizationView = Object.prototype.hasOwnProperty.call(rows[0], "Stage Group");
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
  const weightRows = ["alpha", "beta_pp", "beta_pn", "beta_np", "beta_nn"].map((label) => findRowByLabel(normalizedRows, label)).filter(Boolean);
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
    findItemByLabel(coveragePanel?.items, "A rows"),
    findItemByLabel(coveragePanel?.items, "B rows"),
    findItemByLabel(coveragePanel?.items, "G rows"),
    findItemByLabel(coveragePanel?.items, "NN rows"),
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
          "How many A / B / G / NN rows were emitted for this stage group.",
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

function buildProducerCoefficientSectionsHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">Coefficient rows are only available when First Optimization exposes factor outputs.</div>`;
  }

  const classSet = new Set(rows.map((row) => row.coefficient_class));
  const usesAbg = classSet.has("A") || classSet.has("B") || classSet.has("G") || classSet.has("NN");
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
  const transitionCounts = rows.reduce((accumulator, row) => {
    const key = row.transition_display || row.transition || "Transition";
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  const uniqueHsCodes = new Set(rows.map((row) => row.hs_code || "Unknown"));
  const largestExposureRow = rows.reduce((currentMax, row) => {
    if (!currentMax) {
      return row;
    }
    return Number(row.exposure) > Number(currentMax.exposure) ? row : currentMax;
  }, null);
  const busiestTransition = Object.entries(transitionCounts).sort((left, right) => right[1] - left[1])[0];
  const classOrder = usesAbg ? ["A", "B", "G", "NN"] : ["PP", "PN", "NP"];
  const classSummary = classOrder
    .filter((label) => classCounts[label])
    .map((label) => `${label} ${classCounts[label]}`)
    .join(" | ");
  const boundSummary = ["Lower", "Upper", "Interior"]
    .filter((label) => boundCounts[label])
    .map((label) => `${label} ${boundCounts[label]}`)
    .join(" | ");
  const introText = usesAbg
    ? "First Optimization exposes the synchronized coefficient output directly. Summary cards stay visible above the scrollable HS tables so the overall picture is readable before drilling down."
    : "First Optimization keeps producer-linked coefficients grouped by stage first and then by HS code. The overview cards summarize the active coefficient footprint before the detailed tables.";
  const summaryItems = [
    { label: "Coefficient Rows", value: rows.length, note: "All coefficient rows visible for the current selection." },
    { label: "Stage Groups", value: Object.keys(transitionCounts).length, note: busiestTransition ? `${busiestTransition[0]} is the largest group with ${busiestTransition[1]} rows.` : "" },
    { label: "HS Codes", value: uniqueHsCodes.size, note: "Unique HS codes represented across all grouped coefficient tables." },
    { label: "Class Mix", value: classSummary || "-", note: usesAbg ? "A / B / G / NN rows split by optimizer role." : "Producer-linked coefficient classes in this synchronized export." },
    { label: "Bound Status Mix", value: boundSummary || "-", note: "Interior rows stay away from bounds; Lower and Upper rows sit on Cmin or Cmax." },
    largestExposureRow
      ? {
          label: "Largest Exposure Row",
          value: largestExposureRow.exposure,
          note: `${largestExposureRow.transition_display || largestExposureRow.transition || "Transition"} | ${largestExposureRow.hs_code || "Unknown"} | ${largestExposureRow.producer_scope || "Unknown"} -> ${largestExposureRow.partner_scope || "Unknown"}`,
        }
      : null,
  ].filter(Boolean);
  const intro = usesAbg
    ? `
      <section class="producer-coefficient-intro">
        <p>${escapeHtml(introText)}</p>
        <div class="producer-summary-grid">
          ${summaryItems.map((item) => buildFactTileHtml(item)).join("")}
        </div>
        <div class="producer-legend-grid">
          <article class="producer-legend-item">
            <strong>A</strong>
            <span>Edge-level coefficient on a source-country to target-country trade row.</span>
          </article>
          <article class="producer-legend-item">
            <strong>B</strong>
            <span>Source-side balance coefficient tied to the exporting country for that HS code.</span>
          </article>
          <article class="producer-legend-item">
            <strong>G</strong>
            <span>Target-side balance coefficient tied to the importing country for that HS code.</span>
          </article>
          <article class="producer-legend-item">
            <strong>NN</strong>
            <span>Exporter-level coefficient for target-country exporters sending this HS code onward to non-target destinations.</span>
          </article>
          <article class="producer-legend-item">
            <strong>Exposure</strong>
            <span>The raw trade quantity attached to that coefficient row in the selected case.</span>
          </article>
          <article class="producer-legend-item">
            <strong>Exposure Share</strong>
            <span>The row exposure divided by the total raw trade quantity for that stage-triplet and HS code.</span>
          </article>
        </div>
      </section>
    `
    : `
      <section class="producer-coefficient-intro">
        <p>${escapeHtml(introText)}</p>
        <div class="producer-summary-grid">
          ${summaryItems.map((item) => buildFactTileHtml(item)).join("")}
        </div>
        <div class="producer-legend-grid">
          <article class="producer-legend-item">
            <strong>PP</strong>
            <span>Producer -> Producer. A pair-specific coefficient for a source producer shipping to a target producer.</span>
          </article>
          <article class="producer-legend-item">
            <strong>PN</strong>
            <span>Producer -> Non-producer. One shared coefficient for a source producer shipping this HS code to all non-target producers.</span>
          </article>
          <article class="producer-legend-item">
            <strong>NP</strong>
            <span>Non-producer -> Producer. One shared coefficient for a target producer receiving this HS code from all non-source exporters.</span>
          </article>
          <article class="producer-legend-item">
            <strong>Exposure</strong>
            <span>The raw import volume governed by that coefficient in the selected year.</span>
          </article>
          <article class="producer-legend-item">
            <strong>Exposure Share</strong>
            <span>The coefficient exposure divided by the total raw trade volume of that transition-HS series in the selected year.</span>
          </article>
        </div>
      </section>
    `;

  const stageGroups = new Map();
  rows.forEach((row) => {
    const stageKey = row.transition_display || row.transition || "Transition";
    if (!stageGroups.has(stageKey)) {
      stageGroups.set(stageKey, new Map());
    }
    const hsKey = row.hs_code || "Unknown";
    const hsGroups = stageGroups.get(stageKey);
    if (!hsGroups.has(hsKey)) {
      hsGroups.set(hsKey, []);
    }
    hsGroups.get(hsKey).push(row);
  });

  const sections = Array.from(stageGroups.entries())
    .map(([transition, hsGroups]) => {
      const hsTables = Array.from(hsGroups.entries())
        .map(([hsCode, hsRows]) => `
          <article class="producer-subtable">
            <div class="producer-subtable-head">
              <strong>${escapeHtml(hsCode)}</strong>
              <span>${escapeHtml(`${hsRows.length} coefficient row${hsRows.length === 1 ? "" : "s"}`)}</span>
            </div>
            <div class="producer-coefficient-scroll">
              ${buildTableHtml(
                hsRows.map((row) => ({
                  Class: row.coefficient_class,
                  "Producer Scope": row.producer_scope,
                  "Partner Scope": row.partner_scope,
                  Coefficient: row.coef_value,
                  Bounds: row.bounds,
                  "Bound Status": row.bound_status,
                  Exposure: row.exposure,
                  "Exposure Share": row.exposure_share,
                })),
              )}
            </div>
          </article>
        `)
        .join("");

      const rowCount = Array.from(hsGroups.values()).reduce((sum, value) => sum + value.length, 0);
      return `
        <section class="transition-group producer-coefficient-group">
          <div class="transition-group-head">
            <strong>${escapeHtml(transition)}</strong>
            <span>${escapeHtml(`${hsGroups.size} HS code${hsGroups.size === 1 ? "" : "s"} | ${rowCount} coefficient row${rowCount === 1 ? "" : "s"}`)}</span>
          </div>
          <div class="producer-subtable-grid">
            ${hsTables}
          </div>
        </section>
      `;
    })
    .join("");

  return `${intro}${sections}`;
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
  const board = document.getElementById("data-board");
  board.classList.toggle("is-hidden", state.accessMode !== "analyst");
  if (state.accessMode !== "analyst") {
    return;
  }
  const metricRows = tables.metrics || [];
  const stageRows = tables.stages || [];
  const parameterRows = tables.parameters || [];
  const producerCoefficientRows = tables.producerCoefficients || [];
  document.getElementById("metrics-table").innerHTML =
    metricRows.length && (Object.prototype.hasOwnProperty.call(metricRows[0], "Metric") || Object.prototype.hasOwnProperty.call(metricRows[0], "metric"))
      ? buildMetricSnapshotHtml(metricRows)
      : metricRows.length && Object.prototype.hasOwnProperty.call(metricRows[0], "baseline")
        ? buildCompareMetricsTableHtml(metricRows)
        : buildTableHtml(metricRows);
  document.getElementById("stage-table").innerHTML =
    stageRows.length && (Object.prototype.hasOwnProperty.call(stageRows[0], "Stage Group") || Object.prototype.hasOwnProperty.call(stageRows[0], "stage"))
      ? buildStageOutcomeCardsHtml(stageRows)
      : stageRows.length && Object.prototype.hasOwnProperty.call(stageRows[0], "baseline_unknown")
        ? buildCompareStageTableHtml(stageRows)
        : buildTableHtml(stageRows);
  document.getElementById("parameter-table").innerHTML =
    parameterRows.length && (Object.prototype.hasOwnProperty.call(parameterRows[0], "Parameter") || Object.prototype.hasOwnProperty.call(parameterRows[0], "parameter"))
      ? buildParameterOverviewHtml(parameterRows)
      : parameterRows.length && Object.prototype.hasOwnProperty.call(parameterRows[0], "baseline")
        ? buildCompareParameterTableHtml(parameterRows)
        : buildTableHtml(parameterRows);
  document.getElementById("producer-coefficient-table").innerHTML = buildProducerCoefficientSectionsHtml(producerCoefficientRows);
  document.getElementById("transition-table").innerHTML = buildTransitionCardsHtml(tables.transitions);
  document.getElementById("transition-note").textContent =
    tables.transitionNote ||
    (tables.transitions?.length
      ? "Stage diagnostics summarize each synchronized stage triplet without forcing the overview into wide tables."
      : "Stage diagnostics are only populated when First Optimization exposes synchronized optimizer outputs.");
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
