import {bindSortable, postJson} from "./easykitchen.js";

function showArticleSuggestions(input) {
  const field = input.closest(".article-field");
  const list = field?.querySelector(".article-suggestions");
  if (!list) return;
  const query = input.value.trim().toLocaleLowerCase();
  const names = [...document.querySelectorAll("#articles option")]
    .map((option) => option.value)
    .filter((name) => name && name.toLocaleLowerCase().includes(query));
  list.replaceChildren(...names.map((name) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "article-suggestion";
    button.setAttribute("role", "option");
    button.textContent = name;
    item.append(button);
    return item;
  }));
  const open = names.length > 0;
  list.hidden = !open;
  input.setAttribute("aria-expanded", open ? "true" : "false");
}

document.addEventListener("focusin", (event) => {
  if (event.target.matches?.(".article-field input[name=name]")) showArticleSuggestions(event.target);
});
document.addEventListener("input", (event) => {
  if (event.target.matches?.(".article-field input[name=name]")) showArticleSuggestions(event.target);
});
document.addEventListener("focusout", (event) => {
  const field = event.target.closest?.(".article-field");
  if (!field || field.contains(event.relatedTarget)) return;
  const list = field.querySelector(".article-suggestions");
  if (list) list.hidden = true;
  if (event.target.matches?.("input[name=name]")) event.target.setAttribute("aria-expanded", "false");
});
document.addEventListener("mousedown", (event) => {
  const button = event.target.closest?.(".article-suggestion");
  if (!button) return;
  const field = button.closest(".article-field");
  const input = field?.querySelector("input[name=name]");
  if (!input) return;
  event.preventDefault();
  input.value = button.textContent;
  field.querySelector(".article-suggestions").hidden = true;
  input.setAttribute("aria-expanded", "false");
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !event.target.matches?.(".article-field input[name=name]")) return;
  const list = event.target.closest(".article-field").querySelector(".article-suggestions");
  if (!list) return;
  list.hidden = true;
  event.target.setAttribute("aria-expanded", "false");
});
document.addEventListener("reset", (event) => {
  const input = event.target.querySelector?.(".article-field input[name=name]");
  if (input) requestAnimationFrame(() => showArticleSuggestions(input));
}, true);

const itemsContainer = document.getElementById("items");
const checkedItemsToggle = document.getElementById("toggle-checked-items");
const hideCompletedUrl = itemsContainer?.dataset.hideCompletedUrl;

function setCompletedItemsHidden(hidden) {
  if (!itemsContainer || !checkedItemsToggle) return;
  itemsContainer.classList.toggle("hide-completed", hidden);
  itemsContainer.querySelectorAll(".shopping-item.checked").forEach((item) => {
    item.hidden = hidden;
  });
  const text = hidden ? checkedItemsToggle.dataset.labelShow : checkedItemsToggle.dataset.labelHide;
  const label = checkedItemsToggle.querySelector(".btn-label");
  if (label) label.textContent = text;
  checkedItemsToggle.setAttribute("aria-label", text);
  checkedItemsToggle.setAttribute("aria-pressed", hidden ? "true" : "false");
}

if (itemsContainer?.classList.contains("hide-completed")) {
  setCompletedItemsHidden(true);
}

checkedItemsToggle?.addEventListener("click", () => {
  const hidden = !itemsContainer.classList.contains("hide-completed");
  setCompletedItemsHidden(hidden);
  if (hideCompletedUrl) postJson(hideCompletedUrl, {hide: hidden});
});
bindSortable(itemsContainer, {draggable: ".shopping-item", datasetKey: "itemId", field: "item_ids"});
