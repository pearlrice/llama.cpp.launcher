# Project Rules

## Structure

- `launcher.py`: PySide6 desktop launcher UI and runtime wiring.
- `core/`: deployment logic, runtime defaults, and generated runtime state.
- `pics/`: README and UI screenshots.
- `dist/`, `.venv/`, `__pycache__/`, `.history/`: generated or local-only directories; do not edit for source changes.

## Editing

- Keep launcher UI changes in `launcher.py` unless a reusable deployment behavior belongs in `core/`.
- Keep persistent runtime defaults in `core/default_config.json`; user-specific generated state belongs in `core/config.json`.
- Do not modify packaged `.exe`, `.wsl`, virtualenv, cache, or history artifacts when changing source behavior.
- Prefer small, focused changes that preserve the current PySide6/qfluentwidgets style.

## Verification

- Run Python syntax checks for touched Python files before handing off.
- If behavior depends on local hardware or WSL services, verify what can be checked locally and state any runtime checks that were not possible.
