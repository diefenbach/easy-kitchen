export function postJson(url, body) {
  const token = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? {"X-CSRFToken": token} : {}),
    },
    body: JSON.stringify(body),
  });
}

export function bindSortable(element, {draggable, datasetKey, field}) {
  if (!element) return;
  new globalThis.Sortable(element, {
    animation: 150,
    handle: ".drag-handle",
    draggable,
    onEnd() {
      const ids = [...element.querySelectorAll(draggable)].map((node) => Number(node.dataset[datasetKey]));
      postJson(element.dataset.reorderUrl, {[field]: ids});
    },
  });
}

document.body.addEventListener("htmx:configRequest", (event) => {
  const token = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  if (token) event.detail.headers["X-CSRFToken"] = token;
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
    const sortable = new globalThis.Sortable(container, {
      animation: 150,
      handle: ".drag-handle",
      draggable: "[data-list-id]",
      onEnd() {
        const ids = [...container.querySelectorAll("[data-list-id]")].map((card) => Number(card.dataset.listId));
        postJson(container.dataset.cardReorder, {[container.dataset.idField]: ids});
      },
    });
    container.addEventListener("htmx:beforeCleanupElement", (event) => {
      if (event.target === container) sortable.destroy();
    });
  });
}

document.addEventListener("htmx:load", bindPageElements);
document.addEventListener("htmx:historyRestore", bindPageElements);
bindPageElements();
