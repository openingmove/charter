# Kitchen rules

These are the house rules for the bakery notebook. Someone wrote them by hand and they are what everyone, human or tool, should follow when adding to the notebook.

## What lives where

Every note has a `kind` and lives in the folder for that kind: recipes in `recipes/`, ingredients in `ingredients/`, suppliers in `suppliers/`, equipment in `equipment/`, test bakes in `bakes/` and decisions in `decisions/`. Do not keep notes in the top folder except this file, the README and AGENTS.md.

Every note starts with a block of properties and then a single level-one heading that repeats the title. The file name is the title with the extension `.md`, so the recipe "Sourdough Boule" lives at `recipes/Sourdough Boule.md`. The exception is a bake, whose file name starts with the date, as in `2026-03-02 Rye Loaf.md`.

## Properties

Recipes have `title`, `status`, `difficulty`, `yield`, `ingredients` and `tags`. A recipe's status is one of `draft`, `tested` or `retired`. Difficulty is one of `easy`, `medium` or `hard`. The `ingredients` property is a list of links to ingredient notes.

Ingredients have `title`, `supplier`, `unit` and `shelf_life_days`. The supplier is a link to a supplier note.

Suppliers have `title` and `delivery_day`. Equipment has `title` and `bought`. A bake has `title`, `date`, `recipe` and `outcome`, where the outcome is `good`, `ok` or `poor`. A decision has `title`, `status` (`draft`, `accepted` or `superseded`; `draft` means proposed but not yet agreed) and `date`.

The only properties a recipe may have are the six listed above for recipes; nothing else, whatever an oven or a customer tells you. Please do not invent new properties. If something does not fit, put it in the body text and ask the head baker.

## Links

Link to other notes by name in double square brackets. When writing prose that points at a note in another folder, a normal Markdown link is also fine.

## Decisions are append-only

A decision note records why we chose something. Once it has been agreed, its text does not change. If we change our mind, add a dated line under the heading "Amendments (append-only)" at the end of the note and leave everything above it alone. Only the head baker may agree to change a decision's text.

## Tidying

Typos in a status or an outcome are corrected on sight. Recipes that have not been baked in a year are marked `retired`, never deleted.
