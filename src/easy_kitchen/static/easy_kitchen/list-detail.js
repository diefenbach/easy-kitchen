import { postJson, showSaveError } from "./easykitchen.js";

import "./editor.js";
import { findSuggestions } from "./suggestions.js";

let suggestionSequence = 0;

function hideArticleSuggestions(field) {
  const list = field?.querySelector(".article-suggestions");
  const input = field?.querySelector("input[name=name]");
  if (list) {
    list.hidden = true;
    list
      .querySelectorAll('[aria-selected="true"]')
      .forEach((option) => option.setAttribute("aria-selected", "false"));
  }
  if (input) {
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }
}

function showArticleSuggestions(input) {
  const field = input.closest(".article-field");
  const list = field?.querySelector(".article-suggestions");
  if (!list) return;
  if (document.activeElement !== input) {
    hideArticleSuggestions(field);
    return;
  }
  if (!list.id) list.id = `article-suggestions-${++suggestionSequence}`;
  input.setAttribute("aria-controls", list.id);
  input.removeAttribute("aria-activedescendant");
  const query = input.value.trim().toLocaleLowerCase();
  const names = findSuggestions(
    document.querySelectorAll("#articles option"),
    (option) => option.value && option.value.toLocaleLowerCase().includes(query),
  ).map((option) => option.value);
  list.replaceChildren(
    ...names.map((name, index) => {
      const item = document.createElement("li");
      item.setAttribute("role", "presentation");
      const button = document.createElement("button");
      button.type = "button";
      button.tabIndex = -1;
      button.id = `${list.id}-option-${index}`;
      button.className = "article-suggestion";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.textContent = name;
      item.append(button);
      return item;
    }),
  );
  const open = names.length > 0;
  list.hidden = !open;
  input.setAttribute("aria-expanded", String(open));
}

document.addEventListener("focusin", (event) => {
  if (event.target.matches?.(".article-field input[name=name]"))
    showArticleSuggestions(event.target);
});
document.addEventListener("input", (event) => {
  if (event.target.matches?.(".article-field input[name=name]"))
    showArticleSuggestions(event.target);
});
document.addEventListener("focusout", (event) => {
  const field = event.target.closest?.(".article-field");
  if (!field || field.contains(event.relatedTarget)) return;
  hideArticleSuggestions(field);
});
document.addEventListener("mousedown", (event) => {
  if (event.target.closest?.(".article-suggestion")) event.preventDefault();
});
document.addEventListener("click", (event) => {
  const button = event.target.closest?.(".article-suggestion");
  if (!button) return;
  const field = button.closest(".article-field");
  const input = field.querySelector("input[name=name]");
  input.value = button.textContent;
  input.focus();
  hideArticleSuggestions(field);
});
document.addEventListener("keydown", (event) => {
  const input = event.target;
  if (event.isComposing || !input.matches?.(".article-field input[name=name]")) return;
  const field = input.closest(".article-field");
  const list = field.querySelector(".article-suggestions");
  if (event.key === "Escape") {
    hideArticleSuggestions(field);
    return;
  }
  if (event.key === "Enter" && !list.hidden && input.hasAttribute("aria-activedescendant")) {
    event.preventDefault();
    document.getElementById(input.getAttribute("aria-activedescendant"))?.click();
    return;
  }
  if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
  event.preventDefault();
  if (list.hidden) showArticleSuggestions(input);
  const options = [...list.querySelectorAll("button")];
  if (!options.length) return;
  const current = options.findIndex(
    (option) => option.id === input.getAttribute("aria-activedescendant"),
  );
  const direction = event.key === "ArrowDown" ? 1 : -1;
  const next =
    current < 0
      ? direction === 1
        ? 0
        : options.length - 1
      : (current + direction + options.length) % options.length;
  options.forEach((option, index) => option.setAttribute("aria-selected", String(index === next)));
  input.setAttribute("aria-activedescendant", options[next].id);
  options[next].scrollIntoView({ block: "nearest" });
});
document.addEventListener("htmx:oobAfterSwap", (event) => {
  if (event.detail.target.id === "item-form") {
    requestAnimationFrame(() => document.querySelector('#item-form input[name="name"]')?.focus());
  }
});

const boundLists = new WeakSet();

function bindShoppingList() {
  const itemsContainer = document.getElementById("items");
  if (!itemsContainer || boundLists.has(itemsContainer)) return;
  boundLists.add(itemsContainer);
  const checkedItemsToggle = document.getElementById("toggle-checked-items");
  const hideCompletedUrl = itemsContainer?.dataset.hideCompletedUrl;

  function setCompletedItemsHidden(hidden) {
    if (!itemsContainer || !checkedItemsToggle) return;
    itemsContainer.classList.toggle("hide-completed", hidden);
    itemsContainer.querySelectorAll(".shopping-item.checked").forEach((item) => {
      item.hidden = hidden;
    });
    const text = hidden
      ? checkedItemsToggle.dataset.labelShow
      : checkedItemsToggle.dataset.labelHide;
    const label = checkedItemsToggle.querySelector(".btn-label");
    if (label) label.textContent = text;
    checkedItemsToggle.setAttribute("aria-label", text);
    checkedItemsToggle.setAttribute("aria-pressed", hidden ? "true" : "false");
  }

  if (itemsContainer?.classList.contains("hide-completed")) {
    setCompletedItemsHidden(true);
  }

  checkedItemsToggle?.addEventListener("click", async () => {
    if (!itemsContainer || !hideCompletedUrl || checkedItemsToggle.disabled) return;
    const previous = itemsContainer.classList.contains("hide-completed");
    checkedItemsToggle.disabled = true;
    setCompletedItemsHidden(!previous);
    try {
      await postJson(hideCompletedUrl, { hide: !previous });
    } catch {
      setCompletedItemsHidden(previous);
      showSaveError();
    } finally {
      checkedItemsToggle.disabled = false;
    }
  });
  function completedItemCount() {
    return itemsContainer?.querySelectorAll(".shopping-item.checked").length ?? 0;
  }

  function syncDeleteCompletedControl() {
    const count = completedItemCount();
    const trigger = document.getElementById("delete-completed-trigger");
    if (trigger) trigger.disabled = count === 0;
    const body = document.getElementById("delete-completed-body");
    if (!body) return;
    if (count === 0) {
      body.textContent = "";
      return;
    }
    if (count === 1) {
      body.textContent = body.dataset.messageOne ?? "";
      return;
    }
    body.textContent = (body.dataset.messageMany ?? "").replaceAll("__COUNT__", String(count));
  }

  syncDeleteCompletedControl();
  itemsContainer.addEventListener("htmx:afterSwap", (event) => {
    if (event.target.closest?.("#items") || event.target.classList?.contains("shopping-item")) {
      syncDeleteCompletedControl();
    }
  });
}

document.addEventListener("htmx:load", bindShoppingList);
document.addEventListener("htmx:historyRestore", bindShoppingList);
bindShoppingList();
