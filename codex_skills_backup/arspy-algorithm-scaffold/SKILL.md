---
name: arspy-algorithm-scaffold
description: Create new arspy algorithm folders and starter files that match the sentinel_water execution pattern. Use when asked to initialize a new algorithm directory with app.py, app.sh, config.py, src/main.py, and test.json so it can run via `sh app.sh test.json`.
---

# Arspy Algorithm Scaffold

Create a new algorithm scaffold under the current repo with a fixed runnable structure.

## Workflow

1. Collect parameters from user request.
- Required: algorithm slug/folder name.
- Optional: input field list, algorithm display name, algorithm description.

2. Run scaffold generator script from this skill.

```bash
python scripts/create_scaffold.py --name <algorithm_slug> --inputs <a,b,c> --desc "<description>" --algorithm-name "<display_name>" --path <repo_root>
```

3. Report created files and remind runtime command.
- Runtime command inside generated folder: `sh app.sh test.json`

## Defaults

- `--inputs` default: `primaryFile,resultPath,auxPath`
- `--desc` default: `基于arspy框架的新算法`
- `--algorithm-name` default: generated from slug (title style)
- Existing target folder: fail fast unless `--overwrite` is explicitly provided.

## Guardrails

- Normalize user-provided name to lowercase safe slug (`a-z`, `0-9`, `_`, `-`).
- If normalized name becomes empty, stop and return error.
- If template files are missing, stop and show the missing filenames.
- If user gives empty inputs string, fall back to default inputs.
- During algorithm refactors, keep `config.py` with exactly four variables only:
  `algorithm_name`, `algorithm_description`, `key_steps`, `INPUT`.
- Do not add/remove variable names in `config.py`; only update their values.
- Do not add extra functions inside `src/main.py` during refactor.
- If small helper/private functions are needed, define them in `src/utils.py`.
- If complex processing is needed, create dedicated modules under `src/` (for example: `src/preprocess.py`, `src/infer.py`).
- Prefer `arspy/naming.py` interfaces (`parse_name`, `build_names`, `build_mapinfo`) for output filename/path definition.

## Files Generated

- `<algorithm_slug>/app.py`
- `<algorithm_slug>/app.sh`
- `<algorithm_slug>/config.py`
- `<algorithm_slug>/src/main.py`
- `<algorithm_slug>/test.json`

## Resources

### scripts/
- `scripts/create_scaffold.py`: create algorithm directories from templates.

### assets/templates/
- `app.py.tpl`: algorithm entry script.
- `app.sh.tpl`: shell entry script for `sh app.sh test.json`.
- `config.py.tpl`: algorithm metadata and INPUT fields.
- `main.py.tpl`: minimal runnable algorithm main logic with naming.py-oriented output definition pattern.
- `test.json.tpl`: test input containing required six fields.
