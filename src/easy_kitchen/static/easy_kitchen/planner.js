// Enhance the server-validated recipe selects with a keyboard-accessible autocomplete.
const searchTextById = new Map(
  Object.entries(JSON.parse(document.getElementById("recipe-search-data").textContent))
    .map(([id, text]) => [id, text.toLocaleLowerCase()])
);

document.querySelectorAll(".recipe-field").forEach((field) => {
  const select = field.querySelector("select");
  const input = field.querySelector(".recipe-search");
  const list = field.querySelector(".recipe-suggestions");
  const recipes = [...select.options].filter((option) => option.value);
  let active = -1;

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function choose(value) {
    select.value = value;
    input.value = select.selectedOptions[0].textContent;
    input.setCustomValidity("");
    input.focus();
    close();
  }

  function show() {
    const terms = input.value.toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const matches = recipes.filter((option) => {
      const text = searchTextById.get(option.value);
      return terms.every((term) => text.includes(term));
    });
    active = -1;
    input.removeAttribute("aria-activedescendant");
    list.replaceChildren(...matches.map((option, index) => {
      const item = document.createElement("li");
      item.setAttribute("role", "presentation");
      const button = document.createElement("button");
      button.type = "button";
      button.tabIndex = -1;
      button.id = `${input.id}-option-${index}`;
      button.className = "recipe-suggestion";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.textContent = option.textContent;
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => choose(option.value));
      item.append(button);
      return item;
    }));
    list.hidden = matches.length === 0;
    input.setAttribute("aria-expanded", String(matches.length > 0));
  }

  input.value = select.value ? select.selectedOptions[0].textContent : "";
  input.required = true;
  input.hidden = false;
  select.required = false;
  select.hidden = true;
  field.querySelector(".recipe-select-label").hidden = true;
  input.addEventListener("focus", show);
  input.addEventListener("input", () => {
    select.value = "";
    input.setCustomValidity(input.dataset.selectionMessage);
    show();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close();
      return;
    }
    if (event.key === "Enter" && !list.hidden && active >= 0) {
      event.preventDefault();
      list.querySelectorAll("button")[active].click();
      return;
    }
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    if (list.hidden) show();
    const options = [...list.querySelectorAll("button")];
    if (!options.length) return;
    const direction = event.key === "ArrowDown" ? 1 : -1;
    active = active < 0
      ? (direction === 1 ? 0 : options.length - 1)
      : (active + direction + options.length) % options.length;
    options.forEach((option, index) => option.setAttribute("aria-selected", String(index === active)));
    input.setAttribute("aria-activedescendant", options[active].id);
    options[active].scrollIntoView({block: "nearest"});
  });
  field.addEventListener("focusout", (event) => {
    if (!field.contains(event.relatedTarget)) close();
  });
});
