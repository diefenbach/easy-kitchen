# EasyKitchen

EasyKitchen is a private shopping-list and recipe app. It is built with Django 5.2 LTS, server-rendered templates, HTMX for small updates, Bootstrap 5.3, and SortableJS for ordering.

Each account sees only its own lists, recipes, and articles. The web UI, the REST API, and the MCP server call the same operations in `easy_kitchen/services.py`.

```{toctree}
:maxdepth: 2
:caption: Contents

installation
usage
json
api
mcp
development
```

## What you can do

- Keep dated shopping lists with quantities and a completed state.
- Save item names as articles so the item field can suggest them later.
- Store recipes, then copy their ingredients onto a list.
- Import and export JSON that the app can read again.
- Drive the same data from the API or from MCP.

## Source

The code lives at [github.com/diefenbach/easy-kitchen](https://github.com/diefenbach/easy-kitchen). English is the source language. German is the default interface language.
