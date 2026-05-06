export function debounce(callback, waitMs = 250) {
  let timer = null;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => callback(...args), waitMs);
  };
}

export function setShellBusy(isBusy, statusText = "") {
  document.body.classList.toggle("is-updating-figure", Boolean(isBusy));
  const chartFrame = document.querySelector(".chart-frame");
  if (chartFrame) {
    chartFrame.setAttribute("aria-busy", isBusy ? "true" : "false");
  }
  document.querySelectorAll("[data-stateful-control], .control-dock button, .control-dock input").forEach((node) => {
    if (node.id === "access-password-input") {
      return;
    }
    node.classList.toggle("is-pending", Boolean(isBusy));
  });
  const live = document.getElementById("chart-live-status");
  if (live && statusText) {
    live.textContent = statusText;
  }
}

export function setInlineStatus(element, message, kind = "neutral") {
  if (!element) {
    return;
  }
  element.textContent = message;
  element.dataset.status = kind;
}
