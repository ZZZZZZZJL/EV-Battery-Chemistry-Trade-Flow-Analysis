export function stableStringify(value) {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
}

function metalIds(metadata) {
  return new Set((metadata.metals || []).map((metal) => metal.id));
}

function asBooleanParam(value) {
  return value === "1" || value === "true" || value === "yes";
}

function pickAllowed(params, name, allowed, fallback) {
  const value = params.get(name);
  return value && allowed.includes(value) ? value : fallback;
}

function pickYear(params, years, fallback) {
  const parsed = Number(params.get("year"));
  return years.includes(parsed) ? parsed : fallback;
}

function pickReferenceQuantity(params, fallback) {
  const parsed = Number(params.get("ref"));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function sanitizeFigureRequest(request) {
  const sanitized = { ...request };
  delete sanitized.accessPassword;
  return sanitized;
}

export function buildFigureRequestKey(request) {
  return stableStringify(sanitizeFigureRequest(request));
}

export function hydrateStateFromUrl(state, metadata) {
  const params = new URLSearchParams(window.location.search);
  const ids = metalIds(metadata);
  const metal = params.get("metal");
  if (metal && ids.has(metal)) {
    state.metal = metal;
  }
  state.year = pickYear(params, metadata.years || [], state.year);
  state.theme = pickAllowed(params, "theme", metadata.themes || [], state.theme);
  state.resultMode = pickAllowed(params, "result", metadata.resultModes || [], state.resultMode);
  state.cobaltMode = pickAllowed(params, "cobalt", metadata.cobaltModes || [], state.cobaltMode);
  state.referenceQty = pickReferenceQuantity(params, state.referenceQty);

  const s7Mode = params.get("s7");
  if (s7Mode === "country") {
    state.s7Display = { country: true, chemistry: false, aggregateNmcNca: false };
  } else if (s7Mode === "chemistry_only") {
    state.s7Display.country = false;
    state.s7Display.chemistry = true;
  } else if (s7Mode === "chemistry") {
    state.s7Display.country = true;
    state.s7Display.chemistry = true;
  }
  state.s7Display.aggregateNmcNca = Boolean(state.s7Display.chemistry && asBooleanParam(params.get("s7Merge")));
}

export function syncStateToUrl(state) {
  const params = new URLSearchParams(window.location.search);
  const s7Mode = state.s7Display.country && state.s7Display.chemistry
    ? "chemistry"
    : state.s7Display.chemistry
      ? "chemistry_only"
      : "country";
  params.set("metal", state.metal);
  params.set("year", String(state.year));
  params.set("result", state.resultMode);
  params.set("theme", state.theme);
  params.set("ref", String(Math.round(state.referenceQty)));
  params.set("s7", s7Mode);
  if (state.metal === "Co") {
    params.set("cobalt", state.cobaltMode);
  } else {
    params.delete("cobalt");
  }
  if (state.s7Display.chemistry && state.s7Display.aggregateNmcNca) {
    params.set("s7Merge", "1");
  } else {
    params.delete("s7Merge");
  }
  params.delete("access");
  params.delete("password");
  const query = params.toString();
  const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState(null, "", nextUrl);
}
