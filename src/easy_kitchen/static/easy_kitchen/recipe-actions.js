const boundActions = new WeakSet();

function bindRecipeActions() {
  for (const id of ["add-to-planner-modal", "add-to-list-modal"]) {
    const modal = document.getElementById(id);
    if (!modal || boundActions.has(modal)) continue;
    boundActions.add(modal);
    function selectRecipe(event) {
      const trigger = event.relatedTarget;
      const action = trigger?.dataset.recipeAction;
      if (!action) return;
      const form = modal.querySelector("form");
      form.reset();
      form.setAttribute("action", action);
      modal.querySelector("[data-recipe-title]").textContent = trigger.dataset.recipeTitle;
      form.querySelector('button[type="submit"]').disabled = false;
    }
    modal.addEventListener("show.bs.modal", selectRecipe);
    modal.addEventListener("shown.bs.modal", (event) => {
      if (modal.querySelector('button[type="submit"]').disabled) selectRecipe(event);
      modal.querySelector('input:not([type="hidden"]), select')?.focus();
    });
    if (modal.dataset.openOnError === "true") {
      globalThis.bootstrap.Modal.getOrCreateInstance(modal).show();
    }
  }

  const filter = document.getElementById("recipe-favorites");
  if (filter && !boundActions.has(filter)) {
    boundActions.add(filter);
    filter.addEventListener("change", (event) => {
      event.target.form.requestSubmit();
    });
  }
}

document.addEventListener("htmx:load", bindRecipeActions);
document.addEventListener("htmx:historyRestore", bindRecipeActions);
bindRecipeActions();
