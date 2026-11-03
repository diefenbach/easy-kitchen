# JSON import and export

The same document shape is used by the import pages, the export page, and the API. Export writes `easykitchen.json`. Import creates new records for the signed-in user and ignores foreign ids.

## Export

Open **Export JSON** in the account menu, or go to `/export/`. Select the lists and recipes to include, then download the file. The body is an object with `lists` and `recipes` arrays. Omit either key when that side is empty.

## List JSON

Open **Import JSON** on the list overview, or `POST` the same document to `/api/v1/shopping-lists/import_json/` with `Authorization: Token <token>`.

The body is either an object with a `lists` array or the array itself. Every list in the document is created for the signed-in user.

```json
{
  "lists": [
    {
      "title": "Weekend shop",
      "date": "2026-11-01",
      "items": [
        {"name": "Oat milk", "quantity": "2 l"},
        {"name": "Apples", "quantity": "1 kg", "checked": false}
      ]
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | List title |
| `date` | yes | Shopping date, `YYYY-MM-DD` |
| `items` | no | Items on that list. Omit it for an empty list. |
| `items[].name` | yes | Item name |
| `items[].quantity` | no | Quantity text, for example `500 g` or `2 pieces`. An empty string is allowed. |
| `items[].checked` | no | `true` when the item is already completed. Defaults to `false`. |
| `items[].position` | no | Order on the list, starting at `1`. Items keep the array order when this is omitted. |

`id`, `created_at`, and `updated_at` are returned by the API and ignored on import.

## Recipe JSON

Open **Import JSON** on the recipe overview, or `POST` the same document to `/api/v1/recipes/import_json/` with `Authorization: Token <token>`.

The body is either an object with a `recipes` array or the array itself. Every recipe in the document is created for the signed-in user.

```json
{
  "recipes": [
    {
      "title": "Pancakes",
      "description": "Sunday breakfast",
      "image_url": "https://example.com/pancakes.jpg",
      "calories": 450,
      "protein": 12,
      "carbohydrates": 55,
      "fat": 18,
      "preparation_minutes": 25,
      "ingredients": [
        {"name": "flour", "quantity": "200 g"},
        {"name": "eggs", "quantity": "2"}
      ],
      "steps": [
        {"text": "Mix the batter."},
        {"text": "Fry until golden."}
      ]
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | Recipe title |
| `description` | no | Longer text. An empty string is allowed. |
| `image_url` | no | `http` or `https` address of a picture. Shown when no file has been uploaded. |
| `calories` | no | Whole number of kilocalories. Omit it or send `null` when unknown. |
| `protein` | no | Whole number of grams of protein. Omit it or send `null` when unknown. |
| `carbohydrates` | no | Whole number of grams of carbohydrates. Omit it or send `null` when unknown. |
| `fat` | no | Whole number of grams of fat. Omit it or send `null` when unknown. |
| `preparation_minutes` | no | Whole number of minutes. Omit it or send `null` when unknown. |
| `ingredients` | no | Ordered ingredients. Omit it for a recipe without ingredients. |
| `ingredients[].name` | yes | Ingredient name |
| `ingredients[].quantity` | no | Quantity text, for example `500 g` or `2`. An empty string is allowed. |
| `ingredients[].position` | no | Order, starting at `1`. Ingredients keep the array order when this is omitted. |
| `steps` | no | Ordered cooking steps |
| `steps[].text` | yes | One step |
| `steps[].position` | no | Order, starting at `1`. Steps keep the array order when this is omitted. |

`id`, `image`, `picture_url`, `created_at`, and `updated_at` are returned by the API. `image` is the uploaded file address. `picture_url` is the file when one exists, otherwise `image_url`. Import ignores those read-only fields.
