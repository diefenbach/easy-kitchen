# EasyKitchen in ChatGPT

This directory contains a deliberately small Action definition for a **private**
EasyKitchen GPT. It can read shopping lists and create new ones for the user whose
DRF token is configured in the Action.

## Configure the Action

1. Create a private GPT in ChatGPT and open **Actions**.
2. Import or paste `easylist-openapi.yaml`.
3. Set authentication to **API Key** with a **Custom header**:
   - Header name: `Authorization`
   - Secret value: `Token <your DRF token>`
4. Save and test `listShoppingLists` and `createShoppingList` in the Action
   editor.

Keep the GPT private. Anyone allowed to use it would otherwise act through the
configured EasyKitchen account.

## Suggested GPT instructions

```text
Use EasyKitchen only when the user explicitly asks to read or create a shopping
list. Before creating a list, confirm any missing title, date, or unclear item.
Use ISO dates (YYYY-MM-DD). Do not claim that a list was created until
createShoppingList returned successfully. Never reveal or request the API token.
```
