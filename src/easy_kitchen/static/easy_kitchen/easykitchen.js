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

// Optional drag support owns its cleanup, regardless of the calling page.
export function createSortable(element, options) {
  if (!element || typeof globalThis.Sortable !== "function") return;
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
  const sortable = createSortable(element, {
    handle: ".drag-handle",
    draggable,
    onStart() {
      previousOrder = [...element.children];
    },
    async onEnd(event) {
      if (event.oldDraggableIndex === event.newDraggableIndex) return;
      const ids = [...element.querySelectorAll(draggable)].map((node) =>
        Number(node.dataset[datasetKey]),
      );
      sortable.option("disabled", true);
      element.setAttribute("aria-busy", "true");
      try {
        await postJson(url, { [field]: ids });
      } catch {
        previousOrder
          .filter((node) => node.parentElement === element)
          .forEach((node, index) => {
            element.insertBefore(node, element.children[index] ?? null);
          });
        showSaveError();
      } finally {
        sortable.option("disabled", false);
        element.removeAttribute("aria-busy");
      }
    },
  });
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
