import { debounce } from "./ui_shell.js";

function ensureOverlay(frame) {
  let overlay = frame?.querySelector(".chart-overlay");
  if (!overlay && frame) {
    overlay = document.createElement("div");
    overlay.className = "chart-overlay";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    frame.appendChild(overlay);
  }
  return overlay;
}

export class FigureController {
  constructor({ chartId = "chart", frameSelector = ".chart-frame", config = {} } = {}) {
    this.chartId = chartId;
    this.frame = document.querySelector(frameSelector);
    this.config = config;
    window.addEventListener(
      "resize",
      debounce(() => {
        const host = document.getElementById(this.chartId);
        if (host && window.Plotly) {
          window.Plotly.Plots.resize(host);
        }
      }, 160),
    );
  }

  setLoading(message = "Updating chart") {
    const overlay = ensureOverlay(this.frame);
    if (overlay) {
      overlay.textContent = message;
      overlay.dataset.state = "loading";
    }
  }

  setError(message = "Unable to render chart") {
    const overlay = ensureOverlay(this.frame);
    if (overlay) {
      overlay.textContent = message;
      overlay.dataset.state = "error";
    }
  }

  clearOverlay() {
    const overlay = this.frame?.querySelector(".chart-overlay");
    if (overlay) {
      overlay.remove();
    }
  }

  async render(figure) {
    await window.Plotly.react(this.chartId, figure.data, figure.layout, this.config);
    this.clearOverlay();
  }
}
