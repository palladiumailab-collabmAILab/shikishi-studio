# Data-processing rules

- Treat source images, captions, metadata, and imported datasets as immutable.
  Never delete or overwrite them as part of normal preparation.
- Write normalized data, exclusions, review queues, splits, and reports to a
  separate output tree. Every derived artifact must be reproducible from source
  data, configuration, code version, and random seed.
- Validate file readability, schema, identifiers, dimensions, and required
  relationships at ingestion. Do not infer success from a filename extension
  or MIME type alone when the content can be inspected.
- Distinguish three outcomes explicitly:
  - invalid or certainly unusable input: exclude with a machine-readable reason;
  - ambiguous input: preserve it and add it to a review queue;
  - accepted input: process it normally.
- Never silently discard, repair, relabel, or merge input. Automatic repair is
  allowed only when the rule is explicit, deterministic, reversible, logged,
  and covered by tests.
- Keep thresholds, tag policies, class mappings, and sampling ratios in
  configuration. Record the effective configuration with each run.
- Make ordering and tie-breaking deterministic. Stable identifiers and sorted
  inputs must be used before seeded random operations.
- Keep internal numeric precision. Round only at display or export boundaries,
  and state units and coordinate conventions explicitly.
- Preserve provenance for classification, duplicate grouping, filtering, and
  caption changes. Reports must contain enough identifiers and metrics for a
  reviewer to reproduce each decision.
- Prevent leakage across train and validation data by grouping exact duplicates,
  near duplicates, and other related variants before splitting.
- Prefer conservative automation for subjective quality or style judgments.
  Scores may rank review candidates, but uncertain cases must not be removed
  automatically.
- A rerun with identical source, configuration, dependency versions, and seed
  must produce the same logical result.

