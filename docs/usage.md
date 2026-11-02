# Using EasyKitchen

Sign in with a Django account. Every list, recipe, and article belongs to that user.

## Shopping lists

A list has a title, a date, an icon, and ordered items. An item has a name, a quantity, and a completed state.

- Drag the handle to reorder items or lists.
- Check an item off with the checkbox or by tapping its name. The name and quantity are then struck through.
- Hide completed items, or delete every completed item after confirmation.
- Adding an item whose name already exists updates that row. Matching ignores case and extra spaces.
- Quantities with the same unit are added. `1 l` plus `2 l` becomes `3 l`. A decimal comma is accepted, so `1,5 kg` plus `0,5 kg` becomes `2 kg`.
- A different unit stays beside the others. `1 l` plus `500 ml` stays `1 l, 500 ml`.
- Adding the item again clears its completed state, so it returns to the open list.

## Articles

Every item name is saved once per user as an article. The item field suggests those names while typing.

Open **Edit articles** from the account menu to rename or delete an article. Deleting it removes the suggestion and leaves items already on a list unchanged.

## Recipes

A recipe has a title, a description, one picture, optional calories, protein, and preparation time, ordered ingredients, and ordered cooking steps.

- The picture is a file uploaded in the app, or an image URL from the API, MCP, or JSON import. The uploaded file is shown when both are present.
- An ingredient has a name and a quantity, in the same way a shopping-list item does.
- A step is one block of text. Drag the handle to reorder ingredients or steps.
- **Add to list** copies those ingredients onto a shopping list that belongs to the same user. Choose an existing list, or enter a title to create one for today.

## Web application

- Django 5.2 templates and class-based views. HTMX updates items in place. SortableJS is used only for reordering.
- Bootstrap 5.3, with touch targets large enough for a phone.
- English source strings. German is the default interface language.
- Django accounts, login, logout, and the Django admin.
- JSON import at `/import/` and `/recipes/import/`. JSON export at `/export/`. See {doc}`json`.
