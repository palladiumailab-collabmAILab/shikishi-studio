---
name: python-development
description: Implement, refactor, and review Python application code in shikishi.
---

# Python development workflow

## Use when

- adding application behavior
- fixing or refactoring Python code
- reviewing Python changes

## Workflow

1. Read `AGENTS.md` and the applicable files in `rules/`.
2. Locate the existing behavior and define the expected result before editing.
3. Add or update focused tests in `tests/`.
4. Implement the smallest clear change in `src/shikishi/`.
5. Run the Ruff, mypy, and pytest commands documented in `AGENTS.md`.
6. Update `README.md` if setup, usage, or behavior changed.

## Design checks

- Keep external I/O at the edge of the application.
- Validate untrusted input early.
- Use clear names and typed interfaces.
- Return or raise actionable errors; never fail silently.
- Avoid dependencies unless they materially simplify the application.
