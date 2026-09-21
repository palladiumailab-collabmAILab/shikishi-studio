# Project-specific Codex instructions

## Project purpose
- Build and maintain Shikishi Studio as a Python application with small, reviewable changes.

## Sources of truth
- `rules/README.md`: project-specific rule index.
- Project implementation under `src/shikishi/`, `app.py`, `studio/`, `static/`, and `tests/`.

## Project invariants
- Use the matching project rule/skill for Python development, dependency selection, and explicit codebase-health work.
- Validate data at external boundaries and raise actionable errors; never silently discard invalid input.
- Preserve source data and write transformed/generated artifacts to separate traceable locations.
- Never train, fine-tune, merge, rewrite, overwrite, or otherwise mutate model weights without explicit user approval after stating exactly what will change.
- Save approved training results as new, versioned, provenance-recorded artifacts unless overwrite is explicitly approved.
- Do not hardcode secrets; document new environment variables in `.env.example`.

## Verification
- Python/runtime path: `docker compose build app`, Ruff check/format, mypy, and pytest through the app container.
- Documentation-only or narrowly scoped changes may use a smaller gate when omitted checks cannot exercise the changed surface.
