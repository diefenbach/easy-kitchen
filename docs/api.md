# REST API

Base path: `/api/v1/`. Authentication is `Authorization: Token <token>`, not Bearer. Every list, recipe, and meal-plan query is limited to the token owner.

Create a token through Django admin or:

```sh
uv run --env-file .env python src/manage.py drf_create_token <username>
```

Swagger UI is public at `/api/v1/`. The OpenAPI document is at `/api/v1/schema/`. List and recipe operations stay authenticated.

All business actions listed here have MCP equivalents, including detail reads, root deletion, ordering, collection replacement and batch imports. See {doc}`mcp` for tool names and input examples. Automated tests check that every registered REST business action maps to an available MCP tool.

## Collection search and paging

Collection GET routes return JSON arrays as before, with a bounded page of **50 records by default**. Pass `limit` (1–200) and `offset` (0–2,147,483,647) for explicit pages. To read all matches, increase offset by the requested limit until a page contains fewer records than the limit. Filtering happens before paging; results retain their normal stable ordering. An offset beyond the results returns `[]`.

| Collection | Additional query parameters |
| --- | --- |
| `/api/v1/recipes/` | `q` searches titles, descriptions and ingredient names; `is_favorite=true/false` filters favorite state; `summary=true` omits ingredients and steps. |
| `/api/v1/shopping-lists/` | `q` searches titles; `date_from` and `date_to` select inclusive ISO date bounds; `summary=true` omits items. |
| `/api/v1/shopping-items/` | `q` searches names; `checked=true/false` filters state; `list_id` selects an owned list. |
| `/api/v1/articles/` | `q` searches names; `department` selects an owned code/name, with an empty string selecting unassigned defaults. |
| `/api/v1/departments/` | `q` searches codes, stored names and the current translated labels. |

All collections accept `q`, `limit` and `offset`. Search is case-insensitive and requires every whitespace-separated term to match. Omitted boolean filters include both states. Invalid ranges, flags, unknown parameters and limits are rejected; a foreign or missing item-filter `list_id` returns 404. All searches remain scoped to the authenticated user.

`summary=false` is the default, preserving the previous full-record shape within each page. Compact recipe/list pages skip loading their child collections; detail GET routes always return the full object. For example, `GET /api/v1/recipes/?q=tofu&is_favorite=true&summary=true&limit=10&offset=0` finds ten compact favorite matches. Use the selected ID with `GET /api/v1/recipes/{id}/` for ingredients and steps. Reorder operations still require **all** IDs in the relevant collection; gather all pages before reordering a large collection.

## Shared input and update contract

REST and MCP use the same business validation and record projections. Requests accept only writable fields: unknown fields and attempts to submit read-only metadata are rejected. Names and titles cannot consist only of whitespace; supplied ingredients and steps cannot contain blank names/text. Invalid input leaves existing records and their children unchanged.

Recipe descriptions are limited to 5,000 characters, names/titles to 255, ingredient quantities to 100, step text to 2,000, and image URLs to 500. Nutrition and preparation time accept whole numbers from 0 to 2,147,483,647 or explicit null; booleans and fractional values are rejected. Checked and favorite states require JSON booleans.

Recipe PATCH operations lock the current owned record and write only supplied fields. An intervening update to another field is retained even when the PATCH serializer was initialized with an older object. Supplied child arrays still replace their collection atomically; an empty array intentionally clears it.

Business errors expose a stable `code`: `invalid_input`, `not_found`, `quantity_overflow`, `department_not_found` or `department_ambiguous`. Missing and foreign objects return HTTP 404, including planner recipe/list selections. Validation errors return 400 and retain field details. MCP business errors encode the corresponding code and message as JSON tool-error text; SDK argument validation may also report schema errors.

When both an ID and a title/name are provided, the supplied name must match the selected object after case-insensitive whitespace normalization. Contradictions return HTTP 400 / MCP error code `selection_mismatch` without changing data. This applies to recipe selections, target list selections and the MCP checked-state convenience selector. Omit the name when selecting solely by ID.

Checked-only item PATCH operations and MCP `set_item_checked` use the same update service. They preserve quantities, departments and article defaults, and do not recreate deleted saved articles.

