# Project-specific Codex instructions

## Shikishi Studio rules

- Build and maintain Shikishi Studio as a Python application with small, reviewable changes.
- Use `rules/README.md` as the project-specific rule index and follow the matching architecture, reliability, data-processing, testing, security, operations, UI, Python, Git, and Docker rule files.
- Use `skills/python-development/SKILL.md` for Python implementation/refactoring/review, `skills/python-dependency-selection/SKILL.md` when a material dependency choice is open, and `skills/codebase-health-review/SKILL.md` for explicit repository-health work.
- Keep reusable CLI/data-processing code in `src/shikishi/`, web/API code in `app.py` and `studio/`, browser assets in `static/`, and tests in `tests/`.
- Validate data at external boundaries and raise actionable errors. Never silently discard invalid input.
- Preserve source data; write transformed data and generated artifacts to separate, traceable locations.
- Never train, fine-tune, merge, rewrite, overwrite, or otherwise mutate model weights without first stating exactly what will change and obtaining explicit approval. Save approved training results as new, versioned, provenance-recorded artifacts unless overwrite is explicitly approved.
- Do not hardcode secrets. Use environment variables and document new variables in `.env.example`.

## Verification

For Python/runtime changes, use:
- `docker compose build app`
- `docker compose run --rm app python -m ruff check .`
- `docker compose run --rm app python -m ruff format --check .`
- `docker compose run --rm app python -m mypy`
- `docker compose run --rm app python -m pytest`

Documentation-only or other narrowly scoped changes may use a smaller check when the omitted gates cannot exercise the changed surface. Keep commits focused and exclude secrets, virtual environments, caches, generated artifacts, and machine-specific configuration.
