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

A recipe has a title, a description, one picture, optional calories, protein, carbohydrates, fat, and preparation time, ordered ingredients, and ordered cooking steps.

- The picture is a file uploaded in the app, or an image URL from the API, MCP, or JSON import. The uploaded file is shown when both are present.
- An ingredient has a name and a quantity, in the same way a shopping-list item does.
- A step is one block of text. Drag the handle to reorder ingredients or steps.
- **Add to list** copies those ingredients onto a shopping list that belongs to the same user. Choose an existing list, or enter a title to create one for today.

## Meal planner

Open **Meal planner** in the navigation to plan one recipe per day from Monday through Sunday. The arrows switch weeks; **Current week** returns to this week. Empty days are allowed.

Search across titles, descriptions, ingredients (including quantities), and cooking steps. All search terms must occur somewhere in the same recipe; their order and capitalization do not matter. For example, `chickpeas roast` finds a recipe with chickpeas among its ingredients and roasting in its instructions. Choose a suggestion, then **Save**. You can also select a suggestion with the arrow keys and Enter. Choose a different recipe to replace the day's plan, or **Remove** to clear it.

Under **Create shopping list from plan**, choose an existing shopping list or enter a new list title. All ingredients from the selected week are copied to that list using the usual quantity-merging rules. Planning a recipe twice adds its ingredients twice. Empty days contribute nothing. An entirely empty week cannot create a list. Creating the list again adds the ingredients again.

## Web application

- Django 5.2 templates and class-based views. HTMX updates items in place. SortableJS is used only for reordering.
- Bootstrap 5.3, with touch targets large enough for a phone.
- English source strings. German is the default interface language.
- Django accounts, login, logout, and the Django admin.
- JSON import at `/import/` and `/recipes/import/`. JSON export at `/export/`. See {doc}`json`.
