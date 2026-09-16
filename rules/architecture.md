# Architecture rules

- Give each module one clear responsibility and keep dependency direction
  explicit. Boundary layers may depend on domain logic; domain logic must not
  depend on UI, CLI, notebook, or transport frameworks.
- Separate external I/O, schema validation, pure transformation or analysis,
  aggregation, presentation, and persistence. Do not place domain calculations
  in API handlers, notebooks, or UI callbacks.
- Keep one source of truth for each contract, constant, and piece of shared
  state. Generate derived schemas or types when practical instead of maintaining
  duplicate handwritten definitions.
- Validate requests and file contents before passing them into internal logic.
  Validate successful external responses before treating them as trusted data.
- Use explicit domain values and structured results at module boundaries.
  Avoid passing loosely structured dictionaries when a stable typed model is
  available.
- Wrap third-party libraries behind small project-owned functions when their
  behavior, exceptions, or data representation must be normalized.
- Preserve evidence needed to trace an output back to its source record, input
  file, configuration, and processing decision.
- For concurrent or asynchronous work, define who owns state, how cancellation
  propagates, and which result wins. A stale result must not overwrite a newer
  request.
- Add a new abstraction only when it establishes a useful boundary or removes
  proven duplication. Prefer extending an existing cohesive module over adding
  speculative layers.
- Keep public interfaces no broader than necessary. Do not expose third-party
  representations as project contracts unless that coupling is deliberate.
- Choose algorithms and data structures for the expected scale. Measure before
  adding complexity for non-obvious performance work, and avoid unbounded
  queues, caches, and concurrency.
