import "./recipe-actions.js";
import {bindSortable} from "./easykitchen.js";

for (const id of ["ingredients", "steps"]) {
  bindSortable(document.getElementById(id), {draggable: ".recipe-line", datasetKey: "lineId", field: "line_ids"});
}
