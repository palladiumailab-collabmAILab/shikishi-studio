# Testing rules

- Add the smallest failing regression test before fixing a defect when the
  behavior can be isolated reliably.
- Test observable behavior and contracts rather than implementation details.
  Prefer precise assertions over broad snapshots.
- Cover the normal path, boundary values, malformed input, expected failures,
  and recovery or review behavior for every changed rule.
- For data pipelines, test source preservation, deterministic ordering, seeded
  splitting, duplicate grouping, reason codes, provenance, and idempotent reruns.
- For external services, keep contract parsing and job-state handling testable
  without a live account. Use small fixtures and simulated responses for unit
  tests; keep live smoke tests explicit and opt-in.
- Test configuration defaults and overrides. A threshold or mapping change must
  have a test that demonstrates its effect.
- Verify that errors and warnings remain distinguishable and actionable. Do not
  accept a generic empty result where a structured diagnostic is expected.
- Keep fixtures minimal and readable. Do not add private datasets, credentials,
  model weights, or large generated artifacts to the test suite.
- Provide one documented command or script that runs all required local checks.
- Run checks appropriate to the changed surface and report exactly what ran.
  Never claim a check passed when it was skipped, unavailable, or failed.

