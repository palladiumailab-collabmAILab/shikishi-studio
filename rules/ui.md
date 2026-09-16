# UI rules

- Make loading, running, success, empty, warning, failure, and cancelled states
  explicit. Do not replace a specific error with a generic blank state.
- Show actionable errors with the affected file, field, job, or operation when
  known. Preserve structured diagnostic codes internally even when displaying
  friendlier text.
- Keep shared selection and workflow state in one owner. Multiple views of the
  same state must update through the same actions.
- Keep view-only state such as zoom, panel expansion, or local sorting close to
  the component that owns it. It must not mutate analysis results.
- When a newer request supersedes an older one, cancel the old request when
  possible and reject stale responses by identity.
- Preserve the last valid result while a replacement is loading or fails when
  that behavior helps recovery, and label the displayed result unambiguously.
- Do not communicate status, selection, quality, or severity by color alone.
  Use text, icons, patterns, shape, or weight as an additional cue.
- Display rounded values consistently while preserving unrounded values in
  exported data and traceable evidence.
- Keep destructive actions explicit, scoped, and confirmable. Prefer reversible
  operations and state exactly what will be affected.
- Ensure keyboard access, visible focus, useful labels, and readable contrast
  for interactive controls.
