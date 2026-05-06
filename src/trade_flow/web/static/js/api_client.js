import { buildFigureRequestKey } from "./app_state.js";

function clonePayload(payload) {
  return typeof structuredClone === "function"
    ? structuredClone(payload)
    : JSON.parse(JSON.stringify(payload));
}

async function parseResponse(response, fallbackMessage) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || fallbackMessage);
    error.status = response.status;
    throw error;
  }
  return payload;
}

export class ApiClient {
  constructor() {
    this.figureCache = new Map();
    this.inFlight = null;
    this.activeController = null;
  }

  async getBootstrap() {
    const response = await fetch("/api/bootstrap", {
      headers: { Accept: "application/json" },
    });
    return parseResponse(response, "Failed to load bootstrap metadata.");
  }

  clearFigureCache() {
    this.figureCache.clear();
  }

  async requestFigure(request, options = {}) {
    const cacheKey = buildFigureRequestKey(request);
    const cacheable = Boolean(options.cacheable);
    if (cacheable && !options.force && this.figureCache.has(cacheKey)) {
      return clonePayload(this.figureCache.get(cacheKey));
    }

    if (this.inFlight && this.inFlight.key === cacheKey) {
      return this.inFlight.promise.then((payload) => clonePayload(payload));
    }

    if (this.activeController) {
      this.activeController.abort();
    }
    const controller = new AbortController();
    this.activeController = controller;

    const promise = fetch("/api/figure", {
      method: "POST",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    })
      .then((response) => parseResponse(response, "Figure request failed."))
      .then((payload) => {
        if (cacheable) {
          this.figureCache.set(cacheKey, clonePayload(payload));
        }
        return payload;
      })
      .finally(() => {
        if (this.inFlight && this.inFlight.key === cacheKey) {
          this.inFlight = null;
        }
        if (this.activeController === controller) {
          this.activeController = null;
        }
      });

    this.inFlight = { key: cacheKey, promise };
    return promise.then((payload) => clonePayload(payload));
  }
}
