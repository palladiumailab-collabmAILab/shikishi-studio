# Codex harness upstream

The common Codex development harness used by this repository is sourced from:

- repository: `palladiumailab-collabmAILab/codex-dev-harness`
- source revision: `25a3929cdcdba856fd1cc4e45cccf5726132f478`

The upstream harness is the canonical source for the shared operating contract, baseline, generic skills, templates, and harness utility scripts copied into this repository.

When the same shared file changes upstream, update this repository from the upstream version rather than maintaining an independent fork. Project-specific rules may refine the common harness for Shikishi Studio, but should remain visibly separated from the shared contract and must not silently weaken it.

Project-specific material includes `rules/`, the Shikishi-specific skills, application/runtime configuration, model-weight safeguards, Kaggle workflow rules, and the Shikishi quality commands.
