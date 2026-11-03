# MCP server

A second process of the same image serves streamable HTTP at `/mcp` on port `8001`. It uses the shared database and `easy_kitchen/services.py`. It does not call the HTTP API.

Tools have no user argument. Records belong to the owner of the DRF token in `Authorization: Token <token>`.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_shopping_lists` | Read the token owner's lists and items. |
| `list_recipes` | Read the token owner's recipes, ingredients, and steps. |
| `create_shopping_list` | Create a list. Confirm `title`, an ISO `date`, and `items` first. |
| `create_recipe` | Create a recipe. Confirm `title`, `ingredients`, and `steps` first. `image_url`, `calories`, `protein`, `carbohydrates`, `fat`, and `preparation_minutes` are optional. |
| `set_item_checked` | Mark an item completed. Pass `list_id` when the name is on more than one list. `checked` defaults to `true`. |
| `add_item_to_list` | Add an item. Pass `list_id` or `list_title`. Omit the list to use today's list, or create one titled Today. |
| `add_recipe_to_list` | Copy a recipe's ingredients onto a list. Omit the list to use today's list, or create one titled Today. |

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
