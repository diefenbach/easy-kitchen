export async function postJson(url, body) {
  const token = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const response = await fetch(url, {
    method: "POST",
    redirect: "error",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-CSRFToken": token } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response;
}

export function showSaveError() {
  const alert = document.getElementById("save-error");
  if (alert) {
    alert.setAttribute("role", "alert");
    alert.hidden = false;
  }
}

// Sortable instances own their cleanup, regardless of the calling page.
export function createSortable(element, options) {
  if (!element) return;
  const sortable = new globalThis.Sortable(element, { animation: 150, ...options });
  function cleanup(event) {
    if (event.target !== element) return;
    sortable.destroy();
    element.removeEventListener("htmx:beforeCleanupElement", cleanup);
  }
  element.addEventListener("htmx:beforeCleanupElement", cleanup);
  return sortable;
}

export function bindSortable(
  element,
  { draggable, datasetKey, field, url = element?.dataset.reorderUrl },
) {
  let previousOrder = [];
  let pending = false;
  const cards = () => [...element.querySelectorAll(draggable)];
  function syncControls() {
    const nodes = cards();
    nodes.forEach((node, index) => {
      const up = node.querySelector("[data-card-up]");
      const down = node.querySelector("[data-card-down]");
      if (up) up.disabled = pending || index === 0;
      if (down) down.disabled = pending || index === nodes.length - 1;
    });
  }
  async function saveOrder(focusButton) {
    pending = true;
    sortable.option("disabled", true);
    element.setAttribute("aria-busy", "true");
    syncControls();
    try {
      await postJson(url, { [field]: cards().map((node) => Number(node.dataset[datasetKey])) });
    } catch {
      previousOrder
        .filter((node) => node.parentElement === element)
        .forEach((node) => element.append(node));
      showSaveError();
    } finally {
      pending = false;
      sortable.option("disabled", false);
      element.removeAttribute("aria-busy");
      syncControls();
      if (focusButton) {
        const card = focusButton.closest(draggable);
        (focusButton.disabled
          ? (card.querySelector("[data-card-up]:enabled, [data-card-down]:enabled") ??
            card.querySelector(".drag-handle"))
          : focusButton
        )?.focus();
      }
    }
  }
  const sortable = createSortable(element, {
    handle: ".drag-handle",
    draggable,
    onStart() {
      previousOrder = [...element.children];
    },
    onEnd(event) {
      if (event.oldDraggableIndex !== event.newDraggableIndex) saveOrder();
    },
  });
  element.addEventListener("click", (event) => {
    const button = event.target.closest("[data-card-up], [data-card-down]");
    if (!button || pending) return;
    const card = button.closest(draggable);
    const nodes = cards();
    const index = nodes.indexOf(card);
    const up = button.hasAttribute("data-card-up");
    const neighbor = nodes[index + (up ? -1 : 1)];
    if (!neighbor) return;
    previousOrder = [...element.children];
    if (up) element.insertBefore(card, neighbor);
    else element.insertBefore(neighbor, card);
    saveOrder(button);
  });
  syncControls();
  return sortable;
}

document.body.addEventListener("htmx:configRequest", (event) => {
  const token = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  if (token) event.detail.headers["X-CSRFToken"] = token;
});

// Only swap explicitly marked item validation responses; leave other HTTP errors alone.
document.addEventListener("htmx:beforeSwap", (event) => {
  if (
    event.detail.xhr.status === 422 &&
    event.detail.xhr.getResponseHeader("X-Item-Form") === "true"
  ) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

const boundPageElements = new WeakSet();

function bindPageElements() {
  document.querySelectorAll("[data-edit-toggle]").forEach((button) => {
    if (boundPageElements.has(button)) return;
    boundPageElements.add(button);
    button.addEventListener("click", () => {
      const editing = document.body.classList.toggle("editing");
      const icon = button.querySelector("i");
      button.setAttribute("aria-pressed", editing ? "true" : "false");
      const text = editing ? button.dataset.labelOn : button.dataset.labelOff;
      button.setAttribute("aria-label", text);
      const label = button.querySelector(".btn-label");
      if (label) label.textContent = text;
      icon.classList.remove(editing ? icon.dataset.iconOff : icon.dataset.iconOn);
      icon.classList.add(editing ? icon.dataset.iconOn : icon.dataset.iconOff);
    });
  });

  document.querySelectorAll("[data-autohide]").forEach((element) => {
    if (boundPageElements.has(element)) return;
    boundPageElements.add(element);
    const delay = Number(element.dataset.autohide) || 3000;
    window.setTimeout(() => element.remove(), delay + 800);
  });

  document.querySelectorAll("[data-card-reorder]").forEach((container) => {
    if (boundPageElements.has(container)) return;
    boundPageElements.add(container);
    bindSortable(container, {
      draggable: "[data-list-id]",
      datasetKey: "listId",
      field: container.dataset.idField,
      url: container.dataset.cardReorder,
    });
  });
}

document.addEventListener("htmx:load", bindPageElements);
document.addEventListener("htmx:historyRestore", bindPageElements);
bindPageElements();

// Request data has already been collected at beforeRequest. Lock controls only
// now, so disabled fields are still included in this request's submitted values.
const pendingForms = new WeakMap();
const draftForms =
  "#recipe-editor-form, #list-editor-form, #article-editor-form, #department-editor-form, #item-form form";
document.addEventListener("htmx:beforeRequest", (event) => {
  if (
    document.querySelector(
      '#recipe-editor-form[aria-busy="true"], #list-editor-form[aria-busy="true"], #article-editor-form[aria-busy="true"], #department-editor-form[aria-busy="true"]',
    ) &&
    event.detail.target?.matches("main")
  ) {
    event.preventDefault();
    return;
  }
  const form = event.detail.elt;
  if (!form.matches(draftForms)) return;
  const editor = !form.closest("#item-form");
  const controls = [
    ...(editor
      ? document.querySelectorAll("main input, main textarea, main select, main button")
      : form.querySelectorAll("input, textarea, select, button")),
  ];
  const disabled = controls.map((control) => control.disabled);
  const links = editor ? [...document.querySelectorAll("[data-editor-cancel]")] : [];
  pendingForms.set(event.detail.xhr, { form, controls, disabled, links });
  controls.forEach((control) => {
    control.disabled = true;
  });
  links.forEach((link) => link.setAttribute("aria-disabled", "true"));
  form.setAttribute("aria-busy", "true");
  form.dispatchEvent(new CustomEvent("easykitchen:pending", { detail: true }));
});
document.addEventListener("htmx:afterRequest", (event) => {
  if (event.detail.successful) {
    const alert = document.getElementById("save-error");
    if (alert) alert.hidden = true;
  }
  const state = pendingForms.get(event.detail.xhr);
  if (!state) return;
  state.controls.forEach((control, index) => {
    control.disabled = state.disabled[index];
  });
  state.links.forEach((link) => link.removeAttribute("aria-disabled"));
  state.form.removeAttribute("aria-busy");
  state.form.dispatchEvent(new CustomEvent("easykitchen:pending", { detail: false }));
  pendingForms.delete(event.detail.xhr);
});
document.addEventListener(
  "click",
  (event) => {
    if (!event.target.closest('[data-editor-cancel][aria-disabled="true"]')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  },
  true,
);
for (const name of ["htmx:responseError", "htmx:sendError", "htmx:timeout"]) {
  document.addEventListener(name, (event) => {
    if (event.detail.requestConfig?.verb !== "get") showSaveError();
  });
}
function clearPrivateHistory() {
  try {
    localStorage.removeItem("htmx-history-cache");
  } catch {
    // Storage may be unavailable in restricted browser profiles.
  }
}
// Remove legacy snapshots on entry as well as when ending the session.
clearPrivateHistory();
document.addEventListener("submit", (event) => {
  if (event.target.matches("[data-logout]")) clearPrivateHistory();
});