List and recipe responses share their record shapes with MCP: IDs, positions and timestamps are included, recipe children have IDs/positions, and recipe responses expose only `picture_url` for images. The external `image_url` remains a write-only input for creation, editing and imports; `image` is not exposed. REST resolves uploaded image paths to absolute URLs; MCP exposes their stored media paths. These are metadata additions to MCP responses. Send writable fields rather than echoing a full response into an update request.

## Departments

`GET /api/v1/departments/` lists only the token owner's departments, sorted by their displayed labels. Each entry contains `id`, the stable `code`, the stored `name`, and the translated `label`.

`GET /api/v1/departments/resolve/?query=Obst%20und%20Gem%C3%BCse` resolves a code or name without changing anything. An unambiguous match returns the same department metadata. Both GET endpoints are read-only. `PATCH /api/v1/departments/{id}/` accepts `{"name": "Chilled food"}` to rename a department while retaining its stable code, position and all references.

Shopping items accept a department code or name in `department`; responses always contain its stable code. Exact codes take precedence. Otherwise, saved names and their translations in the configured languages are compared after normalizing case, whitespace, punctuation, conjunctions (`&`, `/`, `+`, `and`, `und`), and umlaut spellings such as `ü`/`ue`. No aliases are stored. Renaming a department preserves its code and does not retain its former name as an alias.

Omit `department` to use the saved article default. Send `"department": ""` to explicitly clear the assignment and update the article default.

An unknown or ambiguous department returns HTTP 400 with `code` (`department_not_found` or `department_ambiguous`), `query`, `message`, and `candidates`. Candidates contain only owned departments, with `code`, `name`, and `label`. Similar names are suggestions, never automatic assignments. Ask the user to choose a candidate and retry with its code. An unresolved request does not create departments or partially save a list, import, or replacement collection.

A resolver error looks like this; nested shopping items place the same detail under `items[index].department`:

```json
{
  "department": {
    "code": "department_not_found",
    "query": "Obst",
    "message": "Invalid department. No exact match was found; choose a saved code.",
    "candidates": [
      {"code": "produce", "name": "Fruit & vegetables", "label": "Fruit & vegetables"}
    ]
  }
}
```

## Shopping lists

- Collection: `/api/v1/shopping-lists/`
- The view set creates, reads, updates, and deletes lists with nested items.
- `POST /api/v1/shopping-lists/{id}/reorder/` accepts `{"item_ids": [3, 1, 2]}`.
- `POST /api/v1/shopping-lists/import_json/` accepts `{"lists": [...]}` or a bare list. See {doc}`json`.

## Shopping actions and article defaults

| Method | Path | Input / result |
| --- | --- | --- |
| POST | `/api/v1/shopping-lists/{id}/add-item/` | `name`, optional `quantity` and `department`. Returns the added/merged item with HTTP 200. |
| DELETE | `/api/v1/shopping-items/{id}/` | Deletes one owned entry; returns 204. Missing/foreign IDs return 404. |
| POST | `/api/v1/shopping-lists/{id}/delete-completed/` | No body required. Returns `{"list_id": 12, "deleted_count": 3}`. |
| POST | `/api/v1/recipes/{id}/add-to-list/` | Optional `list_id` or `list_title`; returns the resulting list and items with HTTP 200. |

Adding an item merges compatible quantities into an existing line with the same normalized name and reopens it. It preserves the article default when `department` is omitted or null; `""` clears it. Recipe copying uses the same quantity rules. A recipe-copy `list_id` must identify an existing owned list; a title finds or creates a named list; omitting both uses or creates today's list. When both selectors are supplied, the title must match the selected list or the request returns `selection_mismatch`. **Repeating either addition operation adds quantities again.** Invalid departments and quantity overflow return 400 and roll back the entire operation, including defaults, previously copied ingredients and a newly created target list.

Both deletion operations retain the shopping list and saved articles. Bulk deletion removes only checked entries on the selected owned list; repeating it on an unchanged list returns zero.

`GET /api/v1/shopping-items/` and `GET /api/v1/articles/` provide owned IDs. Their detail routes support GET, PUT and PATCH. Item PATCH accepts `name`, `quantity`, `department` and `checked`; article PATCH accepts `name` and `department`. Omitted fields remain unchanged. Item quantity updates replace the amount; article-default updates leave existing shopping entries unchanged.

