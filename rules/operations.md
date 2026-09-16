# Operations rules

- Model long-running local and cloud work as explicit states such as prepared,
  submitted, queued, running, succeeded, failed, cancelled, and artifact saved.
  Do not infer one state from another.
- Persist a timestamped work log for submissions, job identifiers, state
  transitions, progress, retries, failures, fixes, and downloaded artifacts.
  Logs must be useful without exposing secrets.
- Make submission and preparation idempotent. Before creating a replacement,
  check whether the intended dataset, job, notebook version, or artifact already
  exists and whether it matches the requested inputs.
- Retry only failures that are plausibly transient. Use delay or backoff, record
  every attempt, and stop retrying when credentials, configuration, code, quota,
  or data must be corrected.
- Monitoring must inspect authoritative job state and recent logs. A page being
  open, a process existing, or a request returning successfully is not proof
  that useful work is progressing.
- Define measurable completion criteria before starting. Report completion only
  from evidence such as step counters, epoch progress, exit status, checksums,
  or the presence of a verified artifact.
- Save checkpoints often enough to recover from the expected failure modes.
  Resume only when checkpoint and configuration compatibility have been checked.
- When a required output is remote, download it to a documented local path and
  verify its existence, nonzero size, expected format, and checksum when
  available.
- Keep run configuration, dependency versions, random seed, source dataset
  identity, and code revision with the run record.
- Prefer scripts or modules over manual notebook edits for repeatable work.
  Notebooks should orchestrate reusable code and expose progress clearly.
- Before any model-weight mutation, state the target artifact, operation,
  execution tool, expected output, and overwrite behavior, then obtain explicit
  user approval. This applies to training, continued training, fine-tuning,
  adapter merging, tensor resaving, conversion that rewrites tensors, and
  overwriting a weight file. Prefer dedicated, reviewable training tools, but do
  not interpret that preference as authorization. Inference-scale changes,
  unchanged artifact downloads, and checksum verification are non-mutating.
- On failure, preserve the last useful state and diagnostic evidence. Fix the
  smallest identified cause, verify it, and resume from the safest valid point.
- Validate critical configuration at startup and fail clearly when it is
  unusable. Readiness must show whether work can actually be served; liveness
  must not disguise a stuck process.
- For material incidents, non-obvious fixes, failed approaches worth avoiding,
  accepted limitations, and decisions likely to affect later work, append a
  compact JSON record to `docs/engineering/events.jsonl`. Treat records as
  historical evidence, not immutable instructions, and never include secrets,
  personal data, or bulky raw logs.
