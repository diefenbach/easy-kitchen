# MCP server

A second process of the same image serves streamable HTTP at `/mcp` on port `8001`. It uses the shared database and `easy_kitchen/services.py`. It does not call the HTTP API.

Tools have no user argument. Records belong to the owner of the DRF token in `Authorization: Token <token>`.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_departments` | Read the token owner's department IDs, stable codes, names and translated labels. |
| `resolve_department` | Resolve a code, saved name or translation without writing. Pass `name`. |
| `list_shopping_lists` | Read the token owner's lists and items. |
| `list_recipes` | Read the token owner's recipes, ingredients, and steps. |
| `create_shopping_list` | Create a list. Confirm `title`, an ISO `date`, and `items` first. |
| `create_recipe` | Create a recipe. Confirm `title`, `ingredients`, and `steps` first. `image_url`, `calories`, `protein`, `carbohydrates`, `fat`, and `preparation_minutes` are optional. |
| `set_item_checked` | Mark an item completed. Pass `list_id` when the name is on more than one list. `checked` defaults to `true`. |
| `add_item_to_list` | Add an item. Pass `list_id` or `list_title`. Omit the list to use today's list, or create one titled Today. |
| `add_recipe_to_list` | Copy a recipe's ingredients onto a list. Omit the list to use today's list, or create one titled Today. |
| `get_meal_plan_week` | Read a seven-day Monday–Sunday plan. Pass an ISO `week` date, or omit it for the current local week. |
| `set_meal_plan_recipe` | Plan one recipe for an ISO `date`, by owned `recipe_id` or unambiguous `recipe_title`. Replaces an occupied day. |
| `clear_meal_plan_day` | Remove the planned recipe for an ISO `date`. Repeating the call leaves the day empty. |
| `add_meal_plan_week_to_list` | Copy an ISO `week` to exactly one existing `list_id` or a new list named `title`. |

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