```sh
curl -H "Authorization: Token <token>" http://localhost:8000/api/v1/shopping-lists/
curl -X POST -H "Authorization: Token <token>" -H "Content-Type: application/json" \
  -d '{"lists":[{"title":"Pasta","date":"2026-10-30","items":[{"name":"Pasta","quantity":"500 g"}]}]}' \
  http://localhost:8000/api/v1/shopping-lists/import_json/
```

## Replacement collections

For shopping-list and recipe updates, omitted `items`, `ingredients`, or `steps`
stay unchanged. A supplied collection replaces the entire corresponding
collection, including during PATCH. Each supplied item/ingredient requires a
`name`; each supplied step requires `text`. Incomplete replacement children
return field-specific HTTP 400 errors without changing existing data. An explicit
empty array (`[]`) intentionally clears that collection.

List/recipe creation and replacement run in transactions, so failed child writes
roll back metadata and children together. Accumulated shopping quantities must
fit the 100-character limit; overflow returns a validation error rather than
truncating data. Automatic addition applies only to simple decimal amounts with
compatible units. Fractions, mixed numbers and ranges are preserved as separate
quantity expressions, including repeated contributions.

Item/ingredient/step reorder requests must contain every current child ID exactly
once. Missing, duplicate and foreign IDs are rejected without changing order.

## Recipes

- Collection: `/api/v1/recipes/`
- The same token and the same user scope as shopping lists.
- `POST /api/v1/recipes/{id}/reorder-ingredients/` and `POST /api/v1/recipes/{id}/reorder-steps/` accept `{"line_ids": [3, 1, 2]}`.
- `POST /api/v1/recipes/import_json/` accepts `{"recipes": [...]}` or a bare list. An image file is not part of the JSON; send `image_url` or upload the file in the app.
- `POST /api/v1/recipes/{id}/favorite/` accepts `{"is_favorite": true}` or `false` and returns the recipe. Recipe responses expose the read-only `is_favorite` state; this action sets it explicitly rather than toggling it.


## Meal planner

All planner endpoints use the same authentication and services as the web planner.

| Method | Path | Input | Result |
| --- | --- | --- | --- |
| GET | `/api/v1/meal-planner/` | Optional `week=YYYY-MM-DD` query parameter | A Monday–Sunday week with seven days; omitted means the current local week. |
| PUT | `/api/v1/meal-planner/{date}/` | `{"recipe_id": 12}` | Assign or replace that date's recipe. Repeating the same request leaves one entry. |
| DELETE | `/api/v1/meal-planner/{date}/` | None | Clear that date. Returns 204, including when it is already empty. |
| POST | `/api/v1/meal-planner/add-to-list/` | `week` and exactly one of `shopping_list_id` or `title` | Copy the week's ingredients to an existing owned list or a new list, returning the list and its items. |

`date` and `week` use ISO calendar dates. Any day in a week selects the Monday on or before it. Week reads include empty days as `{"date": "2027-01-02", "recipe": null}`; planned days contain a recipe summary with `id` and `title`. Full recipe details are available from `/api/v1/recipes/{id}/`.

For example, `GET /api/v1/meal-planner/?week=2027-01-01` returns:

```json
{
  "week_start": "2026-12-28",
  "week_end": "2027-01-03",
  "days": [
    {"date": "2026-12-28", "recipe": null},
    {"date": "2026-12-29", "recipe": null},
    {"date": "2026-12-30", "recipe": null},
    {"date": "2026-12-31", "recipe": null},
    {"date": "2027-01-01", "recipe": {"id": 12, "title": "Soup"}},
    {"date": "2027-01-02", "recipe": null},
    {"date": "2027-01-03", "recipe": null}
  ]
}
```

To create a shopping list, send `{"week": "2027-01-01", "title": "Weekly shop"}`. To use an existing list, send `{"week": "2027-01-01", "shopping_list_id": 8}`. Supplying both targets or neither is a validation error. A week with no planned recipes is rejected without creating a list.

Matching ingredients and compatible quantities are merged using the existing shopping-list rules. Recipes planned on several days contribute once per day. **Repeating the POST adds the ingredients again**; this operation is not idempotent. Copying never clears the plan. Validation failures return 400; all data stays scoped to the token owner.
