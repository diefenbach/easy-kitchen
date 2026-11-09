# MCP server

A second process of the same image serves streamable HTTP at `/mcp` on port `8001`. It uses the shared database and `easy_kitchen/services.py`. It does not call the HTTP API.

Tools have no user argument. Records belong to the owner of the DRF token in `Authorization: Token <token>`.

Every REST business action has an MCP equivalent, currently 37 tools in total. The route-to-tool mapping is checked automatically by tests, so adding a REST action without its MCP counterpart fails the parity check. Swagger/OpenAPI documentation and HTTP-specific methods are transport facilities rather than additional business tools.

## Shared contract

The REST and MCP adapters share business validation, partial recipe updates and public record projections. Tool argument schemas reject unknown fields. Names/titles and ingredient/step content must contain non-whitespace text. Descriptions are limited to 5,000 characters; nutrition/preparation values are null or whole numbers from 0 to 2,147,483,647. Boolean flags require actual JSON booleans. See {doc}`api` for the full shared input, metadata and error contract.

Record responses include positions and timestamps; recipe children include IDs and positions, and recipe responses expose only the selected `picture_url`. External `image_url` remains accepted as input for creation, editing and imports, but is not returned. Item responses use the same shape across listing, addition, update and checked-state tools. Business errors carry stable JSON `code` and `message` fields. Existing human-readable messages remain in those errors. Each registered MCP call closes its worker's database connections after returning or failing.

## Collection queries

`list_recipes`, `list_shopping_lists`, `list_shopping_items`, `list_articles` and `list_departments` accept `q`, `limit` and `offset`. They return a page of at most 50 records by default; `limit` can be 1–200. Request further pages by increasing offset until fewer than the requested limit are returned. The result remains an array. Existing clients that require the complete collection must now page through all results.

`list_recipes` additionally accepts `is_favorite` and `summary`; `list_shopping_lists` accepts inclusive ISO `date_from`/`date_to` and `summary`; `list_shopping_items` accepts `checked` and an owned `list_id`; `list_articles` accepts `department` (empty means unassigned). Omitted boolean filters include both states. Invalid queries return errors rather than silently changing their meaning.

Prefer `list_recipes` with `{"q": "tofu", "is_favorite": true, "summary": true, "limit": 10}` to discover recipes. Compact results omit ingredients/steps; follow with `get_recipe` for full details. `summary=true` similarly omits list items; follow with `get_shopping_list`. Full records remain the default (`summary=false`). Recipe search also matches ingredient names, department search matches stored codes/names and current translated labels, and each search term must match. See {doc}`api` for the complete filter contract.

