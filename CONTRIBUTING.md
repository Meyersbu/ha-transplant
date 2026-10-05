# Contributing to Transplant

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
npm ci
```

- `pytest tests --ignore=tests/integration` – core engine tests (no Home Assistant needed, < 1 s)
- `pytest tests` – everything, including end-to-end tests against a real Home Assistant core
- `npm run build` – compile the panel into `custom_components/transplant/frontend` (commit the output)
- Preview the panel without Home Assistant: `python -m http.server` in the repo root, then open
  `http://localhost:8000/scripts/preview/index.html` (add `?dark` for the dark theme)

## Where things live

| Module | What it does | Good place to extend |
|---|---|---|
| `core/scanner.py` | Finds references in any config tree | New reference shapes |
| `core/replacer.py` | Pure rewrite of a config tree | New "needs review" rules |
| `core/planner.py` | Entity matching and plans | Better matching heuristics |
| `sources.py` | Reads/writes HA config objects | New sources (helpers, blueprints) |
| `frontend/src` | The panel | UX, translations |

`core/` must stay free of Home Assistant imports so it stays fast to test.

## Rules for changes that write configuration

1. Keep **preview → confirm → execute**. Nothing is written without a plan the user saw.
2. Only write through mechanisms Home Assistant itself uses. No registry or database edits.
3. Every new write path needs an integration test that applies **and** undoes.
