function postJson(url, body) {
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

document.querySelectorAll("[data-edit-toggle]").forEach((button) => {
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

document.querySelectorAll("[data-card-reorder]").forEach((container) => {
  new globalThis.Sortable(container, {
    animation: 150,
    handle: ".drag-handle",
    draggable: "[data-list-id]",
    onEnd() {
      const ids = [...container.querySelectorAll("[data-list-id]")].map((card) => Number(card.dataset.listId));
      postJson(container.dataset.cardReorder, {[container.dataset.idField]: ids});
    },
  });
});
