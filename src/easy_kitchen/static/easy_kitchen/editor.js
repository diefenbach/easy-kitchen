import { createSortable } from "./easykitchen.js";

const boundEditors = new WeakMap();
let activeEditor = null;

function bindCollectionEditor() {
  const editor = document.querySelector("#recipe-editor-form, #list-editor-form");
  if (!editor) {
    activeEditor = null;
    return;
  }
  if (boundEditors.has(editor)) {
    activeEditor = boundEditors.get(editor);
    return;
  }
  const state = { editor, dirty: editor.dataset.bound === "true" };
  boundEditors.set(editor, state);
  activeEditor = state;
  document.querySelector("[data-editor-delete]")?.addEventListener("submit", () => {
    state.dirty = false;
  });
  editor.addEventListener("input", () => {
    state.dirty = true;
  });
  editor.addEventListener("change", () => {
    state.dirty = true;
  });
  editor.addEventListener("submit", () => {
    if (!globalThis.htmx) state.dirty = false;
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
      const html = section
        .querySelector("[data-editor-empty]")
        .innerHTML.replaceAll("__prefix__", total.value);
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
      if (editor.getAttribute("aria-busy") === "true") return;
      const visible = rows();
      const index = visible.indexOf(row);
      if (button.hasAttribute("data-editor-remove")) {
        row.querySelector('[name$="-DELETE"]').value = "on";
        row.hidden = true;
        row.querySelectorAll("input:not([type=hidden]), textarea").forEach((field) => {
          field.required = false;
        });
      } else if (button.hasAttribute("data-editor-up") && index > 0) {
        container.insertBefore(row, visible[index - 1]);
      } else if (button.hasAttribute("data-editor-down") && index < visible.length - 1) {
        container.insertBefore(visible[index + 1], row);
      } else return;
      reorder();
      state.dirty = true;
    });
    const sortable = createSortable(container, {
      handle: ".editor-drag",
      draggable: ".editor-line:not([hidden])",
      onEnd() {
        reorder();
        state.dirty = true;
      },
    });
    editor.addEventListener("easykitchen:pending", (event) => {
      sortable.option("disabled", event.detail);
    });
    reorder();
  }
}

function hasUnsavedChanges() {
  return activeEditor?.editor.isConnected && activeEditor.dirty;
}

// HTMX owns same-document history entries. Tag them through its public events so
// a rejected Back/Forward action can return to the original entry without a swap.
let historyPosition = history.state?.easyKitchenPosition ?? 0;
let restoringHistoryPosition = false;
function markHistoryPosition() {
  history.replaceState({ ...history.state, easyKitchenPosition: historyPosition }, "");
}
markHistoryPosition();
document.addEventListener("htmx:beforeHistoryUpdate", markHistoryPosition);
document.addEventListener("htmx:pushedIntoHistory", () => {
  historyPosition += 1;
  markHistoryPosition();
});
document.addEventListener("htmx:replacedInHistory", markHistoryPosition);
document.addEventListener("htmx:historyRestore", markHistoryPosition);
window.addEventListener(
  "popstate",
  (event) => {
    if (restoringHistoryPosition) {
      event.stopImmediatePropagation();
      restoringHistoryPosition = false;
      markHistoryPosition();
      return;
    }
    const destination = event.state?.easyKitchenPosition;
    if (!Number.isInteger(destination)) return;
    if (hasUnsavedChanges() && !window.confirm(activeEditor.editor.dataset.discardMessage)) {
      event.stopImmediatePropagation();
      const distance = historyPosition - destination;
      if (distance) {
        restoringHistoryPosition = true;
        history.go(distance);
      }
      return;
    }
    historyPosition = destination;
  },
  true,
);

document.addEventListener("htmx:beforeRequest", (event) => {
  if (!hasUnsavedChanges() || !event.detail.target?.contains(activeEditor.editor)) return;
  if (event.detail.elt.matches("#recipe-editor-form, #list-editor-form, [data-editor-cancel]"))
    return;
  if (!window.confirm(activeEditor.editor.dataset.discardMessage)) event.preventDefault();
});

window.addEventListener("beforeunload", (event) => {
  if (!hasUnsavedChanges()) return;
  event.preventDefault();
  event.returnValue = "";
});
const validationFiles = new WeakMap();
document.addEventListener("htmx:beforeSwap", (event) => {
  if (
    event.detail.xhr.status === 422 &&
    (event.detail.xhr.getResponseHeader("X-Recipe-Editor") === "true" ||
      event.detail.xhr.getResponseHeader("X-List-Editor") === "true")
  ) {
    const files = [...(activeEditor?.editor.querySelectorAll('input[type="file"]') ?? [])].map(
      (input) => ({ name: input.name, files: [...input.files] }),
    );
    validationFiles.set(event.detail.xhr, files);
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
document.addEventListener("htmx:afterSwap", (event) => {
  for (const saved of validationFiles.get(event.detail.xhr) ?? []) {
    const input = [...document.querySelectorAll('input[type="file"]')].find(
      (field) => field.name === saved.name,
    );
    if (!input) continue;
    const transfer = new DataTransfer();
    saved.files.forEach((file) => transfer.items.add(file));
    input.files = transfer.files;
  }
  validationFiles.delete(event.detail.xhr);
});
document.addEventListener("htmx:load", bindCollectionEditor);
document.addEventListener("htmx:historyRestore", bindCollectionEditor);
bindCollectionEditor();

// Keep the viewport stable when opening, saving or cancelling the recipe editor.
const editorRequests = new WeakMap();
document.addEventListener("htmx:beforeRequest", (event) => {
  if (
    event.detail.elt.matches(
      "[data-editor-open], [data-editor-cancel], #recipe-editor-form, #list-editor-form",
    )
  ) {
    editorRequests.set(event.detail.xhr, {});
  }
});
document.addEventListener("htmx:beforeSwap", (event) => {
  const position = editorRequests.get(event.detail.xhr);
  if (!position || !event.detail.shouldSwap) return;
  const root = document.documentElement;
  Object.assign(position, {
    x: window.scrollX,
    y: window.scrollY,
    anchor: root.style.overflowAnchor,
    behavior: root.style.scrollBehavior,
  });
  root.style.overflowAnchor = "none";
  root.style.scrollBehavior = "auto";
});
function restoreEditorPosition(position) {
  if (position?.y !== undefined)
    window.scrollTo({ left: position.x, top: position.y, behavior: "instant" });
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