The checked-state convenience tool and general item update use the same service and do not modify article defaults for checked-only requests. Conflicting ID/name or ID/title selections return `selection_mismatch`; matching names may differ in case or whitespace.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_departments` | Read the token owner's department IDs, stable codes, names and translated labels. |
| `resolve_department` | Resolve a code, saved name or translation without writing. Pass `name`. |
| `list_shopping_lists` | Read the token owner's lists and items. |
| `list_recipes` | Read the token owner's recipes, ingredients, and steps. |
| `list_shopping_items` | Read entries across all owned shopping lists, including their list IDs. |
| `get_recipe` | Read one owned `recipe_id`, including ingredients, steps and metadata. |
| `get_shopping_list` | Read one existing owned `list_id`, including items. Never creates a list. |
| `get_shopping_item` | Read one owned list entry by `item_id`. |
| `get_article` | Read one owned saved article by `article_id`. |
| `get_department` | Read one owned department by `department_id`. |
| `create_shopping_list` | Create a list. Confirm `title`, an ISO `date`, and `items` first. |
| `create_recipe` | Create a recipe. Confirm `title`, `ingredients`, and `steps` first. `image_url`, `calories`, `protein`, `carbohydrates`, `fat`, and `preparation_minutes` are optional. |
| `update_recipe` | Edit an owned recipe by `recipe_id` or unique `recipe_title`. Pass only fields to change in `changes`; omitted fields are preserved. |
| `update_shopping_item` | Edit an owned `item_id` using `changes` (`name`, `quantity`, `department`, `checked`). Quantity replaces the previous amount. |
| `delete_shopping_item` | Delete an owned shopping entry by `item_id`, retaining its list and saved article. Missing or foreign IDs return an error. |
| `delete_completed_items` | Delete checked entries from an existing owned `list_id`; returns `list_id` and `deleted_count`. Open entries and saved articles remain. |
| `update_shopping_list` | Edit an owned `list_id` using `changes` (`title`, ISO `date`, `icon`, `items`). Omitted items are preserved; supplied items replace the collection and `[]` clears it. |
| `delete_recipe` | Delete an owned `recipe_id`, its ingredients/steps and planner references. |
| `delete_shopping_list` | Delete an owned `list_id` and its entries, retaining articles and recipes. |
| `reorder_shopping_lists` | Order all owned lists using every current `list_ids` entry exactly once. |
| `reorder_shopping_items` | Order one owned `list_id` using every current `item_ids` entry exactly once. |
| `reorder_recipes` | Order all owned recipes using every current `recipe_ids` entry exactly once. |
| `reorder_recipe_ingredients` | Order an owned `recipe_id` using every current ingredient ID in `line_ids`. |
| `reorder_recipe_steps` | Order an owned `recipe_id` using every current step ID in `line_ids`. |
| `import_recipes` | Create a batch from `recipes`; confirm records first. All-or-nothing, input order preserved. |
| `import_shopping_lists` | Create a batch from `lists`; confirm records first. All-or-nothing, input order preserved. |
| `list_articles` | Read the token owner's saved article IDs, names and default department codes. |
| `update_article` | Edit an owned `article_id` using `changes` (`name`, `department`). Existing shopping-list entries are preserved. |
| `update_department` | Rename an owned `department_id` using `changes: {"name": "..."}`. Its stable code and references are preserved. |
| `set_recipe_favorite` | Set `is_favorite` to `true` or `false` for an owned `recipe_id` or unique `recipe_title`. |
| `set_item_checked` | Set checked state by owned `item_id` (preferred), or an unambiguous `name` and optional `list_id`. Duplicate names are rejected. `checked` defaults to `true`. |
| `add_item_to_list` | Add an item. Pass `list_id` or `list_title`. Omit the list to use today's list, or create one titled Today. |
| `add_recipe_to_list` | Copy a recipe's ingredients onto a list. Omit the list to use today's list, or create one titled Today. |
| `get_meal_plan_week` | Read a seven-day Monday–Sunday plan. Pass an ISO `week` date, or omit it for the current local week. |
| `set_meal_plan_recipe` | Plan one recipe for an ISO `date`, by owned `recipe_id` or unambiguous `recipe_title`. Replaces an occupied day. |
| `clear_meal_plan_day` | Remove the planned recipe for an ISO `date`. Repeating the call leaves the day empty. |
| `add_meal_plan_week_to_list` | Copy an ISO `week` to exactly one existing `list_id` or a new list named `title`. |

## Editing recipes

Use `list_recipes` to find the recipe, then call `update_recipe` with its `recipe_id` (preferred) or an unambiguous `recipe_title`. Selection is scoped to the token owner. When both ID and title are supplied, their normalized names must agree; conflicting selections return `selection_mismatch`. The tool returns the updated recipe including ingredients and steps, and never creates a new recipe.

For example, `{"recipe_id": 11, "changes": {"fat": 65, "carbohydrates": 50}}` updates only those two nutrition fields. These are illustrative values, not calculated nutrition facts.

`changes` accepts `title`, `description`, `image_url`, `calories`, `protein`, `carbohydrates`, `fat`, `preparation_minutes`, `ingredients`, and `steps`. Omitted fields remain unchanged. Explicit `null` clears a numeric field; zero is stored as zero. Empty strings clear the description or image URL. A title must remain non-empty. Supplied ingredient and step arrays replace the entire corresponding collection; `[]` removes all entries. An empty `changes` object preserves the recipe. Invalid changes leave the entire recipe unchanged. Repeating the same update is idempotent.

## Reading, deleting, sorting and importing

The `get_*` tools correspond to REST `GET .../{id}/`. Missing and foreign IDs return `not_found`; no read tool creates data. `list_shopping_items` corresponds to `GET /api/v1/shopping-items/`.

`delete_recipe` and `delete_shopping_list` correspond to REST DELETE on their detail routes. MCP returns the selected ID and `deleted: true`; REST returns 204. Missing, foreign or already deleted records return an error. Recipe deletion cascades to ingredients, steps and existing meal-plan entries, matching REST; list deletion cascades to list entries and retains saved articles.

Sorting tools use the same services as REST reorder actions. Supply every current ID in the selected collection exactly once. Missing, duplicate, extra and foreign IDs are rejected atomically. Root sorting returns the ordered lists/recipes; child sorting returns the updated parent with its children in the saved order.

Call `import_recipes` with `{"recipes": [{"title": "Soup", "ingredients": [{"name": "Salt", "quantity": "1 tsp"}], "steps": [{"text": "Cook"}]}]}`. Call `import_shopping_lists` with `{"lists": [{"title": "Weekend", "date": "2027-01-02", "items": [{"name": "Tofu", "quantity": "400 g", "department": "dairy", "checked": false}]}]}`. These correspond to REST `POST /api/v1/recipes/import_json/` and `POST /api/v1/shopping-lists/import_json/`.

Imports create new records at the front in input order and shift existing records down. A missing imported list date defaults to today. Supplied child `position` values are supported. Invalid records roll back the entire batch, including positions and article defaults. Imported IDs, ownership and other read-only metadata cannot be assigned. **Repeating an import creates additional records**, so imports are not idempotent. An empty batch returns an empty result.

## Updating lists, items and defaults

Find IDs with `list_shopping_lists`, `list_articles` or `list_departments`, then send only the intended fields in `changes`. Updates never create missing objects. Omitted fields are preserved; an empty `changes` object does nothing. Null is not accepted for these fields. Empty `quantity` or `department` explicitly clears it; names and list titles must remain non-empty. List icons use the same codes as the web UI, such as `basket`, `cart` or `bag`.

For example, `update_shopping_item` with `{"item_id": 42, "changes": {"quantity": "600 g"}}` replaces that line's quantity without adding it to the old amount, resetting checked state or changing its position. Editing an item's name or department also remembers its resulting article default, matching the web editor. Editing an article default itself leaves existing shopping-list entries unchanged.

Department assignments use owned department codes or unambiguous names/translations, with the same structured resolution errors described below. Department renames preserve IDs, codes, order and all existing article/item references. Duplicate article or department names are rejected.

All update tools are idempotent. `set_recipe_favorite` sets an explicit state rather than toggling it. Recipe responses from `list_recipes`, create/update and favorite operations include `is_favorite`.

The corresponding REST operations are:

| Endpoint | Fields |
| --- | --- |
| `PATCH /api/v1/shopping-items/{id}/` | `name`, `quantity`, `department`, `checked` |
| `PATCH /api/v1/shopping-lists/{id}/` | `title`, `date`, `icon` (also retains the existing explicit `items` replacement support) |
| `PATCH /api/v1/articles/{id}/` | `name`, `department` |
| `PATCH /api/v1/departments/{id}/` | `name` |
| `POST /api/v1/recipes/{id}/favorite/` | `is_favorite` (required boolean) |

REST PATCH bodies contain the fields directly, without a `changes` wrapper. The four PATCH routes also support PUT; PATCH is preferred for partial changes. Item, article and department routes support GET for discovery and detail. Articles and departments do not expose create or delete operations. `is_favorite` is read-only in the standard recipe representation; set it through the favorite action. All operations require authentication and scope IDs to the current user. Foreign and missing IDs return 404; invalid input returns 400.

## Shopping actions

| MCP tool | REST equivalent | Result |
| --- | --- | --- |
| `delete_shopping_item(item_id)` | `DELETE /api/v1/shopping-items/{id}/` | MCP returns `item_id` and `deleted: true`; REST returns 204. The list and saved article remain. |
| `delete_completed_items(list_id)` | `POST /api/v1/shopping-lists/{id}/delete-completed/` | Returns `list_id` and `deleted_count`. Only checked entries on that list are removed. |
| `add_item_to_list` | `POST /api/v1/shopping-lists/{id}/add-item/` | Send `name`, optional `quantity` and `department`; returns the added or merged item with its ID. |
| `add_recipe_to_list` | `POST /api/v1/recipes/{id}/add-to-list/` | Send optional `list_id` or `list_title`; returns the resulting list including items. |

Deletion tools require IDs of existing owned objects and never create lists. Deleting an already deleted item returns an error (REST 404). Deleting completed entries again on an unchanged list returns `deleted_count: 0`. No articles are deleted.

Adding an item merges compatible quantities with an existing entry of the same normalized name and reopens it. Omitted/null department retains the article default; an empty string clears it. Copying recipe ingredients uses the same merge rules. For recipe copying, the ID selects an existing owned list; a title finds an owned list or creates one; omitting both uses or creates today's list. When both selectors are supplied, the title must match the selected list; contradictions return `selection_mismatch`. API item addition always targets the list ID in the URL. **Both addition operations are additive: repeating them adds the quantities again.** Invalid departments and quantity overflow roll back the entire operation, including defaults, earlier ingredients and newly created lists.

## Department selection

Call `list_departments` first and prefer the returned `code` when creating a list or adding an item. `department` also accepts unambiguous saved names and English/German translations, including normalized variants such as `Obst und Gemüse`, `Obst & Gemüse`, and `Obst / Gemuese`.

Use `resolve_department` with `{"name": "Obst und Gemüse"}` to resolve a name before writing. It returns `id`, `code`, `name`, and `label`. Exact codes take precedence; approximate spelling matches are never assigned automatically.

Unresolved or ambiguous inputs produce a tool error containing a JSON object with `code` (`department_not_found` or `department_ambiguous`), `query`, `message`, and `candidates`. The MCP SDK may prefix that JSON with the tool name. Candidates contain owned `code`, `name`, and `label` values. Ask the user to select a candidate and retry with its code; do not guess or automatically create a department. If no candidate fits, ask the user for another department or an explicit assignment without a department.

An unresolved write rolls back the entire operation, including a newly created Today list or earlier items in a batch. Omitting `department` uses the article default; an empty string explicitly clears it. No aliases are stored.

## Meal planning

Planner tools share the web planner's services and the token owner's data. A `week` can be any day in the desired week and is normalized to Monday. The read tool returns `week_start`, `week_end`, and seven `days`; each day has `date` and a nullable `recipe` summary with `id` and `title`.

For example, call `set_meal_plan_recipe` with `{"date": "2027-01-01", "recipe_id": 12}`, then `get_meal_plan_week` with `{"week": "2027-01-01"}`. Clear that day with `clear_meal_plan_day` and `{"date": "2027-01-01"}`. No tool accepts a user id.

Copy the week with `{"week": "2027-01-01", "title": "Weekly shop"}`, or use `list_id` instead of `title` for an existing owned list. A week with no planned recipes cannot create a list. Ingredients and compatible quantities merge; a repeated recipe counts once for each planned day. **Calling the copy tool again adds the ingredients again.** The plan itself is preserved.

Setting and clearing a date are idempotent. Their annotations indicate that they can overwrite or remove existing plans. Week reads are read-only; copying ingredients is not idempotent.

## Production

Nginx proxies `/mcp` to the MCP container:

```yaml
command: ["python", "-m", "easy_kitchen.mcp_server"]
```

```nginx
location /mcp {
    proxy_pass http://kitchen-mcp:8001;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_buffering off;
}
```

Clients call `https://kitchen.iqpp.de/mcp`. Host and origin checks use `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. Override them with `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS` when the public host differs, for example an ngrok URL.

## Local process

```sh
DJANGO_SETTINGS_MODULE=project.settings.development PYTHONPATH=src POSTGRES_HOST=localhost \
  uv run --env-file .env python -m easy_kitchen.mcp_server
```

Cursor can point `mcp.json` at `http://127.0.0.1:8001/mcp` or at a tunnel in front of that port. Use a token created on the same database the process is using.
