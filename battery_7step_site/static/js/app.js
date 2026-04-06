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


let layoutSyncToken = 0;

function syncWorkspaceLayout(chartHeightHint = state.lastChartHeight || 0) {
  const workspaceMain = document.querySelector(".workspace-main");
  const workspaceSide = document.querySelector(".workspace-side");
  const chartFrame = document.querySelector(".chart-frame");
  const chartHost = document.getElementById("chart");
  if (!workspaceMain || !workspaceSide || !chartFrame || !chartHost) {
    return;
  }

  const intrinsicHeight = Math.max(Number(chartHeightHint) || 0, chartHost.offsetHeight || 0, 760);
  chartFrame.style.minHeight = `${Math.ceil(intrinsicHeight)}px`;

  if (window.innerWidth <= 1080) {
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

async function loadFigure() {
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
  state.metal = payload.metal;
  state.cobaltMode = payload.cobaltMode || state.cobaltMode;
  state.resultMode = payload.resultMode;
  state.accessMode = payload.accessMode || state.accessMode;
  applyTheme(payload.theme);
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
        ? `Diagnostics: Original only / Figure: ${resultModeLabel(payload.resultMode)}`
        : `Diagnostics: Original vs ${resultModeLabel(payload.resultMode)} / Figure: ${resultModeLabel(payload.resultMode)}`;
  state.lastChartHeight = Number(payload.figure?.layout?.height || 0);
  await Plotly.react("chart", payload.figure.data, payload.figure.layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
  });
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

function buildMetricsTableHtml(rows) {
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

function buildStageTableHtml(rows) {
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

function buildParameterTableHtml(rows) {
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

function buildTransitionPanelHtml(panel) {
  return `
    <section class="transition-panel">
      <div class="transition-panel-head">
        <strong>${escapeHtml(panel.title || "Diagnostics")}</strong>
        <span>${escapeHtml(panel.subtitle || "")}</span>
      </div>
      ${buildKeyValueGrid(panel.items, panel.emptyText || "No rows were recorded for this panel.")}
    </section>
  `;
}

function buildTransitionCardHtml(row) {
  const signalLabel = row.signal_label || (row.has_signal ? "Tuned" : "No visible adjustment");
  const signalClass = row.signal_class || (row.has_signal ? "positive" : "neutral");
  const diagnosticPills = row.diagnostic_pills || [
    { label: "Stage Unknown", value: row.stage_unknown_total, tone: "unknown" },
    { label: "Non-Source", value: row.non_source_total, tone: "source" },
    { label: "Non-Target", value: row.non_target_total, tone: "target" },
  ];
  const diagnosticPanels = row.diagnostic_panels || [
    {
      title: "Priority Multipliers",
      subtitle: "Country-level scale shifts",
      items: row.multiplier_pairs,
      emptyText: "No country-level multipliers were applied for this HS folder.",
    },
    {
      title: "Applied Hyperparameters",
      subtitle: "Shared metal-level setting set",
      items: row.parameter_pairs,
      emptyText: "No hyperparameter signature was recorded.",
    },
  ];
  return `
    <article class="transition-card ${row.diagnostic_kind === "v3" ? "transition-card-v3" : ""}">
      <div class="transition-card-head">
        <div>
          <span class="transition-eyebrow">${escapeHtml(row.transition_display || row.transition || "")}</span>
          <h4>${escapeHtml(row.folder_display || row.folder_name || "")}</h4>
          <p>${escapeHtml(row.card_note || row.folder_group || "")}</p>
        </div>
        <span class="delta-badge ${signalClass}">${escapeHtml(signalLabel)}</span>
      </div>
      <div class="transition-pill-row">
        ${diagnosticPills.map((item) => buildTransitionMetricPill(item)).join("")}
      </div>
      <div class="transition-detail-grid">
        ${diagnosticPanels.map((panel) => buildTransitionPanelHtml(panel)).join("")}
      </div>
    </article>
  `;
}

function buildProducerCoefficientSectionsHtml(rows) {
  if (!rows || !rows.length) {
    return `<div class="order-empty">Producer-country coefficient rows are only available for First Optimization.</div>`;
  }

  const intro = `
    <section class="producer-coefficient-intro">
      <p>
        Only active for First Optimization. Each table keeps the V3 producer-linked coefficients visible outside the
        per-HS cards and groups them by post-trade stage first, then by HS code.
      </p>
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
            <span>${escapeHtml(`${hsGroups.size} HS code${hsGroups.size === 1 ? "" : "s"} | ${rowCount} producer-linked coefficient row${rowCount === 1 ? "" : "s"}`)}</span>
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
    return `<div class="order-empty">No per-HS diagnostics are available for the current selection.</div>`;
  }
  const groups = new Map();
  rows.forEach((row) => {
    const key = row.transition_display || row.transition || "Transition";
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(row);
  });
  return Array.from(groups.entries())
    .map(
      ([transition, groupRows]) => `
        <section class="transition-group">
          <div class="transition-group-head">
            <strong>${escapeHtml(transition)}</strong>
            <span>${escapeHtml(`${groupRows.length} HS folder${groupRows.length === 1 ? "" : "s"}`)}</span>
          </div>
          <div class="transition-card-grid">
            ${groupRows.map((row) => buildTransitionCardHtml(row)).join("")}
          </div>
        </section>
      `,
    )
    .join("");
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
    metricRows.length && Object.prototype.hasOwnProperty.call(metricRows[0], "baseline")
      ? buildMetricsTableHtml(metricRows)
      : buildTableHtml(metricRows);
  document.getElementById("stage-table").innerHTML =
    stageRows.length && Object.prototype.hasOwnProperty.call(stageRows[0], "baseline_unknown")
      ? buildStageTableHtml(stageRows)
      : buildTableHtml(stageRows);
  document.getElementById("parameter-table").innerHTML =
    parameterRows.length && Object.prototype.hasOwnProperty.call(parameterRows[0], "baseline")
      ? buildParameterTableHtml(parameterRows)
      : buildTableHtml(parameterRows);
  document.getElementById("producer-coefficient-table").innerHTML = buildProducerCoefficientSectionsHtml(producerCoefficientRows);
  document.getElementById("transition-table").innerHTML = buildTransitionCardsHtml(tables.transitions);
  document.getElementById("transition-note").textContent = tables.transitionNote || "";
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
  state.resultModes = payload.metadata.resultModes || ["baseline", "optimized_v3", "optimized_v4"];
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
      setStatus("Access denied", "warn");
      document.getElementById("notes-list").innerHTML = `<div class="note-item">${escapeHtml(error.message)}</div>`;
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
      setStatus("Access denied", "warn");
      document.getElementById("notes-list").innerHTML = `<div class="note-item">${escapeHtml(error.message)}</div>`;
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
  setStatus("Error", "warn");
  document.getElementById("notes-list").innerHTML = `<div class="note-item">${escapeHtml(error.message)}</div>`;
});
