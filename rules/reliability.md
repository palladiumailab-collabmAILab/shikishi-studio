# Contracts, state, and reliability rules

- Define valid inputs, outputs, invariants, failure semantics, and compatibility
  expectations for public APIs, CLI and file formats, schemas, and events.
- Keep logical state changes atomic. Use transactions or atomic file replacement
  where partial writes could be mistaken for valid state, and never record failed
  work as successful.
- Make retried, resumed, redelivered, or duplicated operations idempotent, or
  protect them with a deliberate mechanism such as unique constraints,
  idempotency keys, version checks, durable completion markers, or deduplication.
- Give external waits finite timeouts. Retry only plausibly transient failures,
  bound total attempts or elapsed time, and prevent layered retries from
  multiplying unexpectedly.
- When interruption is costly, persist confirmed progress so work can resume
  without repeating completed side effects. Make partial successes and failures
  independently identifiable.
- Protect shared mutable state with synchronization, versioning, database, or
  filesystem primitives appropriate to its scope. Prevent stale writes, lost
  updates, and duplicate side effects.
- For schema or data migrations, plan for interruption and mixed-version
  operation. Validate before destructive cleanup and provide a realistic
  rollback, compensation, backup-and-restore, or roll-forward path.
- A code rollback is not a data recovery strategy when persistent state has
  changed incompatibly.
