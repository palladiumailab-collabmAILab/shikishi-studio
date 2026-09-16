# Git rules

- Keep commits single-purpose and reviewable.
- Run the quality gates before committing; do not bypass the hook except for an
  explicitly documented emergency.
- Never add secrets, `.env` files, local environments, caches, or generated
  output to Git.
- Preserve unrelated user changes in a dirty worktree. Stage only the files and
  hunks that belong to the requested change.
- Use conventional commit prefixes: `feat`, `fix`, `docs`, `test`, `refactor`,
  `chore`, `ci`, or `perf`.
- Do not push, rewrite history, change remotes, or bypass hooks without explicit
  user authorization.
