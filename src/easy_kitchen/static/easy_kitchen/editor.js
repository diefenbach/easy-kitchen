const boundEditors = new WeakMap();
let activeEditor = null;

function bindCollectionEditor() {
  const editor = document.querySelector("#recipe-editor-form, #list-editor-form");
  if (!editor) { activeEditor = null; return; }
  if (boundEditors.has(editor)) { activeEditor = boundEditors.get(editor); return; }
  const state = {editor, dirty: editor.dataset.bound === "true", sortables: []};
  boundEditors.set(editor, state);
  activeEditor = state;
  document.querySelector("[data-editor-delete]")?.addEventListener("submit", () => { state.dirty = false; });
  editor.addEventListener("input", () => { state.dirty = true; });
  editor.addEventListener("change", () => { state.dirty = true; });
  editor.addEventListener("submit", () => {
    if (!globalThis.htmx) state.dirty = false;
  });
  editor.addEventListener("htmx:beforeCleanupElement", (event) => {
    if (event.target === editor) state.sortables.forEach((sortable) => sortable.destroy());
  });
  document.querySelectorAll("[data-editor-cancel]").forEach((link) => {
    link.addEventListener("click", () => {
      if (!globalThis.htmx) state.dirty = false;
    });
  });
  for (const section of editor.querySelectorAll("[data-editor-lines]")) {
    const prefix = section.dataset.editorLines;
    const container = section.querySelector("[data-editor-rows]");
    const total = section.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
    const max = Number(section.querySelector(`[name="${prefix}-MAX_NUM_FORMS"]`).value);
    const add = section.querySelector("[data-editor-add]");
    const rows = () => [...container.querySelectorAll(".editor-line:not([hidden])")];
    function reorder() {
      const visible = rows();
      visible.forEach((row, index) => {
        row.querySelector('[name$="-ORDER"]').value = index + 1;
        row.querySelector("[data-editor-number]").textContent = `${index + 1}.`;
        row.querySelector("[data-editor-up]").disabled = index === 0;
        row.querySelector("[data-editor-down]").disabled = index === visible.length - 1;
      });
      add.disabled = Number(total.value) >= max;
    }
    add.addEventListener("click", () => {
      const html = section.querySelector("[data-editor-empty]").innerHTML.replaceAll("__prefix__", total.value);
      container.insertAdjacentHTML("beforeend", html);
      total.value = Number(total.value) + 1;
      reorder();
      container.lastElementChild.querySelector('input:not([type="hidden"]), textarea').focus();
      state.dirty = true;
    });
    container.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      const row = button?.closest(".editor-line");
      if (!row) return;
      const visible = rows();
      const index = visible.indexOf(row);
      if (button.hasAttribute("data-editor-remove")) {
        row.querySelector('[name$="-DELETE"]').value = "on";
        row.hidden = true;
        row.querySelectorAll("input:not([type=hidden]), textarea").forEach((field) => { field.required = false; });
      } else if (button.hasAttribute("data-editor-up") && index > 0) {
        container.insertBefore(row, visible[index - 1]);
      } else if (button.hasAttribute("data-editor-down") && index < visible.length - 1) {
        container.insertBefore(visible[index + 1], row);
      } else return;
      reorder();
      state.dirty = true;
    });
    state.sortables.push(new globalThis.Sortable(container, {
      handle: ".editor-drag", draggable: ".editor-line:not([hidden])", animation: 150,
      onEnd() { reorder(); state.dirty = true; },
    }));
    reorder();
  }
}

window.addEventListener("beforeunload", (event) => {
  if (!activeEditor?.editor.isConnected || !activeEditor.dirty) return;
  event.preventDefault();
  event.returnValue = "";
});
document.addEventListener("htmx:beforeSwap", (event) => {
  if (event.detail.xhr.status === 422 && (event.detail.xhr.getResponseHeader("X-Recipe-Editor") === "true" || event.detail.xhr.getResponseHeader("X-List-Editor") === "true")) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
document.addEventListener("htmx:load", bindCollectionEditor);
document.addEventListener("htmx:historyRestore", bindCollectionEditor);
bindCollectionEditor();

// Keep the viewport stable when opening, saving or cancelling a collection editor.
const editorRequests = new WeakMap();
document.addEventListener("htmx:beforeRequest", (event) => {
  if (event.detail.elt.matches("[data-editor-open], [data-editor-cancel], #recipe-editor-form, #list-editor-form")) {
    editorRequests.set(event.detail.xhr, {});
  }
});
document.addEventListener("htmx:beforeSwap", (event) => {
  const position = editorRequests.get(event.detail.xhr);
  if (!position || !event.detail.shouldSwap) return;
  const root = document.documentElement;
  Object.assign(position, {
    x: window.scrollX, y: window.scrollY,
    anchor: root.style.overflowAnchor, behavior: root.style.scrollBehavior,
  });
  root.style.overflowAnchor = "none";
  root.style.scrollBehavior = "auto";
});
function restoreEditorPosition(position) {
  if (position?.y !== undefined) window.scrollTo({left: position.x, top: position.y, behavior: "instant"});
}
document.addEventListener("htmx:afterSwap", (event) => {
  restoreEditorPosition(editorRequests.get(event.detail.xhr));
});
document.addEventListener("htmx:afterSettle", (event) => {
  const position = editorRequests.get(event.detail.xhr);
  if (position?.y === undefined) return;
  requestAnimationFrame(() => {
    restoreEditorPosition(position);
    requestAnimationFrame(() => {
      restoreEditorPosition(position);
      document.documentElement.style.overflowAnchor = position.anchor;
      document.documentElement.style.scrollBehavior = position.behavior;
      editorRequests.delete(event.detail.xhr);
    });
  });
});
